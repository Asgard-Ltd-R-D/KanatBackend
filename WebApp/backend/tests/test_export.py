"""Exporting a Session's results (routers/export.py): refused while it is still
active, so no one hands out a report of a live Session."""
import uuid
from types import SimpleNamespace

import pytest

from app.routers import export as export_router


@pytest.mark.parametrize("fmt", ["pdf", "csv", "excel"])
def test_exporting_an_active_session_is_refused(client, monkeypatch, fmt):
    session_id = uuid.uuid4()
    active = SimpleNamespace(id=session_id, name="Range A", status="active")
    # The router bound get_session_detail by name, so patch it on the router
    monkeypatch.setattr(export_router, "get_session_detail", lambda sid, db: active)

    res = client.get(f"/sessions/{session_id}/export/{fmt}")

    assert res.status_code == 409
    assert "close it before exporting" in res.json()["detail"]
