"""Keeps MediaMTX's camera paths matching the cameras table.

Each enabled camera is a MediaMTX path named after its alias, which runs
VideoService's run_record.sh: GStreamer joins the camera's multicast group and
publishes the stream to MediaMTX as RTSP, as KanatFrontend set it up. Paths
added through the Control API live only in MediaMTX's memory, so they are
re-applied when the backend starts and every camera_sync_interval_s after.
"""
import asyncio
import logging
import threading

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session as DBSession

from app.config.settings import settings
from app.core.database import SessionLocal
from app.models import Camera
from app.repositories import cameras as cameras_repo
from app.services import cameras, mediamtx

log = logging.getLogger(__name__)

_RECORD_SCRIPT = "./run_record.sh"

_lock = threading.Lock()
# Aliases already reported as clashing with a mediamtx.yml path, so the sync
# loop logs each once rather than every round
_conflicts: set[str] = set()


def path_config(camera: Camera) -> dict:
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
    }


def is_camera_path(config: dict) -> bool:
    """Whether a path is one of the cameras' (it runs run_record.sh), so paths
    from mediamtx.yml are never deleted."""
    return _RECORD_SCRIPT in (config.get("runOnInit") or "")


def taken_by_config(alias: str) -> bool:
    """Whether a path of that name comes from mediamtx.yml (e.g. loopdemo): a
    camera of that name would overwrite it, and deleting the camera delete it.
    False when MediaMTX cannot be asked; the sync never deletes such paths."""
    try:
        config = mediamtx.list_path_configs().get(alias)
    except mediamtx.MediaMTXUnreachable:
        return False
    return config is not None and not is_camera_path(config)


def sync(db: DBSession) -> None:
    """Make MediaMTX's camera paths match the database. Raises
    MediaMTXUnreachable if it cannot be reached."""
    with _lock:
        wanted = {c.alias: path_config(c) for c in cameras_repo.list_all(db) if c.enabled}
        current = mediamtx.list_path_configs()

        for name, config in wanted.items():
            existing = current.get(name)
            if existing is None:
                mediamtx.add_path(name, config)
                continue
            if not is_camera_path(existing):
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
            if name not in wanted and is_camera_path(existing):
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
    finally:
        db.close()
    cameras.watch_traffic()


async def run_forever() -> None:
    """The sync loop, started with the app (main.py). Logs only when its state
    changes, not on every failed attempt."""
    failing = False
    while True:
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
