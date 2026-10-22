"""The Detection Service on this PC (ImageRecognitionService/detection/service.py,
ADR-0008): its control API, which starts and ends a Session's Run."""
import time
import uuid
from typing import NamedTuple

import httpx

from app.config.settings import settings

# A start is answered once its Run is watching, or has failed: the Stream's
# open, Board space and the baseline, which the service itself gives up on
# after its START_TIMEOUT_S (15 s)
START_TIMEOUT_S = 20
# An end is answered once the Run has judged the Candidates it has open, which
# the service bounds by its ENDING_TIMEOUT_S (5 s), its Stream is closed, which
# waits out a stalled read for up to its STREAM_TIMEOUT_MS (5 s), and its posts
# to this backend are drained: ~1.5-3 s when the Stream is well (#228)
END_TIMEOUT_S = 15   # PROVISIONAL
# The status check answers within the frontend's own 2 s limit, as MediaMTX's
# does beside it (routers/status.py)
STATUS_TIMEOUT_S = 1
# An answer this recent counts as the Detection Service being up, so a stopped
# service reads down within it, plus the frontend's 3 s poll
FRESH_S = 12

# When the Detection Service last answered (time.monotonic()), from any
# request: kept in memory, which is enough with the backend's single worker.
# Unlike MediaMTX's, an error status counts too: a 404 for no such Run or a
# 409 for another Session's is the service answering.
_last_answer: float | None = None


class DetectionServiceUnreachable(Exception):
    """The Detection Service did not answer, or answered an end with an error."""


class Run(NamedTuple):
    """The Detection Service's Run, as its status reports it."""
    session_id: uuid.UUID
    state: str   # starting, watching or ending


class RunRefused(Exception):
    """The Detection Service answered a start with an error: 409 while another
    Session's Run is active (or this one's is ending), 502 when the Run failed
    to start, with the service's reason as `detail`."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail = status, detail


def _request(method: str, path: str, timeout: float, **kwargs) -> httpx.Response:
    try:
        res = httpx.request(method, f"{settings.detection_service_url}{path}", timeout=timeout, **kwargs)
    except httpx.HTTPError as e:
        raise DetectionServiceUnreachable(f"{method} {path}: {e}") from e
    global _last_answer
    _last_answer = time.monotonic()
    return res


def is_reachable() -> bool:
    """Whether the Detection Service is up. A recent answer to any call says
    so without asking again; it is asked only when there is none."""
    if _last_answer is not None and time.monotonic() - _last_answer < FRESH_S:
        return True
    try:
        _request("GET", "/status", STATUS_TIMEOUT_S)
    except DetectionServiceUnreachable:
        return False
    return True


def status() -> Run | None:
    """The Detection Service's Run, or None without one. Raises
    DetectionServiceUnreachable, also for an answer that is not its status."""
    res = _request("GET", "/status", STATUS_TIMEOUT_S)
    try:
        run = res.raise_for_status().json()["run"]
        return None if run is None else Run(uuid.UUID(run["session_id"]), run["state"])
    except (httpx.HTTPStatusError, ValueError, KeyError, TypeError) as e:
        raise DetectionServiceUnreachable(f"GET /status: HTTP {res.status_code} {res.text[:200]}") from e


def start_run(session_id: uuid.UUID, stream_url: str) -> None:
    """Start the Session's Run on the Stream, answered once it is watching.
    The same Session's Run already watching is answered as started. Raises
    RunRefused or DetectionServiceUnreachable."""
    res = _request("POST", "/runs", START_TIMEOUT_S, json={"session_id": str(session_id), "stream_url": stream_url})
    if res.is_error:
        try:
            detail = res.json()["detail"]
        except (ValueError, KeyError, TypeError):
            detail = res.text[:200]
        raise RunRefused(res.status_code, detail)


def end_run(session_id: uuid.UUID) -> bool:
    """End the Session's Run, answered once it has ended and its posts are
    drained. Returns whether there was one: no such Run (404) is already
    ended, but not by this end, so what it saw last is not confirmed posted."""
    res = _request("POST", f"/runs/{session_id}/end", END_TIMEOUT_S)
    if res.is_error and res.status_code != 404:
        raise DetectionServiceUnreachable(f"POST /runs/{session_id}/end: HTTP {res.status_code} {res.text[:200]}")
    return res.status_code != 404
