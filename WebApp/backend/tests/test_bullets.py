"""POST /sessions/{id}/bullets against the v1 contract (docs/api_contract.md),
with the database replaced: what a Bullet Hole is stored as, and what is
refused."""
import json
import math
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.main import app
from app.repositories import bullets as bullets_repo
from app.repositories import sessions as sessions_repo
from tests.fakes import NOW


class FakeDB:
    def close(self):
        pass


@pytest.fixture
def session(monkeypatch):
    """The only Session there is, active until a test completes it."""
    session = SimpleNamespace(id=uuid.uuid4(), status="active")
    monkeypatch.setattr(sessions_repo, "get_for_update",
                        lambda db, session_id: session if session_id == session.id else None)
    return session


@pytest.fixture
def stored(monkeypatch):
    """The Bullet Holes stored, in order."""
    rows = []

    def add(db, bullet):
        bullet.created_at = NOW
        rows.append(bullet)
        return bullet

    monkeypatch.setattr(bullets_repo, "find_by_idempotency_key", lambda db, session_id, key: None)
    monkeypatch.setattr(bullets_repo, "count_active", lambda db, session_id: len(rows))
    monkeypatch.setattr(bullets_repo, "add", add)
    return rows


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = FakeDB
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def body(x, y, **fields):
    return {"version": "v1", "first_seen_at": NOW.isoformat(), "position": {"x": x, "y": y}, **fields}


@pytest.mark.parametrize("x, y", [
    (774.8, 560.3),     # on the artwork
    (1500.4, -3.6),     # a Miss beyond it
    (-2210.0, 3405.5),  # on another Target
])
def test_a_position_is_stored_as_sent(client, session, stored, x, y):
    res = client.post(f"/sessions/{session.id}/bullets", json=body(x, y))

    assert res.status_code == 201
    assert (res.json()["position_x"], res.json()["position_y"]) == (x, y)
    assert [(b.position_x, b.position_y) for b in stored] == [(x, y)]


def test_a_manual_position_off_the_artwork_is_stored_as_sent(client, session, stored):
    session.status = "completed"

    res = client.post(f"/sessions/{session.id}/bullets", json=body(1406.0, 1121.0, source="manual"))

    assert res.status_code == 201
    assert [(b.position_x, b.position_y, b.source) for b in stored] == [(1406.0, 1121.0, "manual")]


@pytest.mark.parametrize("payload", [
    *(body(value, 0) for value in (math.nan, math.inf, -math.inf, "", "abc", None)),
    body(0, -math.inf),
    body(0, 0, x_mm=math.nan),
])
def test_a_value_that_is_not_a_finite_number_is_refused(client, session, stored, payload):
    # Python's JSON writes and reads NaN and Infinity, so they reach the
    # schema, and the 422 must still be written as JSON
    res = client.post(f"/sessions/{session.id}/bullets", content=json.dumps(payload),
                      headers={"Content-Type": "application/json"})

    assert res.status_code == 422
    assert stored == []


def test_an_unknown_version_is_refused(client, session, stored):
    res = client.post(f"/sessions/{session.id}/bullets", json={**body(774.8, 560.3), "version": "v2"})

    assert res.status_code == 422
    assert stored == []


# --- the write gate: who may add a bullet, and when ---

def test_the_model_cannot_add_a_bullet_to_a_completed_session(client, session, stored):
    session.status = "completed"

    res = client.post(f"/sessions/{session.id}/bullets", json=body(774.8, 560.3))  # source defaults to model

    assert res.status_code == 409
    assert stored == []


def test_a_manual_bullet_cannot_be_added_while_the_session_is_active(client, session, stored):
    # Manual bullets are the operator's corrections, only after the session ends
    res = client.post(f"/sessions/{session.id}/bullets", json=body(774.8, 560.3, source="manual"))

    assert res.status_code == 409
    assert stored == []


# --- ranking ---

def test_bullets_are_ranked_in_the_order_they_arrive(client, session, stored):
    # rank = count_active + 1, serialized so three in a row are 1, 2, 3
    for x in (1.0, 2.0, 3.0):
        assert client.post(f"/sessions/{session.id}/bullets", json=body(x, 0.0)).status_code == 201

    assert [b.rank for b in stored] == [1, 2, 3]


def test_a_bullet_reported_again_with_the_same_key_returns_the_stored_one(client, session, stored, monkeypatch):
    # The model retried a POST whose answer it never got: the stored bullet is
    # returned and nothing new is stored (idempotency_key dedup)
    from app.models import BulletHole

    existing = BulletHole(
        id=uuid.uuid4(), session_id=session.id, first_seen_at=NOW, position_x=1.0, position_y=2.0,
        source="model", rank=7, idempotency_key="shot-1", created_at=NOW,
    )
    monkeypatch.setattr(bullets_repo, "find_by_idempotency_key",
                        lambda db, session_id, key: existing if key == "shot-1" else None)

    res = client.post(f"/sessions/{session.id}/bullets", json=body(9.0, 9.0, idempotency_key="shot-1"))

    assert res.status_code == 201
    assert res.json()["id"] == str(existing.id) and res.json()["rank"] == 7
    assert stored == []   # the retry stored nothing new
