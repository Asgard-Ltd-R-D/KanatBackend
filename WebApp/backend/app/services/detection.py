"""Each Session's detection: whether a Run of the Detection Service watches it
(ADR-0008), on its camera's Stream from MediaMTX.

Held in memory, which is enough with the backend's single worker, and pushed
on the Session's live stream at each change. A Session the backend has not
asked a Run for reads `none`.
"""
import logging
import threading
import uuid

from app.config.settings import settings
from app.core.live import hub
from app.schemas.live import DetectionUpdatedEvent
from app.schemas.session import Detection
from app.services import detection_service

log = logging.getLogger(__name__)

NONE = Detection(state="none")

_states: dict[uuid.UUID, Detection] = {}
_lock = threading.Lock()


def state_of(session_id: uuid.UUID) -> Detection:
    return _states.get(session_id, NONE)


def _set(session_id: uuid.UUID, detection: Detection, only_from: str | None = None) -> None:
    """Changes the Session's state and pushes it, unless `only_from` is given
    and the state is no longer that."""
    with _lock:
        if only_from is not None and state_of(session_id).state != only_from:
            return
        if detection.state == "none":
            _states.pop(session_id, None)
        else:
            _states[session_id] = detection
    hub.publish_from_thread(session_id, DetectionUpdatedEvent(detection=detection))


def starting(session_id: uuid.UUID) -> None:
    """The Session's Run is about to be asked for (`watch`)."""
    _set(session_id, Detection(state="starting"))


def watch(session_id: uuid.UUID, alias: str) -> None:
    """Asks the Detection Service for the Session's Run on the camera's Stream,
    which answers once the Run is watching: seconds, so it runs after the
    request that started the Session has answered. A Session that started
    ending meanwhile keeps its state."""
    try:
        detection_service.start_run(session_id, f"{settings.mediamtx_rtsp_url}/{alias}")
    except detection_service.DetectionServiceUnreachable as e:
        log.warning("Session %s is not watched: the Detection Service did not answer: %s", session_id, e)
        result = Detection(state="not_watching", reason="service_down")
    except detection_service.RunRefused as e:
        log.warning("Session %s is not watched: %s", session_id, e)
        reason = "other_session" if e.status == 409 else "stream_failed"
        result = Detection(state="not_watching", reason=reason, detail=e.detail)
    else:
        result = Detection(state="watching")
    _set(session_id, result, only_from="starting")


def end(session) -> None:
    """Ends the active Session's Run, if it has a camera, and returns once the
    Run has ended: `ending` meanwhile, then `none`. A Detection Service that
    cannot be reached is logged, and the Session ends anyway."""
    if session.status != "active" or session.camera_id is None:
        return
    _set(session.id, Detection(state="ending"))
    try:
        detection_service.end_run(session.id)
    except detection_service.DetectionServiceUnreachable as e:
        log.warning("The Run of session %s may not have ended: %s", session.id, e)
    _set(session.id, NONE)
