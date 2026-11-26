"""The baseline frame image stored per Run: uploaded by the Detection Service,
served to the web app. The database is replaced; files go to a temp log dir."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config.settings import settings
from app.core.deps import get_db
from app.main import app
from app.repositories import runs as runs_repo
from tests.fakes import FakeDB

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
SESSION = uuid.uuid4()


@pytest.fixture
def run(monkeypatch, tmp_path):
    """The latest Run of camera `cam1` in SESSION, and a temp log dir."""
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    run = SimpleNamespace(session_id=SESSION, camera_alias="cam1",
                          taken_at=datetime(2026, 11, 26, 9, 0, tzinfo=timezone.utc), baseline_image_path=None)
    monkeypatch.setattr(runs_repo, "latest",
                        lambda db, session_id, alias: run if (session_id, alias) == (SESSION, "cam1") else None)
    monkeypatch.setattr(runs_repo, "save", lambda db: None)
    return run


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = FakeDB
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def url(alias="cam1"):
    return f"/sessions/{SESSION}/cameras/{alias}/baseline-image"


def test_an_uploaded_image_is_stored_on_the_latest_run(client, run, tmp_path):
    res = client.post(url(), content=PNG, headers={"content-type": "image/png"})

    assert res.status_code == 204
    assert (tmp_path / run.baseline_image_path).read_bytes() == PNG
    assert run.baseline_image_path.startswith(f"baseline-images/{SESSION}/")


def test_the_stored_image_is_served(client, run):
    client.post(url(), content=PNG, headers={"content-type": "image/png"})

    res = client.get(url())

    assert res.status_code == 200
    assert res.content == PNG
    assert res.headers["content-type"] == "image/png"


def test_nothing_stored_is_a_404(client, run):
    assert client.get(url()).status_code == 404


def test_an_unsupported_content_type_is_a_415(client, run):
    res = client.post(url(), content=b"hello", headers={"content-type": "text/plain"})

    assert res.status_code == 415
    assert run.baseline_image_path is None


def test_a_camera_with_no_run_is_a_404(client, run):
    res = client.post(url("other"), content=PNG, headers={"content-type": "image/png"})

    assert res.status_code == 404


def test_a_reserved_or_unsafe_alias_gets_a_safe_filename(client, run, monkeypatch, tmp_path):
    monkeypatch.setattr(runs_repo, "latest", lambda db, session_id, alias: run)

    res = client.post(url("CON"), content=PNG, headers={"content-type": "image/jpeg"})
    assert res.status_code == 204
    name = run.baseline_image_path.rsplit("/", 1)[1]
    assert name.startswith("_CON-") and name.endswith(".jpg")
    assert (tmp_path / run.baseline_image_path).is_file()


def test_a_reupload_of_another_type_replaces_the_file(client, run, tmp_path):
    client.post(url(), content=PNG, headers={"content-type": "image/png"})
    client.post(url(), content=b"\xff\xd8jpeg", headers={"content-type": "image/jpeg"})

    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert files == [tmp_path / run.baseline_image_path]
    assert run.baseline_image_path.endswith(".jpg")


def test_an_oversized_upload_is_a_413_and_stores_nothing(client, run, tmp_path, monkeypatch):
    from app.routers import baseline_image
    monkeypatch.setattr(baseline_image, "MAX_BYTES", 8)

    res = client.post(url(), content=PNG, headers={"content-type": "image/png"})

    assert res.status_code == 413
    assert run.baseline_image_path is None
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]
