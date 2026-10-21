import logging
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.config.settings import settings
from app.models import Camera
from app.schemas.recording import CameraRecording, RecordingSpan
from app.services import mediamtx

log = logging.getLogger(__name__)

# A long unbroken recording is offered in parts of at most this long, so one
# part is a few hundred MB at most; the player runs each part into the next
MAX_PART_S = 600

# MediaMTX deletes a recording a day after it was made (RECORDING's
# recordDeleteAfter in camera_sync.py); its replay copies go with it
CACHE_MAX_AGE_S = 24 * 3600
# A half-written download older than this was abandoned
PARTIAL_MAX_AGE_S = 3600
# How often the camera sync loop cleans the replay cache
CACHE_CLEAN_INTERVAL_S = 600
# A copy served within this long is still being played (the player asks for
# its ranges as it goes), so the cache limit does not remove it
IN_USE_S = 15 * 60


def _parts(start: datetime, end: datetime) -> list[RecordingSpan]:
    parts = []
    while start < end:
        part_end = min(start + timedelta(seconds=MAX_PART_S), end)
        parts.append(RecordingSpan(start=start, duration_s=(part_end - start).total_seconds()))
        start = part_end
    return parts


def session_recordings(windows: list[tuple[datetime, datetime]], cameras: list[Camera]) -> list[CameraRecording]:
    """Each camera's recorded parts within the windows a Session recorded, cut
    to them: another Session recording at the same time does not show here.
    MediaMTX deletes recordings after a day, so any camera may have none."""
    out = []
    for camera in cameras:
        spans = []
        for start, end in windows:
            for item in mediamtx.list_recordings(camera.alias, start, end):
                span_start = datetime.fromisoformat(item["start"])
                span_end = span_start + timedelta(seconds=item["duration"])
                spans += _parts(max(span_start, start), min(span_end, end))
        if spans:
            out.append(CameraRecording(alias=camera.alias, spans=sorted(spans, key=lambda s: s.start)))
    return out


def is_listed_part(
    windows: list[tuple[datetime, datetime]], cameras: list[Camera], alias: str, start: datetime, duration_s: float
) -> bool:
    """Whether (alias, start, duration_s) is one of the parts session_recordings
    lists for these windows and cameras: the only video a Session may replay,
    so no other path, nor another stretch of the same one, can be fetched
    through it."""
    for recording in session_recordings(windows, [c for c in cameras if c.alias == alias]):
        for span in recording.spans:
            if abs((span.start - start).total_seconds()) < 0.001 and abs(span.duration_s - duration_s) < 0.001:
                return True
    return False


# --- replay files ---
#
# The playback server streams a recording without a length and cannot serve a
# byte range, so a <video> playing it straight cannot seek, and misreads its
# duration. Each part is therefore fetched once into a file, which is served
# with range support.

# A part's lock and how many requests are using it: an entry exists only while
# someone holds or waits for it, so the registry stays as small as the
# downloads in progress, and deletion only looks at those
_locks: dict[Path, list] = {}  # path -> [Lock, users]
_locks_guard = threading.Lock()
# Copies being played: path -> time.monotonic() until which it counts as in use
_in_use: dict[Path, float] = {}


class PartWithdrawn(Exception):
    """The part's session was deleted after the request was authorised."""


def _cache_dir() -> Path:
    if settings.replay_cache_dir:
        path = Path(settings.replay_cache_dir)
    elif (recordings := _recordings_dir()) is not None:
        # On disk beside the recordings, not in a temp folder that may live in RAM
        path = recordings.parent / "replay-cache"
    else:
        path = Path(tempfile.gettempdir()) / "kanat-replay"
    path.mkdir(parents=True, exist_ok=True)
    return path


# A replay copy is named <alias>_<recording start in UTC>_<seconds>.mp4
_CACHE_STAMP = "%Y%m%dT%H%M%S%fZ"


def _cache_name(alias: str, start: datetime, duration_s: float) -> str:
    return f"{alias}_{start.astimezone(timezone.utc).strftime(_CACHE_STAMP)}_{duration_s:.3f}.mp4"


def _read_cache_name(file: Path) -> tuple[str, datetime, float] | None:
    """The alias, recording start and length a replay copy's name holds."""
    head, _, seconds = file.stem.rpartition("_")
    alias, _, stamp = head.rpartition("_")
    try:
        start = datetime.strptime(stamp, _CACHE_STAMP).replace(tzinfo=timezone.utc)
        return alias, start, float(seconds)
    except ValueError:
        return None


def _mark_in_use(path: Path) -> None:
    with _locks_guard:
        _in_use[path] = time.monotonic() + IN_USE_S


def _forget_finished_plays() -> None:
    """Drops the marks of copies not served within IN_USE_S."""
    now = time.monotonic()
    with _locks_guard:
        for path in [p for p, until in _in_use.items() if until <= now]:
            del _in_use[path]


def _unlink_unless_in_use(file: Path) -> bool:
    """Removes the copy unless it is being played. Checked and removed under
    the lock _mark_in_use takes, so a request that marks it while the cache is
    pruned either finds it gone (and fetches it again) or keeps it."""
    with _locks_guard:
        if _in_use.get(file, 0) > time.monotonic():
            return False
        file.unlink(missing_ok=True)
        return True


def _prune_cache(directory: Path) -> None:
    """Drops the copies whose recording is over a day old (MediaMTX has deleted
    the original by then), abandoned downloads, and the least recently played
    copies beyond replay_cache_max_gb, but never one still being played, even
    if those alone are over the limit: concurrent players each keep their part.
    An expired copy being played goes once it is no longer played. A copy's
    mtime is when it was last played (replay_file touches it)."""
    _forget_finished_plays()
    now = time.time()
    expired = datetime.now(timezone.utc) - timedelta(seconds=CACHE_MAX_AGE_S)
    kept = []
    for file in directory.iterdir():
        try:
            stat = file.stat()
            if file.suffix == ".part":
                if now - stat.st_mtime > PARTIAL_MAX_AGE_S:
                    file.unlink()
            elif file.suffix == ".mp4":
                named = _read_cache_name(file)
                # A name that cannot be read: its age by the time it was written
                too_old = named[1] < expired if named else now - stat.st_mtime > CACHE_MAX_AGE_S
                if too_old:
                    _unlink_unless_in_use(file)
                else:
                    kept.append((stat.st_mtime, stat.st_size, file))
        except FileNotFoundError:
            pass  # another request removed it first

    budget = settings.replay_cache_max_gb * 1024**3
    total = sum(size for _, size, _ in kept)
    for _, size, file in sorted(kept):
        if total <= budget:
            break
        if _unlink_unless_in_use(file):
            total -= size


def clean_cache() -> None:
    """The camera sync loop's cleaning of the replay cache, so copies go with
    their recordings even when nothing is replayed."""
    _prune_cache(_cache_dir())


@contextmanager
def _part_lock(path: Path) -> Iterator[None]:
    """Holds the part's lock: its download holds it from start to finish, and
    deleting the part takes it too, so neither overtakes the other. The entry
    is dropped when its last user leaves."""
    with _locks_guard:
        entry = _locks.setdefault(path, [threading.Lock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _locks_guard:
            entry[1] -= 1
            if entry[1] == 0 and _locks.get(path) is entry:
                del _locks[path]


def replay_file(alias: str, start: datetime, duration_s: float, still_allowed: Callable[[], bool]) -> Path:
    """The part as an MP4 file, fetched from the playback server the first time.

    still_allowed is asked once the part's lock is held, and must read the
    database afresh (e.g. that the session still exists). Deletion commits
    before it looks at the locks in use, so a request either holds its lock
    when deletion looks, and deletion waits and removes its result, or takes it
    after, and sees the deletion here. Raises PartWithdrawn then, and
    MediaMTXUnreachable if the part cannot be fetched."""
    directory = _cache_dir()
    path = directory / _cache_name(alias, start, duration_s)

    # The player asks for several ranges at once; one request fetches the file,
    # the others wait for it
    with _part_lock(path):
        if not still_allowed():
            raise PartWithdrawn(path.name)
        # Each of the player's requests renews it, so no other request's
        # pruning removes it while it is read
        _mark_in_use(path)
        if path.exists():
            path.touch()  # played again: keep it over parts not played lately
        else:
            _prune_cache(directory)
            partial = path.with_suffix(".part")
            video = mediamtx.open_recording(alias, start, duration_s)
            try:
                with open(partial, "wb") as out:
                    for chunk in video.iter_bytes():
                        out.write(chunk)
            except httpx.HTTPError as e:
                # MediaMTX stopped or stalled mid-download: nothing half-written is kept
                partial.unlink(missing_ok=True)
                raise mediamtx.MediaMTXUnreachable(f"playback get {alias}: {e}") from e
            finally:
                video.close()
            partial.replace(path)
            _prune_cache(directory)  # keep the total within the limit with this one in
    return path


# --- deleting a Session's video ---
#
# MediaMTX names each file after the moment it started recording, in this PC's
# local time (RECORDING's recordPath in camera_sync.py), and last writes it
# when that file ends, at most a segment later. Recording only runs while some
# Session records, so a Session's files are the ones that started within its
# recording intervals; one that runs on into another Session's intervals is
# kept for it.

_RECORDING_NAME = "%Y-%m-%d_%H-%M-%S-%f"
SEGMENT = timedelta(minutes=10)  # RECORDING's recordSegmentDuration


def _recordings_dir() -> Path | None:
    """VideoService/recordings in this repo, unless settings.recordings_dir
    says otherwise; None when it cannot be found (e.g. inside a container)."""
    if settings.recordings_dir:
        return Path(settings.recordings_dir)
    parents = Path(__file__).resolve().parents
    # app/services/recordings.py -> KanatBackend/
    return parents[4] / "VideoService" / "recordings" if len(parents) > 4 else None


def _file_start(file: Path) -> datetime | None:
    try:
        local = datetime.strptime(file.stem, _RECORDING_NAME)
    except ValueError:
        return None
    first, second = local.replace(fold=0).astimezone(), local.replace(fold=1).astimezone()
    if first == second:
        return first
    # The hour repeated when daylight saving time ends: a file is written after
    # it starts, so the later reading that is not after its last write is it
    try:
        written = datetime.fromtimestamp(file.stat().st_mtime).astimezone()
    except FileNotFoundError:
        return None
    return second if second <= written else first


def _camera_folders(root: Path) -> list[Path]:
    """The recording folders of every camera that recorded, present or past:
    all of them except those of the paths mediamtx.yml defines, which MediaMTX
    keeps and expires itself. Empty when mediamtx.yml cannot be read: which
    folders are MediaMTX's own is then unknown, so none is touched."""
    config_names = mediamtx.config_path_names()
    if config_names is None:
        log.warning("mediamtx.yml unreadable (MEDIAMTX_CONFIG?): no recording folder is cleaned or deleted")
        return []
    return [folder for folder in root.iterdir() if folder.is_dir() and folder.name not in config_names]


def remove_unused_recordings(aliases: list[str]) -> int:
    """Deletes day-old recordings in folders no camera uses any more (a deleted
    camera): MediaMTX only expires the recordings of paths it still has. Returns how many files were deleted."""
    root = _recordings_dir()
    if root is None or not root.is_dir():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=CACHE_MAX_AGE_S)
    deleted = 0
    for folder in _camera_folders(root):
        if folder.name in aliases:
            continue
        for file in folder.glob("*.mp4"):
            began = _file_start(file)
            if began is not None and began < cutoff:
                file.unlink(missing_ok=True)
                deleted += 1
        if not any(folder.iterdir()):
            folder.rmdir()
    return deleted


def _file_end(file: Path, began: datetime) -> datetime:
    """When the recording ended: its last write, at most a segment after it
    began (a file still being written ends now)."""
    try:
        written = datetime.fromtimestamp(file.stat().st_mtime).astimezone()
    except FileNotFoundError:
        written = began
    return min(max(written, began), began + SEGMENT)


def delete_session_video(
    windows: list[tuple[datetime, datetime]],
    other_windows: list[tuple[datetime, datetime]],
) -> int:
    """Deletes the recordings that started within the windows a Session
    recorded, and their replay copies, keeping any that runs on into what
    another Session recorded. Every camera's folder counts, including those of
    cameras since deleted. Returns how many recordings were deleted."""

    def belongs(began: datetime, ended: datetime) -> bool:
        """Overlaps what this Session recorded, and nothing a remaining Session
        recorded: a segment two Sessions shared goes with the last of them."""
        return any(began < e and s < ended for s, e in windows) and not any(
            began < e and s < ended for s, e in other_windows
        )

    deleted = 0
    root = _recordings_dir()
    if root is None:
        log.warning("Recordings folder not found; set RECORDINGS_DIR to delete a Session's video")
    for folder in _camera_folders(root) if root and root.is_dir() else []:
        for file in folder.glob("*.mp4"):
            began = _file_start(file)
            if began is not None and belongs(began, _file_end(file, began)):
                file.unlink(missing_ok=True)
                deleted += 1

    # Replay copies: finished ones, half-written ones, and downloads just begun
    # (known only by their lock). Each is deleted under its download lock, so a
    # download in progress finishes first and its result goes too.
    # The caller has committed the session's deletion before this, so a replay
    # whose lock is not in _locks yet will see the deletion (replay_file)
    cache = _cache_dir()
    with _locks_guard:
        downloading = list(_locks)
    copies = {f.with_suffix(".mp4") for f in [*cache.glob("*.mp4"), *cache.glob("*.part"), *downloading]}
    for copy in copies:
        named = _read_cache_name(copy)
        if named is None:
            continue
        _, began, length_s = named
        if belongs(began, began + timedelta(seconds=length_s)):
            with _part_lock(copy):
                copy.unlink(missing_ok=True)
                copy.with_suffix(".part").unlink(missing_ok=True)
    return deleted
