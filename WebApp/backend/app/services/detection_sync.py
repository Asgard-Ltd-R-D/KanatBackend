"""Each Session's detection, one board per enabled camera (ADR-0008): whether a
Run of the Detection Service watches each board, on that camera's Stream from
MediaMTX. A Session spans every enabled camera, so it has a Run per board, each
keyed by (session_id, camera alias).

Held in memory, which is enough with the backend's single worker, and pushed on
the Session's live stream at each change, naming the board. A board the backend
has not asked a Run for reads `none`.

Every camera_sync_interval_s the backend reconciles the Detection Service's Runs
with the boards that should hold them (`reconcile`): the active Session's
enabled cameras, one Run each, so a Run that was lost, or never started, comes
back by itself, from a fresh baseline.

Each Run that watches a board is stored with its Session, with its Baseline View
(ADR-0009), the first time the backend sees it watching. Each status read, and
the end's answer, then moves it on to how far it watched.
"""
import asyncio
import logging
import math
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import anyio
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session as DBSession

from app.config.settings import settings
from app.core.database import SessionLocal
from app.core.live import hub
from app.core.locks import db_write
from app.models import Run, Session
from app.repositories import cameras as cameras_repo
from app.repositories import runs as runs_repo
from app.repositories import sessions as sessions_repo
from app.schemas.live import DetectionUpdatedEvent, RunMovedEvent
from app.schemas.run import Place
from app.schemas.session import BoardDetection, Detection
from app.services import detection_client

log = logging.getLogger(__name__)

# A board is keyed by its Session and its camera's alias
Key = tuple[uuid.UUID, str]

NONE = Detection(state="none")
WATCHING = Detection(state="watching")
SERVICE_DOWN = Detection(state="not_watching", reason="service_down")
CAMERA_DISABLED = Detection(state="not_watching", reason="camera_disabled")
# The Run is gone while the Detection Service answers: its Stream failed, or
# the service restarted between two ticks, which the backend cannot tell
# apart, so no reason is given until the new Run's start answers
RUN_LOST = Detection(state="not_watching")
# Kept once the Session completes, unlike the others, until it is reopened
END_UNCONFIRMED = Detection(state="end_unconfirmed")
# The states with no start or end under way, which a tick may change; the
# call under way sets the state itself once it is answered
IDLE = ("none", "watching", "not_watching")
# A start under way longer than this was lost to an error before it set its
# answer, and is let go by the next tick: well past the longest call it makes
# (detection_client.START_TIMEOUT_S). An end is never let go: ending() sets
# its answer however its block leaves, and until then the Session's
# completion or deletion is still under way, which a new Run would race
STUCK_S = 60

# A Run's registered place is kept once it lies more than this from the last
# one kept, at any point of its Target outlines, in the baseline frame's
# picture px (ADR-0009): a Board holding still adds no rows, a creeping one
# (~1 px/s on CamA) a few a minute
MOVED_PX = 2.0

_states: dict[Key, Detection] = {}
# When each state in _states was set (time.monotonic())
_since: dict[Key, float] = {}
# The boards a Run has watched since their Run's end was last confirmed,
# whatever they read now: one that reads not watching since may still have
# lost its last Bullet Holes with its Run
_watched: set[Key] = set()
# The boards whose Run a retake asked to stop, the stop unanswered: a Run of
# theirs still there has the old sheet's baseline, so it is stopped, not
# adopted, and none is started for them until it is gone
_to_stop: set[Key] = set()
# The Sessions whose end is under way (ending(): completing or deleting). No
# board of theirs is started while they are here, so a camera enabled in the
# same moment cannot leave a Run behind the completion
_ending: set[uuid.UUID] = set()
# Reentrant: retaking_baseline holds it round a _set
_lock = threading.RLock()


def state_of(session_id: uuid.UUID, camera: str) -> Detection:
    return _states.get((session_id, camera), NONE)


def boards_of(session_id: uuid.UUID) -> list[BoardDetection]:
    """Each of the Session's boards that has a detection state, for its
    response. The frontend shows a board per enabled camera; a board missing
    here reads `none`."""
    with _lock:
        return [BoardDetection(camera_alias=cam, detection=detection)
                for (sid, cam), detection in _states.items() if sid == session_id]


def _set(key: Key, detection: Detection, only_from: tuple[str, ...] | None = None) -> bool:
    """Changes the board's state and pushes it, unless `only_from` is given
    and the state is none of those. Returns whether it changed it, or it
    already read that; that is not pushed again. `end_unconfirmed` is read
    as `none` for a board not in _watched, under the same lock as the
    confirmed end that takes it out."""
    session_id, camera = key
    with _lock:
        current = state_of(session_id, camera)
        if only_from is not None and current.state not in only_from:
            return False
        if detection == END_UNCONFIRMED and key not in _watched:
            detection = NONE
        if detection == WATCHING:
            _watched.add(key)
        elif detection.state in ("none", "end_unconfirmed"):
            _watched.discard(key)
        if detection == current:
            return True
        if detection.state == "none":
            _states.pop(key, None)
            _since.pop(key, None)
        else:
            _states[key] = detection
            _since[key] = time.monotonic()
        # Pushed under the lock, so two changes at once reach the frontend in order
        hub.publish_from_thread(session_id, DetectionUpdatedEvent(camera_alias=camera, detection=detection))
    return True


async def watch_all(session_id: uuid.UUID, cameras: list[str]) -> None:
    """Ask for every board's Run at once: `watch` blocks until a board is
    watching or its start times out, so starting them in turn would let one slow
    or unavailable camera hold up detection on the others. Each runs in the
    threadpool (where `publish_from_thread` can reach the event loop), together."""
    await asyncio.gather(*(run_in_threadpool(watch, session_id, camera) for camera in cameras))


def starting(session_id: uuid.UUID, camera: str) -> None:
    """The board's Run is about to be asked for (`watch`)."""
    _set((session_id, camera), Detection(state="starting"))


def _to_picture(H: tuple, point: tuple[float, float]) -> tuple[float, float]:
    """A template point through a template_to_picture homography, in picture px."""
    x, y = point
    w = H[2][0] * x + H[2][1] * y + H[2][2]
    return (H[0][0] * x + H[0][1] * y + H[0][2]) / w, (H[1][0] * x + H[1][1] * y + H[1][2]) / w


def _follow(db: DBSession, stored: Run | None, run: detection_client.Run) -> None:
    """Moves the stored Run on to how far `run`, its status read or end's
    answer, says it watched: `watched_until` to its `looked_at`, and its
    `registered` place kept if it lies more than MOVED_PX from the last kept,
    then pushed as `run_moved`. A read no newer than `watched_until`, a
    tick's that raced an end's answer, changes neither: its place may be
    one the Board has since left."""
    if stored is None or run.looked_at is None or run.looked_at <= stored.watched_until:
        return
    stored.watched_until = run.looked_at
    last = Place.model_validate(stored.places[-1])
    new = run.registered
    moved = new is not None and any(
        math.dist(_to_picture(last.template_to_picture, p), _to_picture(new.template_to_picture, p)) > MOVED_PX
        for outline in stored.baseline_view["targets"] for p in outline)
    if moved:
        stored.places = [*stored.places, new.model_dump(mode="json")]
    runs_repo.save(db)
    if moved:
        hub.publish_from_thread(stored.session_id,
                                RunMovedEvent(camera_alias=stored.camera_alias, taken_at=stored.taken_at))


def retaking_baseline(session_id: uuid.UUID, camera: str) -> bool:
    """The operator asks one of the active Session's boards for a fresh
    baseline, after re-hanging its Target Sheet: it reads `starting` until a new
    Run is watching, so a tick neither starts nor ends one in between. False
    when a start or an end is already under way on that board. Its Run is put in
    _to_stop under the same lock, so an end that races the retake stops it
    rather than judging it."""
    key = (session_id, camera)
    with _lock:
        if not _set(key, Detection(state="starting"), only_from=IDLE):
            return False
        _to_stop.add(key)
    return True


def retake_baseline(session_id: uuid.UUID, camera: str) -> None:
    """Ends the board's Run and asks for a new one, which takes its baseline
    from what the camera sees now, the Session left active.
    The Run is stopped, not ended as at completion: the Candidates it has
    open are the re-hung sheet's change, not shots, and are dropped unposted.
    A Session completed meanwhile reads `ending`, and `watch` ends the Run it
    started. A stop not answered leaves it not watching, and the old Run, if
    it is still there, to reconcile to stop: a start now would be answered
    with it."""
    if _end_run(session_id, camera, judge=False) is None:
        _set((session_id, camera), SERVICE_DOWN, only_from=("starting",))
        return
    watch(session_id, camera)


def _store_run(session_id: uuid.UUID, camera: str, run: detection_client.Run) -> None:
    """Stores the Run, watching on the board `camera`, for its Session if that
    still exists; one already stored is not stored again. Done before
    `watching` is pushed, so the frontend's refetch on it brings the Run.
    Then moves it on to how far `run` says it watched (`_follow`).
    Storing fails with the database, or a Run view it cannot place, logged:
    the next status read that shows the Run stores it, and the board is not
    left reading `starting`."""
    if run.baseline_view is None:
        return
    db = SessionLocal()
    try:
        if sessions_repo.exists(db, session_id):
            view = run.baseline_view
            # Placed where its baseline frame showed the Board, and watched until then
            baseline = Place(at=view.taken_at, template_to_picture=view.template_to_picture)
            runs_repo.add_once(db, session_id, camera, view.taken_at, view.model_dump(mode="json"),
                               [baseline.model_dump(mode="json")], view.taken_at)
            # Serialized (db_write) against the end's answer following the same
            # Run: on SQLite get_for_update does not lock, so a concurrent
            # read-modify-write of places/watched_until could be lost
            with db_write:
                _follow(db, runs_repo.get_for_update(db, session_id, camera, view.taken_at), run)
    except Exception as e:
        log.warning("The Run of session %s board %s is not stored yet: %s", session_id, camera, e, exc_info=True)
    finally:
        db.close()


def watch(session_id: uuid.UUID, camera: str, only_from: tuple[str, ...] = ("starting",)) -> None:
    """Asks the Detection Service for the board's Run on the camera's Stream,
    which answers once the Run is watching: seconds, so it runs after the
    request that started the Session has answered, or in the reconcile loop.
    The answer is set only if the board still reads one of `only_from`: one
    that started ending meanwhile keeps its state, and a Run started for it
    is ended. Any other error reads not watching, with no reason, which the
    next tick retries, rather than leaving the board `starting`."""
    key = (session_id, camera)
    with _lock:
        if session_id in _ending:
            return   # the Session's end is under way: do not start a Run for it
    try:
        run = detection_client.start_run(session_id, camera, f"{settings.mediamtx_rtsp_url}/{camera}")
    except detection_client.DetectionServiceUnreachable as e:
        log.warning("Session %s board %s is not watched: the Detection Service did not answer: %s",
                    session_id, camera, e)
        result = SERVICE_DOWN
    except detection_client.RunRefused as e:
        log.warning("Session %s board %s is not watched: %s", session_id, camera, e)
        if e.status != 409:
            result = Detection(state="not_watching", reason="stream_failed", detail=e.detail)
        elif e.holder == session_id:
            # Its own previous Run still ending, a lost Run's: the next tick retries
            result = Detection(state="not_watching", detail=e.detail)
        else:
            result = Detection(state="not_watching", reason="other_session", detail=e.detail)
    except Exception:
        log.exception("Session %s board %s is not watched: asking for its Run failed", session_id, camera)
        result = RUN_LOST
    else:
        _store_run(session_id, camera, run)
        result = WATCHING
    if not _set(key, result, only_from) and result.state == "watching" and state_of(session_id, camera).state in ("ending", "none"):
        # Its end may have reached the Detection Service before this start did,
        # and found no Run to end. (A board already watching had a second
        # start, its create's and a tick's, answered with the same Run.)
        _end_run(session_id, camera)


def _end_run(session_id: uuid.UUID, camera: str, judge: bool = True) -> bool | None:
    """Whether the Detection Service answered that this end ended the Run:
    False when it had no Run for the board, None when it could not be
    reached, either way not confirmed. An answer of either kind says the
    board has no Run left, so takes it out of _to_stop. `judge` as
    detection_client.end_run's, but a board in _to_stop is stopped
    whatever it says: its Run's open Candidates are the re-hang's. Its
    answer moves the stored Run it names on to how far it watched
    (`_follow`); one never stored, the database down all its life, moves
    none."""
    key = (session_id, camera)
    try:
        ended = detection_client.end_run(session_id, camera, judge and key not in _to_stop)
    except detection_client.DetectionServiceUnreachable as e:
        log.warning("The Run of session %s board %s may not have ended: %s", session_id, camera, e)
        return None
    with _lock:
        _to_stop.discard(key)
        if ended is not None:
            _watched.discard(key)
    if ended is None:
        return False
    db = SessionLocal()
    try:
        if ended.baseline_view is not None:   # none for a Run ended before it watched
            # Serialized (db_write) against a tick following the same Run
            with db_write:
                _follow(db, runs_repo.get_for_update(db, session_id, camera, ended.baseline_view.taken_at), ended)
    except Exception as e:   # the Run did end: only what it reported is lost
        log.warning("How far the Run of session %s board %s watched is not stored: %s",
                    session_id, camera, e, exc_info=True)
    finally:
        db.close()
    return True


def _boards_in_state(session_id: uuid.UUID) -> list[str]:
    """The cameras of the Session that have a detection state now."""
    with _lock:
        return sorted({cam for (sid, cam) in _states if sid == session_id})


# The ends run on their own worker limiter, not the default one run_in_threadpool
# uses. ending() is called from a sync request, which already holds a default
# worker token, and blocks in from_thread.run below while its ends run: if those
# ends also drew from the default limiter, enough concurrent completions would
# leave every default token held by a waiting parent with none left for its
# ends, wedging them and every other sync endpoint for good. A separate pool
# keeps the ends' capacity out of reach of the parents waiting on them.
_END_WORKERS = anyio.CapacityLimiter(40)


def _in_parallel(fn: Callable[[str], None], cameras: list[str]) -> None:
    """Run `fn` on each camera at once and wait for all. For board ends, which
    each block on the Detection Service independently, so ending them in turn
    would add their waits up. ending() runs in a sync request (an AnyIO worker
    thread), so the fan-out goes back onto the event loop and each `fn` runs in
    an AnyIO worker thread -- where `publish_from_thread` can reach the loop, as
    watch_all does; a plain threading.Thread could not publish run_moved. The
    ends take tokens from _END_WORKERS, not the default pool the calling request
    holds one of, so a waiting parent cannot starve its own ends."""
    async def end_on_worker(camera: str) -> None:
        await anyio.to_thread.run_sync(fn, camera, limiter=_END_WORKERS)

    async def fan_out() -> None:
        async with anyio.create_task_group() as task_group:
            for camera in cameras:
                task_group.start_soon(end_on_worker, camera)

    anyio.from_thread.run(fan_out)


@contextmanager
def ending(session: Session) -> Iterator[None]:
    """Ends every one of the active Session's boards' Runs before the block
    runs, which completes or deletes the Session: each board reads `ending`
    from the start of the end until the block has committed that, so no tick
    starts a board a Run in between, while each Run judges the Candidates it has
    open and posts what persisted. Then `none`.
    A Detection Service that cannot be reached, or does not answer within
    END_TIMEOUT_S, is logged, and the Session ends anyway. So does a Run that is
    already gone. A board then reads `end_unconfirmed` if a Run watched it
    since its Run's end was last confirmed, even if it reads not watching by
    now: its last Bullet Holes may be missing. A block that fails before it
    commits leaves the Session active, each board reading `none`, and the next
    tick watches it again; one that fails after is read as one that succeeded.

    ponytail: a deleted Session's `end_unconfirmed` stays in memory until the
    backend restarts, a few bytes for each board; reconcile does not read the
    deleted ones apart from the completed ones"""
    if session.status != "active":
        yield
        return
    session_id = session.id
    # No board of this Session is started from now until the end is done, so a
    # camera enabled in the same moment cannot leave a Run behind the completion
    with _lock:
        _ending.add(session_id)
    try:
        boards = set(_boards_in_state(session_id))
        # _states is empty after a backend restart, though the Detection Service
        # may still watch this Session's boards; discover those too, so their
        # Runs are ended now and not left for reconcile to drain after the
        # Session has completed, when their last Bullet Holes would be rejected.
        try:
            live = [run for run in detection_client.status() if run.session_id == session_id]
            answered = True
        except detection_client.DetectionServiceUnreachable:
            live, answered = [], False
        live_cameras = {run.camera for run in live}
        # After a restart _states is empty; recover the Session's other boards
        # from its stored Runs. A stored board the service does not list either
        # ended cleanly (its camera was removed, so it reads disabled now) or was
        # lost unconfirmed (its camera still enabled, its Run having crashed or
        # its Stream failed — service.py drops such a Run too). Warn only the
        # latter; when the service could not be asked at all, none is confirmed.
        db = SessionLocal()
        try:
            stored = runs_repo.cameras_of(db, session_id)
            enabled = ({c.alias for c in cameras_repo.list_all(db) if c.enabled}
                       if stored and answered else set())
        finally:
            db.close()
        with _lock:
            for run in live:
                # A watching or ending Run has watched: keep end_unconfirmed if
                # its end is not confirmed, which _set reads from _watched
                if run.state in ("watching", "ending"):
                    _watched.add((session_id, run.camera))
                boards.add(run.camera)
            for camera in stored:
                if camera in live_cameras:
                    continue   # handled above
                if not answered or camera in enabled:
                    # unconfirmed: the service could not be asked, or an enabled
                    # board's Run is gone (lost, not a clean removal)
                    _watched.add((session_id, camera))
                    boards.add(camera)
                # else: its camera was removed and its Run already ended; leave it
        boards = sorted(boards)
        if not boards:
            yield
            return
        for camera in boards:
            _set((session_id, camera), Detection(state="ending"))
        confirmed: dict[str, bool | None] = {}
        try:
            # Whether each Run's end was confirmed is read by _set once answered: a
            # start answered just before the end began, or a tick's end of the same
            # Run confirmed meanwhile, changes it.
            # ponytail: the Detection Service drops its Run before it answers that
            # tick's end, so this end's 404 can come first and read end_unconfirmed,
            # the safe way round. Waiting on an end of the same Run already under
            # way closes it if it ever matters.
            # The boards are ended together: each _end_run blocks until that board's
            # Run has judged its open Candidates and drained its posts (seconds), so
            # ending them in turn would add those waits up across the boards. Each
            # board is independent, and _end_run takes its own locks, so this only
            # overlaps the waiting.
            def end_board(camera: str) -> None:
                confirmed[camera] = _end_run(session_id, camera)
            _in_parallel(end_board, boards)
            yield
        except BaseException:
            still_active = _still_active(session_id)
            for camera in boards:
                _set((session_id, camera), NONE if confirmed.get(camera) or still_active else END_UNCONFIRMED)
            raise
        for camera in boards:
            _set((session_id, camera), NONE if confirmed.get(camera) else END_UNCONFIRMED)
    finally:
        with _lock:
            _ending.discard(session_id)


def _still_active(session_id: uuid.UUID) -> bool:
    """Whether the Session is active in the database: a block that failed may
    have committed its end first. Not known reads not active, so a board
    whose Run's end was not confirmed warns its last shots may be missing."""
    db = SessionLocal()
    try:
        session = sessions_repo.get(db, session_id)
        return session is not None and session.status == "active"
    except Exception:
        log.exception("Reading whether session %s is still active failed", session_id)
        return False
    finally:
        db.close()


def reopened(session_id: uuid.UUID) -> None:
    """The Session is active again: its boards' last ends not being confirmed no
    longer stand, and reconcile watches them again from a fresh baseline."""
    for camera in _boards_in_state(session_id):
        _set((session_id, camera), NONE, only_from=("end_unconfirmed",))


def reconcile(db: DBSession) -> None:
    """One round of keeping the Detection Service's Runs on the boards that
    should hold them: the active Session's enabled cameras, one Run each. A Run
    of any other board is ended — another Session's, one left by a Session
    completed while the service could not be told, or one whose camera was
    disabled or deleted — and a board with none is started. Every board of a
    Session no longer active reads `none`, unless its end was not confirmed. A
    board with a start or an end under way is left to it."""
    # Asked before the database is read: a Run is only started for a board of a
    # Session already committed, so the Session of each Run it reports is read below
    try:
        runs, answered = detection_client.status(), True
    except detection_client.DetectionServiceUnreachable:
        runs, answered = [], False
    cameras = {c.alias: c for c in cameras_repo.list_all(db)}
    enabled = {alias for alias, c in cameras.items() if c.enabled}
    active = sessions_repo.list_active(db)
    active_ids = {s.id for s in active}
    session = active[0] if active else None

    with _lock:
        ended = [key for key in _states if key[0] not in active_ids]
        stuck = [(key, detection.state) for key, detection in _states.items()
                 if detection.state == "starting" and time.monotonic() - _since.get(key, time.monotonic()) > STUCK_S]
    for key, state in stuck:
        log.warning("Session %s board %s read %s for over %ss: letting it go", key[0], key[1], state, STUCK_S)
        _set(key, NONE if key[0] in active_ids else END_UNCONFIRMED, only_from=(state,))
    for key in ended:
        # Left by a start that raced its Session's end
        _set(key, NONE, only_from=IDLE)

    runs_by_key = {(r.session_id, r.camera): r for r in runs}
    if answered:
        for (sid, cam), run in list(runs_by_key.items()):
            if run.state == "ending":
                continue
            if session is None or sid != session.id or cam not in enabled:
                # Its Session completed or was deleted while the Detection
                # Service could not be told, or its camera was disabled or deleted
                log.info("Ending the Run of session %s board %s: it is no longer one to watch", sid, cam)
                _end_run(sid, cam)
                runs_by_key.pop((sid, cam), None)

    if session is None:
        return

    # A board whose camera was disabled or deleted, but that read something
    # other than `none` while it had one
    for cam in set(_boards_in_state(session.id)) - enabled:
        _set((session.id, cam), CAMERA_DISABLED, only_from=IDLE)

    if not answered:
        for cam in enabled:
            _set((session.id, cam), SERVICE_DOWN, only_from=IDLE)
        return

    with _lock:
        if session.id in _ending:
            return   # the Session's end is under way: start no board, new or not

    for cam in sorted(enabled):
        key = (session.id, cam)
        run = runs_by_key.get(key)
        current = state_of(session.id, cam).state
        if current not in IDLE or (run and run.state == "ending"):
            continue   # a start or an end is under way on this board
        if key in _to_stop:   # a retake's stop went unanswered
            # Its Run still there, watching or starting, has or may build the
            # old sheet's baseline. (Another board's was ended above, and an
            # ending one returned.)
            if run:
                log.info("Stopping the Run of session %s board %s: its baseline was retaken", session.id, cam)
                if _end_run(session.id, cam, judge=False) is None:
                    continue
                run = None
            else:   # the stop did end it, only its answer was lost
                with _lock:
                    _to_stop.discard(key)
        if run and run.state == "watching":
            # Unknown since the backend restarted, or its start not answered to it
            _store_run(session.id, cam, run)
            _set(key, WATCHING, only_from=IDLE)
            continue
        if current == "none":
            # Reopened, or not asked for since the backend restarted. A Session
            # being completed or deleted reads `ending` until that is committed
            shown = Detection(state="starting")
        elif current == "watching":
            shown = RUN_LOST
        else:
            shown = state_of(session.id, cam)   # retried, still not watching
        if not _set(key, shown, only_from=(current,)):
            continue   # its end began meanwhile
        log.info("Session %s board %s has no Run watching it: starting one", session.id, cam)
        watch(session.id, cam, only_from=(shown.state,))


def _reconcile_once() -> None:
    db = SessionLocal()
    try:
        reconcile(db)
    finally:
        db.close()


async def run_forever() -> None:
    """The reconcile loop, started with the app (main.py) beside the camera
    sync loop and as often. A round waits for the Runs it starts or ends, so
    rounds are camera_sync_interval_s apart rather than that often. Logs only
    when its state changes, not on every failed attempt."""
    failing = False
    while True:
        try:
            await run_in_threadpool(_reconcile_once)
            if failing:
                log.info("Reconciling the Detection Service's Runs restored")
            failing = False
        except Exception as e:  # keep the loop alive whatever one attempt hits
            if not failing:
                log.warning("Reconciling the Detection Service's Runs failing, retrying every %ss: %s",
                            settings.camera_sync_interval_s, e)
            failing = True
        await asyncio.sleep(settings.camera_sync_interval_s)
