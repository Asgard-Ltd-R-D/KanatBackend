"""One active Session at a time (services/sessions.py), driven through the
REST API with the database replaced (tests/conftest.py); the database's own
hold on it is in tests/test_schema.py."""


def test_a_session_cannot_start_while_another_is_active(client, db, detection):
    first = client.post("/sessions", json={"name": "Range A"})

    second = client.post("/sessions", json={"name": "Range B"})

    assert first.status_code == 201
    assert (second.status_code, second.json()["detail"]) == (409, "Session 'Range A' is still active: complete it first")
    assert [s.name for s in db.sessions.values()] == ["Range A"]


def test_a_session_can_start_once_the_active_one_completes(client, db, detection):
    first = client.post("/sessions", json={"name": "Range A"}).json()["id"]
    client.patch(f"/sessions/{first}", json={"status": "completed"})

    assert client.post("/sessions", json={"name": "Range B"}).status_code == 201


def test_a_completed_session_cannot_reopen_while_another_is_active(client, db, detection):
    first = client.post("/sessions", json={"name": "Range A"}).json()["id"]
    client.patch(f"/sessions/{first}", json={"status": "completed"})
    client.post("/sessions", json={"name": "Range B"})

    res = client.patch(f"/sessions/{first}", json={"status": "active"})

    assert (res.status_code, res.json()["detail"]) == (409, "Session 'Range B' is still active: complete it first")


def test_the_active_session_can_still_be_changed(client, db, detection):
    session_id = client.post("/sessions", json={"name": "Range A"}).json()["id"]

    res = client.patch(f"/sessions/{session_id}", json={"name": "Range A2", "status": "active"})

    assert (res.status_code, res.json()["name"]) == (200, "Range A2")


def test_a_session_cannot_take_a_name_already_in_use(client, db, detection):
    first = client.post("/sessions", json={"name": "Range A"}).json()["id"]
    client.patch(f"/sessions/{first}", json={"status": "completed"})

    # Same name, differing only in case and surrounding space: still a clash
    res = client.post("/sessions", json={"name": " range a "})

    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]
    assert [s.name for s in db.sessions.values()] == ["Range A"]


def test_a_session_cannot_be_renamed_onto_another_name(client, db, detection):
    first = client.post("/sessions", json={"name": "Range A"}).json()["id"]
    client.patch(f"/sessions/{first}", json={"status": "completed"})
    second = client.post("/sessions", json={"name": "Range B"}).json()["id"]

    res = client.patch(f"/sessions/{second}", json={"name": "Range A"})

    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]


def test_a_session_name_clash_folds_unicode_case(client, db, detection):
    first = client.post("/sessions", json={"name": "Équipe"}).json()["id"]
    client.patch(f"/sessions/{first}", json={"status": "completed"})

    # Case folded across Unicode, not only ASCII: "équipe" clashes with "Équipe"
    res = client.post("/sessions", json={"name": " équipe "})

    assert res.status_code == 409
    assert [s.name for s in db.sessions.values()] == ["Équipe"]


def test_a_session_may_keep_its_own_name_on_update(client, db, detection):
    session_id = client.post("/sessions", json={"name": "Range A"}).json()["id"]

    # Renaming to its own name (here via a status change) is not a clash with itself
    res = client.patch(f"/sessions/{session_id}", json={"name": "Range A", "status": "completed"})

    assert res.status_code == 200
