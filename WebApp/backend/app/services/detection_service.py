"""The Detection Service on this PC (ImageRecognitionService/detection/service.py,
ADR-0008): its control API, which starts and ends a Session's Run."""
import uuid

import httpx

from app.config.settings import settings

# A start is answered once its Run is watching, or has failed: the Stream's
# open, Board space and the baseline, which the service itself gives up on
# after its START_TIMEOUT_S (15 s)
START_TIMEOUT_S = 20
# An end is answered once the Run has stopped and its posts are drained
END_TIMEOUT_S = 10   # PROVISIONAL: #228 bounds the end with its persistence window


class DetectionServiceUnreachable(Exception):
    """The Detection Service did not answer, or answered an end with an error."""


class RunRefused(Exception):
    """The Detection Service answered a start with an error: 409 while another
    Session's Run is active (or this one's is ending), 502 when the Run failed
    to start, with the service's reason as `detail`."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail = status, detail


def _post(path: str, timeout: float, **kwargs) -> httpx.Response:
    try:
        return httpx.post(f"{settings.detection_service_url}{path}", timeout=timeout, **kwargs)
    except httpx.HTTPError as e:
        raise DetectionServiceUnreachable(f"POST {path}: {e}") from e


def start_run(session_id: uuid.UUID, stream_url: str) -> dict:
    """Start the Session's Run on the Stream, answered once it is watching:
    the Run, as the service's GET /status shows it. The same Session's Run
    already watching is answered as started. Raises RunRefused or
    DetectionServiceUnreachable."""
    res = _post("/runs", START_TIMEOUT_S, json={"session_id": str(session_id), "stream_url": stream_url})
    if res.is_error:
        try:
            detail = res.json()["detail"]
        except (ValueError, KeyError, TypeError):
            detail = res.text[:200]
        raise RunRefused(res.status_code, detail)
    return res.json()


def end_run(session_id: uuid.UUID) -> None:
    """End the Session's Run, answered once it has ended and its posts are
    drained. No such Run (404) is already ended."""
    res = _post(f"/runs/{session_id}/end", END_TIMEOUT_S)
    if res.is_error and res.status_code != 404:
        raise DetectionServiceUnreachable(f"POST /runs/{session_id}/end: HTTP {res.status_code} {res.text[:200]}")
