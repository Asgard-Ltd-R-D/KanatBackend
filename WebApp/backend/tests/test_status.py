import httpx

from app.services import mediamtx


# --- the status indicator ---

def test_the_status_reports_whether_the_video_service_answers(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        monkeypatch.setattr(mediamtx, "is_reachable", lambda: True)
        assert client.get("/status").json() == {"video_service": True}
        monkeypatch.setattr(mediamtx, "is_reachable", lambda: False)
        assert client.get("/status").json() == {"video_service": False}


def test_the_status_uses_a_recent_answer_and_asks_only_without_one(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(mediamtx.time, "monotonic", lambda: clock[0])
    asked = []

    def request(method, url, timeout, **kwargs):
        asked.append(url)
        return httpx.Response(200, json={}, request=httpx.Request(method, url))

    monkeypatch.setattr(mediamtx.httpx, "request", request)
    monkeypatch.setattr(mediamtx, "_last_answer", None)

    assert mediamtx.is_reachable() is True      # no answer yet: asks
    assert len(asked) == 1
    clock[0] += mediamtx.FRESH_S - 1
    assert mediamtx.is_reachable() is True      # recent answer: does not ask
    assert len(asked) == 1

    clock[0] += 2                               # stale: asks again, and finds it down
    monkeypatch.setattr(mediamtx.httpx, "request", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert mediamtx.is_reachable() is False
