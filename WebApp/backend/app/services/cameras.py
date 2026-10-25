import logging
import threading
import time
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.models import Camera
from app.repositories import cameras as repo
from app.schemas.camera import CameraInput, CameraResponse
from app.services import mediamtx

log = logging.getLogger(__name__)


def get_camera_or_404(camera_id: uuid.UUID, db: DBSession) -> Camera:
    camera = repo.get(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


def list_cameras(db: DBSession) -> list[Camera]:
    return repo.list_all(db)


# A path stays "ready" after its camera stops sending, because GStreamer keeps
# its RTSP session open; only the path's inbound bytes still growing show video
# is arriving. Each path's counter is remembered with when it last grew.
STALE_S = 10
_traffic: dict[str, tuple[int, float | None]] = {}
_traffic_lock = threading.Lock()
# The paths the sync loop last saw video arriving on, so a change is logged once
_arriving: set[str] = set()


def receiving(paths: dict[str, dict]) -> set[str]:
    """The paths whose inbound bytes grew in the last STALE_S. Needs two looks
    at a path before it can say yes; the sync loop keeps looking."""
    now = time.monotonic()
    live = set()
    with _traffic_lock:
        for name in list(_traffic):
            if name not in paths:
                del _traffic[name]
        for name, path in paths.items():
            inbound = path.get("inboundBytes", 0) if path.get("ready") else 0
            previous = _traffic.get(name)
            if previous is None:
                _traffic[name] = (inbound, None)
            elif inbound > previous[0]:
                _traffic[name] = (inbound, now)
                live.add(name)
            else:
                _traffic[name] = (inbound, previous[1])
                if previous[1] is not None and now - previous[1] < STALE_S:
                    live.add(name)
    return live


def watch_traffic() -> None:
    """Takes a look at every path's counter (camera_sync's loop), so a status
    asked for later already has something to compare with, and logs each
    camera whose video starts or stops arriving."""
    global _arriving
    live = receiving(mediamtx.path_states())
    for path in sorted(live - _arriving):
        log.info("Video arriving from '%s'", path, extra={"camera": path})
    for path in sorted(_arriving - live):
        log.warning("Video stopped arriving from '%s'", path, extra={"camera": path, "stale_s": STALE_S})
    _arriving = live


def with_status(cameras: list[Camera]) -> list[CameraResponse]:
    """The cameras, each with whether video is arriving from it."""
    try:
        ready = receiving(mediamtx.path_states())
    except mediamtx.MediaMTXUnreachable:
        ready = None

    out = []
    for camera in cameras:
        item = CameraResponse.model_validate(camera)
        if not camera.enabled:
            item.status = "disabled"
        elif ready is None:
            item.status = "unreachable"
        else:
            item.status = "live" if camera.alias in ready else "no_signal"
        out.append(item)
    return out


def _fields(camera: Camera) -> dict:
    return {
        "camera": camera.alias, "mcast_ip": camera.mcast_ip, "mcast_port": camera.mcast_port,
        "iface": camera.iface, "enabled": camera.enabled,
    }


def _save(camera: Camera, body: CameraInput, db: DBSession) -> Camera:
    camera.alias = body.alias
    camera.mcast_ip = str(body.mcast_ip)
    camera.mcast_port = body.mcast_port
    camera.iface = body.iface
    camera.enabled = body.enabled
    try:
        return repo.save(db, camera)
    except repo.AliasTaken:
        raise HTTPException(status_code=409, detail=f"A camera named '{body.alias}' already exists")


def create_camera(body: CameraInput, db: DBSession) -> Camera:
    camera = _save(Camera(id=uuid.uuid4()), body, db)
    log.info("Camera '%s' added", camera.alias, extra=_fields(camera))
    return camera


def update_camera(camera_id: uuid.UUID, body: CameraInput, db: DBSession) -> Camera:
    camera = get_camera_or_404(camera_id, db)
    # The alias names the camera's stream (rtsp://.../<alias>, which the
    # detection model reads) and its recordings, which replay and session
    # deletion find by it: renaming would orphan both, so it cannot change
    if body.alias != camera.alias:
        raise HTTPException(
            status_code=409,
            detail="A camera's name cannot be changed: it names its stream and recordings. Add a new camera instead.",
        )
    before = _fields(camera)
    camera = _save(camera, body, db)
    after = _fields(camera)
    changed = {key: {"from": before[key], "to": after[key]} for key in after if before[key] != after[key]}
    if changed:
        log.info("Camera '%s' changed: %s", camera.alias, ", ".join(changed), extra={**after, "changes": changed})
    return camera


def delete_camera(camera_id: uuid.UUID, db: DBSession) -> None:
    camera = get_camera_or_404(camera_id, db)
    fields = _fields(camera)
    repo.delete(db, camera)
    log.info("Camera '%s' deleted", fields["camera"], extra=fields)
