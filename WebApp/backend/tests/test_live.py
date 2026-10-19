import asyncio
import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core import live
from app.core.deps import get_db
from app.core.live import event_stream, hub
from app.main import app
from app.routers import live as live_router
from app.schemas.live import BulletDeletedEvent
from app.services import bullets as bullet_svc
from app.services import sessions as session_svc

SESSION_ID = uuid.uuid4()
NOW = datetime.now(timezone.utc)


class FakeDB:
    def close(self):
        pass


def make_bullet(rank=1):
    return SimpleNamespace(
        id=uuid.uuid4(), session_id=SESSION_ID, rank=rank, first_seen_at=NOW,
        position_x=100.0, position_y=200.0, target_index=0, x_mm=1.5, y_mm=-2.5,
        source="model", created_at=NOW,
    )


def make_session(status="active"):
    return SimpleNamespace(
        id=SESSION_ID, name="Range 1", status=status, started_at=NOW,
        ended_at=None, created_at=NOW, active_bullet_holes=[],
    )


@pytest.fixture
def client(monkeypatch):
    """The app with the database replaced: only SESSION_ID exists."""
    def get_session_or_404(session_id, db):
        if session_id != SESSION_ID:
            raise HTTPException(status_code=404, detail="Session not found")
        return make_session()

    monkeypatch.setattr(session_svc, "get_session_or_404", get_session_or_404)
    app.dependency_overrides[get_db] = FakeDB
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def subscribed():
    """A queue subscribed to SESSION_ID's events, unsubscribed afterwards."""
    queue = hub.subscribe(SESSION_ID)
    yield queue
    hub.unsubscribe(SESSION_ID, queue)


def next_event(queue):
    return json.loads(queue.get_nowait())


BULLET_BODY = {
    "version": "v1",
    "first_seen_at": NOW.isoformat(),
    "position": {"x": 100, "y": 200},
}


def test_a_reported_bullet_is_published(client, subscribed, monkeypatch):
    bullet = make_bullet()
    monkeypatch.setattr(bullet_svc, "create_bullet", lambda session_id, body, db: bullet)

    assert client.post(f"/sessions/{SESSION_ID}/bullets", json=BULLET_BODY).status_code == 201
    event = next_event(subscribed)

    assert event["type"] == "bullet_created"
    assert event["bullet"]["id"] == str(bullet.id)
    assert event["bullet"]["rank"] == 1
    assert event["bullet"]["x_mm"] == 1.5


def test_a_deleted_bullet_is_published(client, subscribed, monkeypatch):
    monkeypatch.setattr(bullet_svc, "delete_bullet", lambda session_id, bullet_id, db: None)
    bullet_id = uuid.uuid4()

    assert client.delete(f"/sessions/{SESSION_ID}/bullets/{bullet_id}").status_code == 204

    assert next_event(subscribed) == {"type": "bullet_deleted", "bullet_id": str(bullet_id)}


def test_ending_the_session_is_published(client, subscribed, monkeypatch):
    monkeypatch.setattr(session_svc, "update_session", lambda session_id, body, db: make_session("completed"))

    assert client.patch(f"/sessions/{SESSION_ID}", json={"status": "completed"}).status_code == 200

    assert next_event(subscribed) == {"type": "session_updated", "status": "completed"}


def test_an_unknown_session_answers_404(client):
    # A 404 is what makes the browser's EventSource stop reconnecting
    assert client.get(f"/sessions/{uuid.uuid4()}/live").status_code == 404


def test_a_closed_stream_unsubscribes_on_the_event_loop(client, monkeypatch):
    # The hub is only safe to change from the event loop, which owns it
    unsubscribe, ran_on = hub.unsubscribe, []

    def record(session_id, queue):
        try:
            asyncio.get_running_loop()
            ran_on.append("event loop")
        except RuntimeError:
            ran_on.append("worker thread")
        unsubscribe(session_id, queue)

    async def one_event(queue):
        yield "data: {}\n\n"

    monkeypatch.setattr(hub, "unsubscribe", record)
    monkeypatch.setattr(live_router, "event_stream", one_event)

    assert client.get(f"/sessions/{SESSION_ID}/live").status_code == 200
    assert ran_on == ["event loop"]
    assert SESSION_ID not in hub._subscribers


def test_events_reach_only_their_own_session():
    other = uuid.uuid4()
    mine, theirs = hub.subscribe(SESSION_ID), hub.subscribe(other)
    try:
        hub.publish(other, BulletDeletedEvent(bullet_id=uuid.uuid4()))
        assert mine.empty()
        assert not theirs.empty()
    finally:
        hub.unsubscribe(SESSION_ID, mine)
        hub.unsubscribe(other, theirs)


def test_a_subscriber_too_far_behind_is_cut_off_and_the_others_still_get_the_event(monkeypatch):
    monkeypatch.setattr(live, "QUEUE_SIZE", 1)
    hub = live.LiveHub()
    behind, current = hub.subscribe(SESSION_ID), hub.subscribe(SESSION_ID)
    hub.publish(SESSION_ID, BulletDeletedEvent(bullet_id=uuid.uuid4()))
    current.get_nowait()

    hub.publish(SESSION_ID, BulletDeletedEvent(bullet_id=uuid.uuid4()))

    assert not current.empty()
    assert behind.get_nowait() is None  # ends its stream, so the browser reconnects
    assert hub._subscribers[SESSION_ID] == {current}


def test_the_stream_formats_events_and_ends_on_none(monkeypatch):
    monkeypatch.setattr(live, "PING_S", 0.05)

    async def read():
        queue = asyncio.Queue()
        stream = event_stream(queue)
        lines = [await anext(stream)]   # retry
        lines.append(await anext(stream))  # ping: nothing queued yet
        queue.put_nowait('{"type": "x"}')
        queue.put_nowait(None)
        lines += [line async for line in stream]
        return lines

    assert asyncio.run(read()) == [
        f"retry: {live.RETRY_MS}\n\n",
        "event: ping\ndata: ping\n\n",
        'data: {"type": "x"}\n\n',
    ]
