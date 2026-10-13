"""Posting Confirmed Bullet Holes to the WebApp (#155).

`WebAppPublisher` is the WebApp's adapter on the pipeline's `publish` seam:
`process` hands it each Confirmed Bullet Hole once, as a
`BulletHoleConfirmed`, and it owns everything that is the WebApp's: the v1
wire format (WebApp/backend/docs/api_contract.md), the idempotency key, the
queue, retries and the final drain. It reads the value's fields and nothing
else, and never imports the pipeline, so it knows nothing of Board space,
frames or the source.
"""
import json
import queue
import threading
import uuid
from datetime import timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# The wait before each retry of a network error or a 5xx, doubling to a cap:
# 9 attempts in all.
RETRY_DELAYS_S = (2, 4, 8, 16, 32, 60, 60, 60)

# How long leaving the `with` waits for what is queued to be posted.
DRAIN_TIMEOUT_S = 120

# One POST's socket timeout, and the grace one in flight gets past the drain.
SOCKET_TIMEOUT_S = 10

# The template's size in px: the range the WebApp validates `position` against.
TEMPLATE_W, TEMPLATE_H = 1405.0, 1120.0


class WebAppPublisher:
    """POSTs each value published to `/sessions/{session_id}/bullets`, on one
    worker thread in the order published, so that a slow or absent WebApp
    never delays a Look. A network error or a 5xx is retried after each of
    `RETRY_DELAYS_S`; a 4xx is dropped, its body logged. A retry is safe: its
    key is the same, and the WebApp answers a key it already holds in the
    Session with that row.

    Leaving the `with`, whether or not the block raised, drains the queue for
    up to `DRAIN_TIMEOUT_S`. Past that, retries stop and nothing more is
    posted, but a POST in flight gets one socket timeout to finish.
    """

    def __init__(self, session_id, backend_url):
        self._session_id = session_id
        self._url = f"{backend_url.rstrip('/')}/sessions/{session_id}/bullets"
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True, name="WebAppPublisher")

    def __enter__(self):
        self._worker.start()
        return self

    def __exit__(self, *exc_info):
        print("[POST] waiting for queued POSTs to finish...")
        self._queue.put(None)   # the sentinel: the worker ends once it reaches it
        self._worker.join(DRAIN_TIMEOUT_S)
        if self._worker.is_alive():
            print(f"[POST] drain timed out after {DRAIN_TIMEOUT_S} s; interrupting retries")
            self._stop.set()
            self._worker.join(SOCKET_TIMEOUT_S)

    def publish(self, value):
        """Queue a `BulletHoleConfirmed` to be posted; returns at once."""
        self._queue.put(value)

    def _run(self):
        for value in iter(self._queue.get, None):
            self._post(value)

    def _post(self, value):
        seen = _clock(value.first_seen_at)
        data = json.dumps(_payload(value, self._session_id)).encode()
        attempts = len(RETRY_DELAYS_S) + 1
        for attempt in range(1, attempts + 1):
            if self._stop.is_set():
                print(f"[POST] Bullet Hole first seen {seen}: not posted, the drain timed out")
                return
            if self._attempt(data, seen, attempt, attempts):
                return
            if attempt < attempts:
                delay = RETRY_DELAYS_S[attempt - 1]
                print(f"[POST] Bullet Hole first seen {seen}: retry in {delay} s")
                self._stop.wait(delay)   # a drain that times out wakes it at once
        print(f"[POST] Bullet Hole first seen {seen}: giving up after {attempts} attempts")

    def _attempt(self, data, seen, attempt, attempts):
        """One POST. True once it is settled: stored, or refused for good."""
        retry = f" (attempt {attempt}/{attempts})" if attempt > 1 else ""
        line = f"[POST] Bullet Hole first seen {seen}{retry} ->"
        request = Request(self._url, data=data, method="POST",
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=SOCKET_TIMEOUT_S) as response:
                print(f"{line} HTTP {response.status}")
                return True
        except HTTPError as error:
            print(f"{line} HTTP {error.code}: {error.read().decode(errors='replace')[:200]}")
            return error.code < 500   # a 4xx is dropped, a 5xx retried
        except Exception as error:   # refused, reset, timed out: the network's
            print(f"{line} ERROR: {error}")
            return False


def _payload(value, session_id):
    """A `BulletHoleConfirmed` as POST /sessions/{id}/bullets takes it
    (api_contract.md v1). Its key is derived, the same on every retry and on
    every run of the same Recording into the Session: two Bullet Holes first
    seen on one frame are a match radius apart, more than a rounded px."""
    x, y = value.template_xy
    key = uuid.uuid5(uuid.NAMESPACE_URL,
                     f"{session_id}:{value.first_frame}:{round(x)}:{round(y)}")
    utc = value.first_seen_at.astimezone(timezone.utc)
    mm = value.mm
    return {
        "version": "v1",
        "first_seen_at": utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "position": {"x": min(max(x, 0.0), TEMPLATE_W), "y": min(max(y, 0.0), TEMPLATE_H)},
        "target_index": value.target,
        "x_mm": None if mm is None else mm[0],
        "y_mm": None if mm is None else mm[1],
        "source": "model",
        "idempotency_key": str(key),
    }


def _clock(at):
    """A time as a live run prints it: local, to the centisecond."""
    return at.astimezone().strftime("%H:%M:%S.%f")[:-4]
