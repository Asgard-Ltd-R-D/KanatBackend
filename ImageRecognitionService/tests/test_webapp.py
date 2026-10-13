"""Checks for the WebApp adapter (#155): what it sends for the values
published to it. `urlopen` is replaced inside the adapter's module only, and
retries wait no time."""
import contextlib
import io
import json
import time
import types
import urllib.error
import uuid
from datetime import datetime, timezone

import pytest

from detection import webapp
from detection.new_bullet_holes import BulletHoleConfirmed

SEEN = datetime(2026, 10, 13, 9, 30, 10, 523999, tzinfo=timezone.utc)
AT = SEEN.astimezone().strftime("%H:%M:%S.%f")[:-4]   # as a live run prints it


def _value(frame=13, xy=(1500.4, -3.6), target=0, mm=(-12.3, 4.1)):
    return BulletHoleConfirmed(frame, SEEN, xy, target, mm)


def _backend(monkeypatch, *answers, seconds=0.0):
    """The requests POSTed, as (url, payload), in order. Each is answered by
    the next of `answers`, the last repeating: an HTTP status, or an
    exception to raise. Each takes `seconds`."""
    monkeypatch.setattr(webapp, "RETRY_DELAYS_S", (0,) * len(webapp.RETRY_DELAYS_S))
    sent, pending = [], iter(answers)
    def urlopen(request, timeout):
        sent.append((request.full_url, json.loads(request.data)))
        time.sleep(seconds)
        answer = next(pending, answers[-1])
        if isinstance(answer, Exception):
            raise answer
        if answer >= 400:
            raise urllib.error.HTTPError(request.full_url, answer, "", {},
                                         io.BytesIO(b"the body"))
        return contextlib.nullcontext(types.SimpleNamespace(status=answer))
    monkeypatch.setattr(webapp, "urlopen", urlopen)
    return sent


def test_a_value_becomes_the_v1_payload(monkeypatch):
    """Clipped to the template, UTC to the millisecond with a `Z`, and keyed
    by the Session, the first frame and the rounded Template coordinates."""
    sent = _backend(monkeypatch, 201)
    with webapp.WebAppPublisher("session", "http://backend:8000/") as publisher:
        publisher.publish(_value())
        publisher.publish(_value(frame=20, xy=(700.0, 500.0), target=None, mm=None))
    (url, on_target), (_, miss) = sent
    assert url == "http://backend:8000/sessions/session/bullets"
    assert on_target == {
        "version": "v1",
        "first_seen_at": "2026-10-13T09:30:10.523Z",
        "position": {"x": 1405.0, "y": 0.0},
        "target_index": 0,
        "x_mm": -12.3,
        "y_mm": 4.1,
        "source": "model",
        "idempotency_key": str(uuid.uuid5(uuid.NAMESPACE_URL, "session:13:1500:-4")),
    }
    assert miss["target_index"] is miss["x_mm"] is miss["y_mm"] is None


def test_a_5xx_or_a_network_error_is_retried_with_the_same_key(monkeypatch, capsys):
    sent = _backend(monkeypatch, 503, urllib.error.URLError("refused"), 201)
    with webapp.WebAppPublisher("session", "http://backend:8000") as publisher:
        publisher.publish(_value())
    assert len(sent) == 3 and sent[0] == sent[1] == sent[2]
    out = capsys.readouterr().out
    assert f"[POST] Bullet Hole first seen {AT} -> HTTP 503: the body" in out
    assert f"[POST] Bullet Hole first seen {AT} (attempt 2/9) -> ERROR:" in out
    assert f"[POST] Bullet Hole first seen {AT} (attempt 3/9) -> HTTP 201" in out


def test_a_4xx_is_dropped_without_a_retry(monkeypatch, capsys):
    sent = _backend(monkeypatch, 422, 201)
    with webapp.WebAppPublisher("session", "http://backend:8000") as publisher:
        publisher.publish(_value())
    assert len(sent) == 1
    assert f"[POST] Bullet Hole first seen {AT} -> HTTP 422: the body" in \
        capsys.readouterr().out


def test_leaving_the_with_even_by_raising_sends_everything_queued_in_order(monkeypatch):
    """Each POST slow enough that the values are still queued when the block
    is left: by an exception, as a run that failed partway leaves it."""
    sent = _backend(monkeypatch, 201, seconds=0.02)
    with pytest.raises(RuntimeError):
        with webapp.WebAppPublisher("session", "http://backend:8000") as publisher:
            for x in (100.0, 200.0, 300.0):
                publisher.publish(_value(xy=(x, 50.0)))
            raise RuntimeError("the run failed")
    assert [p["position"]["x"] for _, p in sent] == [100.0, 200.0, 300.0]


def test_a_drain_that_times_out_stops_pending_retries(monkeypatch, capsys):
    """The WebApp answers 503 for good and each retry waits a minute: past
    the drain's timeout the retry is woken and abandoned, and the value
    queued behind it is never sent."""
    sent = _backend(monkeypatch, 503)
    monkeypatch.setattr(webapp, "RETRY_DELAYS_S", (60,) * 8)
    monkeypatch.setattr(webapp, "DRAIN_TIMEOUT_S", 0.1)
    began = time.monotonic()
    with webapp.WebAppPublisher("session", "http://backend:8000") as publisher:
        publisher.publish(_value())
        publisher.publish(_value(frame=14))
    assert time.monotonic() - began < 5
    assert len(sent) == 1
    out = capsys.readouterr().out
    assert "[POST] drain timed out after 0.1 s" in out
    assert out.count(f"[POST] Bullet Hole first seen {AT}: not posted") == 2
