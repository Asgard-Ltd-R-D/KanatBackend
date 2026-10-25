import json
import logging
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.logs import LOG_FILE, log_dir
from app.main import app  # starts logging before any test here runs


@pytest.fixture
def new_lines():
    """The JSON lines written to backend.log from now on."""
    path = log_dir() / LOG_FILE
    start = path.stat().st_size if path.exists() else 0

    def read() -> list[dict]:
        with open(path, encoding="utf-8") as f:
            f.seek(start)
            return [json.loads(line) for line in f if line.strip()]

    return read


def test_a_log_line_is_json_with_the_calls_own_fields(new_lines):
    session_id = uuid.uuid4()
    logging.getLogger("app.services.sessions").info(
        "Session '%s' created", "Range A",
        extra={"session_id": session_id, "record": True, "at": datetime(2026, 10, 22, tzinfo=timezone.utc)},
    )

    [line] = new_lines()
    assert line["message"] == "Session 'Range A' created"
    assert line["level"] == "info" and line["service"] == "backend"
    assert line["logger"] == "app.services.sessions"
    assert line["session_id"] == str(session_id) and line["record"] is True
    assert line["at"] == "2026-10-22T00:00:00+00:00"
    assert "request_id" not in line                  # not logged during a request


def test_an_exception_is_logged_with_its_traceback(new_lines):
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("app.test").exception("It failed")

    [line] = new_lines()
    assert line["level"] == "error" and "ValueError: boom" in line["exception"]


def test_each_request_is_logged_with_its_id_status_and_duration(new_lines):
    with TestClient(app) as client:
        res = client.get("/no-such-page", headers={"X-Request-ID": "req-1"})

    assert res.headers["x-request-id"] == "req-1"
    [line] = [l for l in new_lines() if l["logger"] == "app.request"]
    assert line["message"] == "GET /no-such-page 404"
    assert line["level"] == "warning"                # a 4xx
    assert line["status"] == 404 and line["method"] == "GET" and line["request_id"] == "req-1"
    assert line["duration_ms"] >= 0


def test_the_status_poll_is_not_logged_unless_it_fails(monkeypatch, new_lines):
    from app.services import mediamtx

    monkeypatch.setattr(mediamtx, "is_reachable", lambda: True)
    with TestClient(app) as client:
        client.get("/status")

    assert not [l for l in new_lines() if l.get("path") == "/status"]


def test_a_line_logged_on_the_threadpool_still_carries_its_requests_id(new_lines):
    # A sync route runs on the threadpool: the request's id must follow it there
    def route():
        logging.getLogger("app.services.test").info("Doing the work")
        return {}

    app.add_api_route("/test-work", route, methods=["POST"])
    try:
        with TestClient(app) as client:
            client.post("/test-work", headers={"X-Request-ID": "work-7"})
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/test-work"]

    [line] = [l for l in new_lines() if l["message"] == "Doing the work"]
    assert line["request_id"] == "work-7"


def test_a_request_that_raises_is_one_error_line_with_its_traceback(new_lines):
    def route():
        raise RuntimeError("the database went away")

    app.add_api_route("/test-crash", route, methods=["GET"])
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/test-crash").status_code == 500
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/test-crash"]

    errors = [l for l in new_lines() if l["level"] == "error"]
    assert [(l["message"], l["status"]) for l in errors] == [("GET /test-crash 500", 500)]
    assert errors[0]["exception"].endswith("RuntimeError: the database went away")


def test_uvicorns_second_report_of_a_request_that_raised_is_dropped():
    record = logging.LogRecord("uvicorn.error", logging.ERROR, "", 0, "Exception in ASGI application", None, None)
    other = logging.LogRecord("uvicorn.error", logging.ERROR, "", 0, "Address already in use", None, None)
    errors = logging.getLogger("uvicorn.error")
    assert not errors.filter(record) and errors.filter(other)


def test_a_request_refused_as_invalid_is_logged_with_what_was_wrong(new_lines):
    with TestClient(app) as client:
        res = client.post("/sessions", json={"record": True})       # no name

    assert res.status_code == 422
    [line] = [l for l in new_lines() if l["message"].startswith("Request refused as invalid")]
    assert line["path"] == "/sessions"
    assert line["problems"] == [{"where": "body.name", "problem": "Field required"}]


def test_a_request_is_logged_when_answered_not_after_its_background_work(new_lines):
    from fastapi import BackgroundTasks

    def after():
        logging.getLogger("app.services.test").info("After the answer")
        raise RuntimeError("the Run could not be asked for")

    def route(background: BackgroundTasks):
        background.add_task(after)
        return {}

    app.add_api_route("/test-later", route, methods=["POST"])
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.post("/test-later").status_code == 200
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/test-later"]

    lines = [(l["level"], l["message"]) for l in new_lines() if "/test-later" in l["message"] or "After" in l["message"]]
    assert lines == [
        ("info", "POST /test-later 200"),
        ("info", "After the answer"),
        ("error", "POST /test-later: work after the answer failed"),
    ]


def test_a_client_gone_before_an_answer_is_a_warning_not_a_500(new_lines):
    import asyncio

    from app.core.request_log import RequestLog

    async def unanswered(scope, receive, send):
        pass   # as a request cancelled before its answer started

    scope = {"type": "http", "method": "GET", "path": "/sessions", "headers": []}
    asyncio.run(RequestLog(unanswered)(scope, None, None))

    [line] = [l for l in new_lines() if l["logger"] == "app.request"]
    assert (line["level"], line["message"], line["status"]) == (
        "warning", "GET /sessions: the client went away before an answer", None)
