"""Logs each request as its answer is sent: method, path, status, how long it
took, and an id that every line logged while it ran carries too
(core/logs.py), also sent back as the X-Request-ID header. Work the request
left to run after its answer (a Session's Run being asked for) is not counted
in its time. A request that raises is that one line, an error with its
traceback: uvicorn's own report of it is dropped (core/logs.py), so one
failure counts once; work after the answer that raises is a line of its own.
A client that goes away before an answer is a warning, not a 500.

The status poll (every 3 s from each window), the health check and each byte
range a replay player asks for would bury everything else, so they are logged
at DEBUG unless they fail.
"""
import logging
import re
import time
import uuid

from app.core.logs import request_id

log = logging.getLogger("app.request")

_QUIET = re.compile(r"^/(status|health)$|^/sessions/[^/]+/recordings/[^/]+/video$")


class RequestLog:
    """Pure ASGI middleware, so a streamed response (the live stream, a replay)
    is logged when it ends, with its true duration."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        rid = headers.get(b"x-request-id", b"").decode("latin-1")[:64] or uuid.uuid4().hex[:12]
        token = request_id.set(rid)
        started = time.perf_counter()
        status = None
        answered = False

        def log_request(failure=None):
            nonlocal answered
            answered = True
            fields = {"method": scope["method"], "path": scope["path"], "status": status,
                      "duration_ms": round((time.perf_counter() - started) * 1000, 1)}
            if scope.get("query_string"):
                fields["query"] = scope["query_string"].decode("latin-1")[:300]
            if failure is None and status is None:
                log.warning("%s %s: the client went away before an answer", scope["method"], scope["path"],
                            extra=fields)
                return
            code = 500 if status is None else status   # ServerErrorMiddleware's answer to a crash
            fields["status"] = code
            log.log(logging.ERROR if failure else _level(scope, code), "%s %s %s", scope["method"],
                    scope["path"], code, extra=fields, exc_info=failure)

        async def send_logged(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], (b"x-request-id", rid.encode("latin-1"))]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body") and not answered:
                log_request()

        try:
            await self.app(scope, receive, send_logged)
        except Exception as e:
            if answered:
                log.error("%s %s: work after the answer failed", scope["method"], scope["path"],
                          extra={"method": scope["method"], "path": scope["path"]}, exc_info=e)
            else:
                log_request(e)
            raise
        finally:
            if not answered:
                log_request()
            request_id.reset(token)


def _level(scope, status: int) -> int:
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    if scope["method"] == "OPTIONS" or _QUIET.match(scope["path"]):
        return logging.DEBUG
    return logging.INFO
