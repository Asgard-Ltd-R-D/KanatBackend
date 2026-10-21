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


def is_camera_path(name: str, config: dict, config_names: set[str] | None) -> bool:
    """Whether a path is one of the cameras', which the sync may patch and
    delete. A path mediamtx.yml defines never is, whatever its settings. Of the
    rest, a camera's path runs run_record.sh, or (disabled) is the playback-only
    path; without mediamtx.yml's names, only the first counts."""
    if _RECORD_SCRIPT in (config.get("runOnInit") or ""):
        return config_names is None or name not in config_names
    if config_names is None or name in config_names:
        return False
    return all(config.get(key) == value for key, value in playback_only_config().items())


def taken_by_config(alias: str) -> bool:
    """Whether a path of that name belongs to MediaMTX itself (e.g. loopdemo in
    mediamtx.yml): a camera of that name would overwrite it, and deleting the
    camera delete it. False when neither mediamtx.yml nor MediaMTX says so; the
    sync never touches such paths anyway."""
    config_names = mediamtx.config_path_names()
    if config_names is not None and alias in config_names:
        return True
    try:
        config = mediamtx.list_path_configs().get(alias)
    except mediamtx.MediaMTXUnreachable:
        return False
    return config is not None and not is_camera_path(alias, config, config_names)


def sync(db: DBSession) -> None:
    """Make MediaMTX's camera paths match the database. Raises
    MediaMTXUnreachable if it cannot be reached."""
    with _lock:
        record = sessions_repo.recording_session_active(db)
        wanted = {
            c.alias: path_config(c, record) if c.enabled else playback_only_config()
            for c in cameras_repo.list_all(db)
        }
        current = mediamtx.list_path_configs()
        config_names = mediamtx.config_path_names()

        for name, config in wanted.items():
            existing = current.get(name)
            if existing is None:
                mediamtx.add_path(name, config)
                continue
            if not is_camera_path(name, existing, config_names):
                # mediamtx.yml owns this name (the API refuses it, but a camera
                # can get it while MediaMTX was down or the YAML changes later):
                # patching would turn the static path into this camera, and
                # deleting the camera would then remove it
                if name not in _conflicts:
                    log.warning("Camera '%s' is not applied: mediamtx.yml has a path of that name", name)
                    _conflicts.add(name)
                continue
            changed = {key: value for key, value in config.items() if existing.get(key) != value}
            if changed:
                mediamtx.patch_path(name, changed)

        for name, existing in current.items():
            if name not in wanted and is_camera_path(name, existing, config_names):
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
