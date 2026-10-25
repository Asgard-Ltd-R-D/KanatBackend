"""Each Session's detection: whether a Run of the Detection Service watches it
(ADR-0008), on its camera's Stream from MediaMTX.

Held in memory, which is enough with the backend's single worker, and pushed
on the Session's live stream at each change. A Session the backend has not
asked a Run for reads `none`.

Every camera_sync_interval_s the backend reconciles the Detection Service's
one Run with the Session that should hold it (`reconcile`), so a Run that was
lost, or never started, comes back by itself, from a fresh baseline.

Each Run that watches a Session is stored with it, with its Baseline View
(ADR-0009), the first time the backend sees it watching. Each status read,
and the end's answer, then moves it on to how far it watched.
"""
import asyncio
import logging
import math
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session as DBSession

from app.config.settings import settings
from app.core.database import SessionLocal
from app.core.live import hub
from app.models import Run, Session
from app.repositories import cameras as cameras_repo
from app.repositories import runs as runs_repo
from app.repositories import sessions as sessions_repo
from app.schemas.live import DetectionUpdatedEvent, RunMovedEvent
from app.schemas.run import Place
from app.schemas.session import Detection
from app.services import detection_client

log = logging.getLogger(__name__)

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

_states: dict[uuid.UUID, Detection] = {}
# When each state in _states was set (time.monotonic())
_since: dict[uuid.UUID, float] = {}
# The Sessions a Run has watched since their Run's end was last confirmed,
# whatever they read now: one that reads not watching since may still have
# lost its last Bullet Holes with its Run
_watched: set[uuid.UUID] = set()
_lock = threading.Lock()


def state_of(session_id: uuid.UUID) -> Detection:
    return _states.get(session_id, NONE)


def _set(session_id: uuid.UUID, detection: Detection, only_from: tuple[str, ...] | None = None) -> bool:
    """Changes the Session's state and pushes it, unless `only_from` is given
    and the state is none of those. Returns whether it changed it, or it
    already read that; that is not pushed again. `end_unconfirmed` is read
    as `none` for a Session not in _watched, under the same lock as the
    confirmed end that takes it out."""
    with _lock:
        current = state_of(session_id)
        if only_from is not None and current.state not in only_from:
            return False
        if detection == END_UNCONFIRMED and session_id not in _watched:
            detection = NONE
        if detection == WATCHING:
            _watched.add(session_id)
        elif detection.state in ("none", "end_unconfirmed"):
            _watched.discard(session_id)
        if detection == current:
            return True
        if detection.state == "none":
            _states.pop(session_id, None)
            _since.pop(session_id, None)
        else:
            _states[session_id] = detection
            _since[session_id] = time.monotonic()
        # Pushed under the lock, so two changes at once reach the frontend in order
        hub.publish_from_thread(session_id, DetectionUpdatedEvent(detection=detection))
    return True


def starting(session_id: uuid.UUID) -> None:
    """The Session's Run is about to be asked for (`watch`)."""
    _set(session_id, Detection(state="starting"))


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
        hub.publish_from_thread(stored.session_id, RunMovedEvent(taken_at=stored.taken_at))


def _store_run(session_id: uuid.UUID, alias: str, run: detection_client.Run) -> None:
    """Stores the Run, watching on the camera `alias`, for its Session if that
    still exists; one already stored is not stored again. Done before
    `watching` is pushed, so the frontend's refetch on it brings the Run.
    Then moves it on to how far `run` says it watched (`_follow`).
    Storing fails with the database, or a Run view it cannot place, logged:
    the next status read that shows the Run stores it, and the Session is not
    left reading `starting`."""
    if run.baseline_view is None:
        return
    db = SessionLocal()
    try:
        if sessions_repo.exists(db, session_id):
            view = run.baseline_view
            # Placed where its baseline frame showed the Board, and watched until then
            baseline = Place(at=view.taken_at, template_to_picture=view.template_to_picture)
            runs_repo.add_once(db, session_id, alias, view.taken_at, view.model_dump(mode="json"),
                               [baseline.model_dump(mode="json")], view.taken_at)
            _follow(db, runs_repo.get_for_update(db, session_id, view.taken_at), run)
    except Exception as e:
        log.warning("The Run of session %s is not stored yet: %s", session_id, e, exc_info=True)
    finally:
        db.close()


def watch(session_id: uuid.UUID, alias: str, only_from: tuple[str, ...] = ("starting",)) -> None:
    """Asks the Detection Service for the Session's Run on the camera's Stream,
    which answers once the Run is watching: seconds, so it runs after the
    request that started the Session has answered, or in the reconcile loop.
    The answer is set only if the Session still reads one of `only_from`: one
    that started ending meanwhile keeps its state, and a Run started for it
    is ended. Any other error reads not watching, with no reason, which the
    next tick retries, rather than leaving the Session `starting`."""
    try:
        run = detection_client.start_run(session_id, f"{settings.mediamtx_rtsp_url}/{alias}")
    except detection_client.DetectionServiceUnreachable as e:
        log.warning("Session %s is not watched: the Detection Service did not answer: %s", session_id, e)
        result = SERVICE_DOWN
    except detection_client.RunRefused as e:
        log.warning("Session %s is not watched: %s", session_id, e)
        if e.status != 409:
            result = Detection(state="not_watching", reason="stream_failed", detail=e.detail)
        elif e.holder == session_id:
            # Its own previous Run still ending, a lost Run's: the next tick retries
            result = Detection(state="not_watching", detail=e.detail)
        else:
            result = Detection(state="not_watching", reason="other_session", detail=e.detail)
    except Exception:
        log.exception("Session %s is not watched: asking for its Run failed", session_id)
        result = RUN_LOST
    else:
        _store_run(session_id, alias, run)
        result = WATCHING
    if not _set(session_id, result, only_from) and result.state == "watching" and state_of(session_id).state in ("ending", "none"):
        # Its end may have reached the Detection Service before this start did,
        # and found no Run to end. (A Session already watching had a second
        # start, its create's and a tick's, answered with the same Run.)
        _end_run(session_id)


def _end_run(session_id: uuid.UUID) -> bool:
    """Whether the Detection Service answered that this end ended the Run: not
    when it could not be reached, or had no Run for the Session. Its answer
    moves the stored Run it names on to how far it watched (`_follow`); one
    never stored, the database down all its life, moves none."""
    try:
        ended = detection_client.end_run(session_id)
    except detection_client.DetectionServiceUnreachable as e:
        log.warning("The Run of session %s may not have ended: %s", session_id, e)
        return False
    if ended is None:
        return False
    with _lock:
        _watched.discard(session_id)
    db = SessionLocal()
    try:
        if ended.baseline_view is not None:   # none for a Run ended before it watched
            _follow(db, runs_repo.get_for_update(db, session_id, ended.baseline_view.taken_at), ended)
    except Exception as e:   # the Run did end: only what it reported is lost
        log.warning("How far the Run of session %s watched is not stored: %s", session_id, e, exc_info=True)
    finally:
        db.close()
    return True


@contextmanager
def ending(session: Session) -> Iterator[None]:
    """Ends the active Session's Run, if it has a camera or had one when its
    Run was asked for, before the block runs, which completes or deletes the
    Session: `ending` from the start of the end until the block has committed
    that, so no tick starts the Session a Run in between, while the Run
    judges the Candidates it has open and posts what persisted. Then `none`.
    A Detection Service that cannot be reached, or does not answer within
    END_TIMEOUT_S, is logged, and the Session ends anyway. So does one whose
    Run is already gone. It then reads `end_unconfirmed` if a Run watched it
    since its Run's end was last confirmed, even if it reads not watching by
    now: its last Bullet Holes may be missing. A block that fails before it
    commits leaves the Session active, reading `none`, and the next tick
    watches it again; one that fails after is read as one that succeeded.

    ponytail: a deleted Session's `end_unconfirmed` stays in memory until
    the backend restarts, a few bytes for each; reconcile does not read the
    deleted ones apart from the completed ones"""
    if session.status != "active" or (session.camera_id is None and session.id not in _states):
        yield
        return
    # Read before the block: one that fails mid-flush leaves `session`
    # expired in a transaction to roll back, so reading its id afterwards
    # raises, and the Session would read `ending` for good
    session_id = session.id
    _set(session_id, Detection(state="ending"))
    confirmed = False
    try:
        # Whether a Run watched it is read by _set once the end is answered: a
        # start answered just before the end began, or a tick's end of the same
        # Run confirmed meanwhile, changes it.
        # ponytail: the Detection Service drops its Run before it answers that
        # tick's end, so this end's 404 can come first and read end_unconfirmed,
        # the safe way round. Waiting on an end of the same Run already under
        # way closes it if it ever matters
        confirmed = _end_run(session_id)
        yield
    except BaseException:
        _set(session_id, NONE if confirmed or _still_active(session_id) else END_UNCONFIRMED)
        raise
    _set(session_id, NONE if confirmed else END_UNCONFIRMED)


def _still_active(session_id: uuid.UUID) -> bool:
    """Whether the Session is active in the database: a block that failed may
    have committed its end first. Not known reads not active, so a Session
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
    """The Session is active again: its last end not being confirmed no longer
    stands, and reconcile watches it again from a fresh baseline."""
    _set(session_id, NONE, only_from=("end_unconfirmed",))


def reconcile(db: DBSession) -> None:
    """One round of keeping the Detection Service's Run on the Session that
    should hold it: the active Session, one at a time (uq_sessions_one_active),
    while its camera is enabled. A Run of any other Session is ended, one
    left by a Session completed while the service could not be told, and the
    active Session's started if it has none. Every Session no longer active
    reads `none`, unless its end was not confirmed. A Session with a start or
    an end under way is left to it."""
    # Asked before the database is read: a Run is only started for a Session
    # already committed, so the Session of the Run it reports is read below
    try:
        run, answered = detection_client.status(), True
    except detection_client.DetectionServiceUnreachable:
        run, answered = None, False
    cameras = {c.id: c for c in cameras_repo.list_all(db)}
    active = sessions_repo.list_active(db)
    active_ids = {s.id for s in active}
    with _lock:
        ended = [session_id for session_id in _states if session_id not in active_ids]
        stuck = [(session_id, detection.state) for session_id, detection in _states.items()
                 if detection.state == "starting" and time.monotonic() - _since.get(session_id, time.monotonic()) > STUCK_S]
    for session_id, state in stuck:
        log.warning("Session %s read %s for over %ss: letting it go", session_id, state, STUCK_S)
        _set(session_id, NONE if session_id in active_ids else END_UNCONFIRMED, only_from=(state,))
    for session_id in ended:
        # Left by a start that raced its Session's end
        _set(session_id, NONE, only_from=IDLE)
    session = active[0] if active else None
    camera = cameras.get(session.camera_id) if session and session.camera_id else None
    wanted = session if camera is not None and camera.enabled else None
    # A Session whose camera was deleted has none, but read something other
    # than `none` while it had one
    if session and wanted is None and (session.camera_id is not None or state_of(session.id) != NONE):
        _set(session.id, CAMERA_DISABLED, only_from=IDLE)
    if not answered:
        if wanted:
            _set(wanted.id, SERVICE_DOWN, only_from=IDLE)
        return

    if run and run.state != "ending" and (wanted is None or run.session_id != wanted.id):
        # Its Session completed or was deleted while the Detection Service
        # could not be told, or its camera was disabled or deleted
        log.info("Ending the Run of session %s: it is no longer the one to watch", run.session_id)
        _end_run(run.session_id)
        run = None
    if wanted is None:
        return

    current = state_of(wanted.id).state
    if current not in IDLE or (run and run.state == "ending"):
        return   # a start or an end is under way
    if run and run.state == "watching":
        # Unknown since the backend restarted, or its start not answered to it
        _store_run(wanted.id, camera.alias, run)
        _set(wanted.id, WATCHING, only_from=IDLE)
        return
    if current == "none":
        # Reopened, or not asked for since the backend restarted. A Session
        # being completed or deleted reads `ending` until that is committed
        shown = Detection(state="starting")
    elif current == "watching":
        shown = RUN_LOST
    else:
        shown = state_of(wanted.id)   # retried, still not watching
    if not _set(wanted.id, shown, only_from=(current,)):
        return   # its end began meanwhile
    log.info("Session %s has no Run watching it: starting one", wanted.id)
    watch(wanted.id, camera.alias, only_from=(shown.state,))


def _reconcile_once() -> None:
    db = SessionLocal()
    try:
        reconcile(db)
    finally:
        db.close()


async def run_forever() -> None:
    """The reconcile loop, started with the app (main.py) beside the camera
    sync loop and as often. A round waits for the Run it starts or ends, so
    rounds are camera_sync_interval_s apart rather than that often. Logs only
    when its state changes, not on every failed attempt."""
    failing = False
    while True:
        try:
            await run_in_threadpool(_reconcile_once)
            if failing:
                log.info("Reconciling the Detection Service's Run restored")
            failing = False
        except Exception as e:  # keep the loop alive whatever one attempt hits
            if not failing:
                log.warning("Reconciling the Detection Service's Run failing, retrying every %ss: %s",
                            settings.camera_sync_interval_s, e)
            failing = True
        await asyncio.sleep(settings.camera_sync_interval_s)
