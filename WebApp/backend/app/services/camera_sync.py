"""Keeps MediaMTX's camera paths matching the cameras table.

Each enabled camera is a MediaMTX path named after its alias, which runs
VideoService's run_record.sh: GStreamer joins the camera's multicast group and
publishes the stream to MediaMTX as RTSP, as KanatFrontend set it up. A
disabled camera keeps its path without the script, because MediaMTX's playback
server only plays recordings of a configured path. Paths
added through the Control API live only in MediaMTX's memory, so they are
re-applied when the backend starts and every camera_sync_interval_s after.

Recording follows the Sessions: the cameras record while an active Session has
`record` on, and stop when none has.
"""
import asyncio
import logging
import threading
import time

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session as DBSession

from app.config.settings import settings
from app.core.database import SessionLocal
from app.models import Camera
from app.repositories import cameras as cameras_repo
from app.repositories import sessions as sessions_repo
from app.services import cameras, mediamtx, recordings

log = logging.getLogger(__name__)

# As KanatFrontend recorded: fMP4 in 10-minute files, deleted after a day.
# Durations are written the way MediaMTX reports them back ("10m" reads back as
# "10m0s"), so an unchanged path compares equal and is left alone.
RECORDING = {
    "recordPath": "./recordings/%path/%Y-%m-%d_%H-%M-%S-%f",
    "recordFormat": "fmp4",
    "recordPartDuration": "2s",
    "recordSegmentDuration": "10m0s",
    "recordDeleteAfter": "1d",
}

_RECORD_SCRIPT = "./run_record.sh"

_lock = threading.Lock()
# The loop's clock. It counts from an arbitrary start (on Linux, the boot), so
# the loop never compares it with a fixed time
_clock = time.monotonic
# Aliases already reported as clashing with a mediamtx.yml path, so the sync
# loop logs each once rather than every round
_conflicts: set[str] = set()
# Whether the sync last found mediamtx.yml unknown, so that is logged once
_config_unknown = False


def path_config(camera: Camera, record: bool) -> dict:
    """The camera's MediaMTX path, as KanatFrontend's makePathDTO built it."""
    # MediaMTX substitutes ${RTSP_PORT} with its own RTSP port when it runs the
    # command; every interpolated value is held to safe characters by
    # schemas/camera.py
    rtsp_url = f"rtsp://127.0.0.1:${{RTSP_PORT}}/{camera.alias}"
    iface_arg = f' --iface "{camera.iface}"' if camera.iface else ""
    run_on_init = (
        "bash -lc '\n"
        f'exec {_RECORD_SCRIPT} --mcast-ip "{camera.mcast_ip}" --mcast-port "{camera.mcast_port}"'
        f' --rtsp-url "{rtsp_url}"{iface_arg}\n'
        "'"
    )
    return {
        "source": "publisher",
        "sourceOnDemand": False,
        "overridePublisher": True,
        "runOnInit": run_on_init,
        "runOnInitRestart": True,
        "record": record,
        **RECORDING,
    }


def playback_only_config() -> dict:
    """A disabled camera's path: nothing runs or records on it, and its
    recordings stay playable."""
    return {
        "source": "publisher",
        "sourceOnDemand": False,
        "overridePublisher": True,
        "runOnInit": "",
        "runOnInitRestart": False,
        "record": False,
        **RECORDING,
    }


def is_camera_path(name: str, config: dict, config_paths: mediamtx.ConfigPaths | None) -> bool:
    """Whether a path is one of the cameras', which the sync may patch and
    delete. A path mediamtx.yml defines never is, whatever its settings. Of the
    rest, a camera's path runs run_record.sh, or (disabled) is the playback-only
    path; without mediamtx.yml's paths, only the first counts."""
    if _RECORD_SCRIPT in (config.get("runOnInit") or ""):
        return config_paths is None or not config_paths.defines(name)
    if config_paths is None or config_paths.defines(name):
        return False
    return all(config.get(key) == value for key, value in playback_only_config().items())


def taken_by_config(alias: str) -> bool:
    """Whether a path of that name belongs to MediaMTX itself (e.g. loopdemo, or
    a name a ~regular expression in mediamtx.yml matches): a camera of that
    name would overwrite or shadow it, and deleting the camera delete it. False
    when neither mediamtx.yml nor MediaMTX says so; the sync never touches such
    paths anyway."""
    config_paths = mediamtx.config_paths()
    if config_paths is not None and config_paths.defines(alias):
        return True
    try:
        config = mediamtx.list_path_configs().get(alias)
    except mediamtx.MediaMTXUnreachable:
        return False
    return config is not None and not is_camera_path(alias, config, config_paths)


def sync(db: DBSession) -> None:
    """Make MediaMTX's camera paths match the database. Changes nothing while
    mediamtx.yml is unknown (unreadable, or a regular expression not trusted):
    MediaMTX lists a ~regexp path under its key, not the names it covers, so
    any name might be its. Raises MediaMTXUnreachable if it cannot be reached."""
    global _config_unknown
    with _lock:
        record = sessions_repo.recording_session_active(db)
        wanted = {
            c.alias: path_config(c, record) if c.enabled else playback_only_config()
            for c in cameras_repo.list_all(db)
        }
        current = mediamtx.list_path_configs()
        config_paths = mediamtx.config_paths()
        if config_paths is None:
            if not _config_unknown:
                log.warning("mediamtx.yml unreadable or not understood (MEDIAMTX_CONFIG?): cameras are not applied to MediaMTX")
                _config_unknown = True
            return
        if _config_unknown:
            log.info("mediamtx.yml read again: cameras are applied to MediaMTX")
            _config_unknown = False

        for name, config in wanted.items():
            existing = current.get(name)
            if config_paths.defines(name) or (existing is not None and not is_camera_path(name, existing, config_paths)):
                # mediamtx.yml owns this name (the API refuses it, but a camera
                # can get it while MediaMTX was down or the YAML changes later):
                # adding or patching would turn the static path, or the name
                # its ~regular expression covers, into this camera, and
                # deleting the camera would then remove it
                if name not in _conflicts:
                    log.warning("Camera '%s' is not applied: mediamtx.yml has a path of that name", name)
                    _conflicts.add(name)
                continue
            if existing is None:
                mediamtx.add_path(name, config)
                continue
            changed = {key: value for key, value in config.items() if existing.get(key) != value}
            if changed:
                mediamtx.patch_path(name, changed)

        for name, existing in current.items():
            if name not in wanted and is_camera_path(name, existing, config_paths):
                mediamtx.delete_path(name)


def sync_soon(db: DBSession) -> None:
    """Sync after a change, without failing the request when MediaMTX is down:
    the sync loop applies it once MediaMTX is back."""
    try:
        sync(db)
    except mediamtx.MediaMTXUnreachable as e:
        log.warning("MediaMTX not updated now, the sync loop will retry: %s", e)


def _sync_once() -> None:
    db = SessionLocal()
    try:
        sync(db)
        aliases = [c.alias for c in cameras_repo.list_all(db)]
    finally:
        db.close()
    cameras.watch_traffic()
    recordings.remove_unused_recordings(aliases)


async def run_forever() -> None:
    """The sync loop, started with the app (main.py). Logs only when its state
    changes, not on every failed attempt. Every CACHE_CLEAN_INTERVAL_S it also
    cleans the replay cache."""
    failing = False
    cleaned_at: float | None = None  # first round cleans, whatever the clock reads
    while True:
        if cleaned_at is None or _clock() - cleaned_at >= recordings.CACHE_CLEAN_INTERVAL_S:
            try:
                await run_in_threadpool(recordings.clean_cache)
            except OSError as e:
                log.warning("Cleaning the replay cache failed: %s", e)
            cleaned_at = _clock()
        try:
            await run_in_threadpool(_sync_once)
            if failing:
                log.info("Camera sync with MediaMTX restored")
            failing = False
        except Exception as e:  # keep the loop alive whatever one attempt hits
            if not failing:
                log.warning("Camera sync with MediaMTX failing, retrying every %ss: %s", settings.camera_sync_interval_s, e)
            failing = True
        await asyncio.sleep(settings.camera_sync_interval_s)
