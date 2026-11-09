import uuid

import httpx
import pytest

from app.services import detection_client, mediamtx

# --- the status indicator ---

def test_the_status_reports_whether_the_video_and_detection_services_answer(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(detection_client, "_detector", (None, None))
    with TestClient(app) as client:
        monkeypatch.setattr(mediamtx, "is_reachable", lambda: True)
        monkeypatch.setattr(detection_client, "is_reachable", lambda: False)
        assert client.get("/status").json() == {"video_service": True, "detection_service": False,
                                                "detector_device": None, "detector_model": None}
        monkeypatch.setattr(mediamtx, "is_reachable", lambda: False)
        monkeypatch.setattr(detection_client, "is_reachable", lambda: True)
        assert client.get("/status").json() == {"video_service": False, "detection_service": True,
                                                "detector_device": None, "detector_model": None}


@pytest.mark.parametrize("read", [detection_client.is_reachable, detection_client.status],
                         ids=["status check", "reconcile read"])
def test_the_status_reports_the_detector_the_last_status_answer_named(monkeypatch, read):
    """Kept from the reads the backend already makes, so showing it asks
    the Detection Service nothing more; an older service names no model."""
    from fastapi.testclient import TestClient

    from app.main import app

    answer = {"run": None, "device": "cuda:0", "model": "kanat_yolo26m_v1"}
    monkeypatch.setattr(detection_client.httpx, "request", lambda method, url, timeout, **kwargs:
                        httpx.Response(200, json=answer, request=httpx.Request(method, url)))
    monkeypatch.setattr(detection_client, "_last_answer", None)
    monkeypatch.setattr(detection_client, "_detector", (None, None))
    read()

    with TestClient(app) as client:
        monkeypatch.setattr(mediamtx, "is_reachable", lambda: True)
        assert client.get("/status").json() == {"video_service": True, "detection_service": True,
                                                "detector_device": "cuda:0",
                                                "detector_model": "kanat_yolo26m_v1"}
    del answer["model"]
    detection_client.status()
    assert detection_client.detector() == ("cuda:0", None)
    answer["device"] = {"type": "cuda"}   # not a name: dropped, not passed on to fail the status
    detection_client.status()
    assert detection_client.detector() == (None, None)


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
