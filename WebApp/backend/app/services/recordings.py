import logging
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.config.settings import settings
from app.models import Camera, Session
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


def session_window(session: Session) -> tuple[datetime, datetime]:
    return session.started_at, session.ended_at or datetime.now(timezone.utc)


def _parts(start: datetime, end: datetime) -> list[RecordingSpan]:
    parts = []
    while start < end:
        part_end = min(start + timedelta(seconds=MAX_PART_S), end)
        parts.append(RecordingSpan(start=start, duration_s=(part_end - start).total_seconds()))
        start = part_end
    return parts


def session_recordings(session: Session, cameras: list[Camera]) -> list[CameraRecording]:
    """Each camera's recorded parts within the Session, cut to its start and
    end. Recording may have been switched on for only part of it, and MediaMTX
    deletes recordings after a day, so any camera may have none."""
    start, end = session_window(session)
    out = []
    for camera in cameras:
        spans = []
        for item in mediamtx.list_recordings(camera.alias, start, end):
            span_start = datetime.fromisoformat(item["start"])
            span_end = span_start + timedelta(seconds=item["duration"])
            spans += _parts(max(span_start, start), min(span_end, end))
        if spans:
            out.append(CameraRecording(alias=camera.alias, spans=spans))
    return out


# --- replay files ---
#
# The playback server streams a recording without a length and cannot serve a
# byte range, so a <video> playing it straight cannot seek, and misreads its
# duration. Each part is therefore fetched once into a file, which is served
# with range support.

_locks: dict[Path, threading.Lock] = {}
_locks_guard = threading.Lock()


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


def _prune_cache(directory: Path) -> None:
    """Drops the copies whose recording is over a day old (MediaMTX has deleted
    the original by then), abandoned downloads, and the least recently played
    copies beyond replay_cache_max_gb. A copy's mtime is when it was last
    played (replay_file touches it)."""
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
                    file.unlink()
                else:
                    kept.append((stat.st_mtime, stat.st_size, file))
        except FileNotFoundError:
            pass  # another request removed it first

    budget = settings.replay_cache_max_gb * 1024**3
    total = sum(size for _, size, _ in kept)
    for _, size, file in sorted(kept):
        if total <= budget:
            break
        file.unlink(missing_ok=True)
        total -= size


def clean_cache() -> None:
    """The camera sync loop's cleaning of the replay cache, so copies go with
    their recordings even when nothing is replayed."""
    _prune_cache(_cache_dir())


def replay_file(alias: str, start: datetime, duration_s: float) -> Path:
    """The part as an MP4 file, fetched from the playback server the first time.
    Raises MediaMTXUnreachable if it cannot be fetched."""
    directory = _cache_dir()
    path = directory / _cache_name(alias, start, duration_s)

    with _locks_guard:
        lock = _locks.setdefault(path, threading.Lock())
    # The player asks for several ranges at once; one request fetches the file,
    # the others wait for it
    with lock:
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
# local time (RECORDING's recordPath in camera_sync.py), and a file runs until
# the next one starts, at most a segment long. Recording only runs while a
# recording Session is active, so a Session's files are the ones that started
# during it; one that runs on into another Session's time is kept for it.

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


def remove_unused_recordings(aliases: list[str]) -> int:
    """Deletes day-old recordings in folders no camera uses any more (a deleted
    or renamed camera): MediaMTX only expires the recordings of paths it still
    has. Returns how many files were deleted."""
    root = _recordings_dir()
    if root is None or not root.is_dir():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=CACHE_MAX_AGE_S)
    deleted = 0
    for folder in root.iterdir():
        if not folder.is_dir() or folder.name in aliases:
            continue
        for file in folder.glob("*.mp4"):
            began = _file_start(file)
            if began is not None and began < cutoff:
                file.unlink(missing_ok=True)
                deleted += 1
        if not any(folder.iterdir()):
            folder.rmdir()
    return deleted


def delete_session_video(
    window: tuple[datetime, datetime],
    aliases: list[str],
    other_windows: list[tuple[datetime, datetime]],
) -> int:
    """Deletes the recordings that started within `window`, and their replay
    copies, keeping any that also falls in another Session's window. Returns
    how many recordings were deleted."""
    start, end = window

    def belongs(began: datetime, ended: datetime) -> bool:
        """Started in this Session, and overlaps no other Session's time."""
        return start <= began <= end and not any(began < e and s < ended for s, e in other_windows)

    deleted = 0
    root = _recordings_dir()
    if root is None:
        log.warning("Recordings folder not found; set RECORDINGS_DIR to delete a Session's video")
    for alias in aliases if root else []:
        folder = root / alias
        if not folder.is_dir():
            continue
        files = sorted((began, file) for file in folder.glob("*.mp4") if (began := _file_start(file)))
        for i, (began, file) in enumerate(files):
            ended = min(files[i + 1][0], began + SEGMENT) if i + 1 < len(files) else began + SEGMENT
            if belongs(began, ended):
                file.unlink(missing_ok=True)
                deleted += 1

    cache = _cache_dir()
    for alias in aliases:
        for file in cache.glob(f"{alias}_*.mp4"):
            named = _read_cache_name(file)
            # The alias must match whole: "cam1" must not catch camera "cam1_x"
            if named is None or named[0] != alias:
                continue
            _, began, length_s = named
            if belongs(began, began + timedelta(seconds=length_s)):
                file.unlink(missing_ok=True)
    return deleted
