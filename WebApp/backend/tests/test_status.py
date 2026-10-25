import uuid

import httpx
import pytest

from app.services import detection_client, mediamtx

# --- the status indicator ---

def test_the_status_reports_whether_the_video_and_detection_services_answer(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        monkeypatch.setattr(mediamtx, "is_reachable", lambda: True)
        monkeypatch.setattr(detection_client, "is_reachable", lambda: False)
        assert client.get("/status").json() == {"video_service": True, "detection_service": False}
        monkeypatch.setattr(mediamtx, "is_reachable", lambda: False)
        monkeypatch.setattr(detection_client, "is_reachable", lambda: True)
        assert client.get("/status").json() == {"video_service": False, "detection_service": True}


@pytest.mark.parametrize("service", [mediamtx, detection_client], ids=["video", "detection"])
def test_the_status_uses_a_recent_answer_and_asks_only_without_one(monkeypatch, service):
    clock = [1000.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    asked = []

    def request(method, url, timeout, **kwargs):
        asked.append(url)
        return httpx.Response(200, json={}, request=httpx.Request(method, url))

    monkeypatch.setattr(service.httpx, "request", request)
    monkeypatch.setattr(service, "_last_answer", None)

    assert service.is_reachable() is True      # no answer yet: asks
    assert len(asked) == 1
    clock[0] += service.FRESH_S - 1
    assert service.is_reachable() is True      # recent answer: does not ask
    assert len(asked) == 1

    clock[0] += 2                               # stale: asks again, and finds it down
    monkeypatch.setattr(service.httpx, "request", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert service.is_reachable() is False


def test_any_answer_from_the_detection_service_counts_as_up(monkeypatch):
    asked = []

    def request(method, url, timeout, **kwargs):
        asked.append(url)
        return httpx.Response(404, json={"detail": "no such Run"}, request=httpx.Request(method, url))

    monkeypatch.setattr(detection_client.httpx, "request", request)
    monkeypatch.setattr(detection_client, "_last_answer", None)

    detection_client.end_run(uuid.uuid4())     # no such Run: an answer all the same
    assert detection_client.is_reachable() is True
    assert len(asked) == 1
