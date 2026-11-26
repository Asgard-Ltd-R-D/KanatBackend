"""The baseline frame image stored per Run: uploaded by the Detection Service,
served to the web app. The database is replaced; files go to a temp log dir."""
import io
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config.settings import settings
from app.core.deps import get_db
from app.main import app
from app.repositories import runs as runs_repo
from tests.fakes import FakeDB


def _image(fmt: str) -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (4, 3), (10, 20, 30)).save(out, format=fmt)
    return out.getvalue()


def _decodes_as(data: bytes, fmt: str) -> bool:
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        return image.format == fmt and image.size == (4, 3)


PNG = _image("PNG")
JPEG = _image("JPEG")
SESSION = uuid.uuid4()
TAKEN = datetime(2026, 11, 26, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def run(monkeypatch, tmp_path):
    """The latest Run of camera `cam1` in SESSION, and a temp log dir."""
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    run = SimpleNamespace(session_id=SESSION, camera_alias="cam1", taken_at=TAKEN, baseline_image_path=None)
    monkeypatch.setattr(runs_repo, "get_for_update",
                        lambda db, session_id, alias, taken_at:
                        run if (session_id, alias, taken_at) == (SESSION, "cam1", TAKEN) else None)
    monkeypatch.setattr(runs_repo, "save", lambda db: None)
    return run


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = FakeDB
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def url(alias="cam1", taken_at=None, replace=False):
    """The camera's image URL for the Run taken at `taken_at` (TAKEN by default)."""
    taken = urllib.parse.quote((taken_at or TAKEN).isoformat())
    return f"/sessions/{SESSION}/cameras/{alias}/baseline-image?taken_at={taken}" + ("&replace=true" if replace else "")


def test_an_uploaded_image_is_stored_on_the_latest_run(client, run, tmp_path):
    res = client.post(url(), content=PNG, headers={"content-type": "image/png"})

    assert res.status_code == 204
    assert _decodes_as((tmp_path / run.baseline_image_path).read_bytes(), "PNG")
    assert run.baseline_image_path.startswith(f"baseline-images/{SESSION}/")


def test_the_stored_image_is_served(client, run):
    client.post(url(), content=PNG, headers={"content-type": "image/png"})

    res = client.get(url())

    assert res.status_code == 200
    assert _decodes_as(res.content, "PNG")
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
    monkeypatch.setattr(runs_repo, "get_for_update", lambda db, session_id, alias, taken_at: run)

    res = client.post(url("CON"), content=JPEG, headers={"content-type": "image/jpeg"})
    assert res.status_code == 204
    name = run.baseline_image_path.rsplit("/", 1)[1]
    assert name.startswith("_CON-") and name.endswith(".jpg")
    assert (tmp_path / run.baseline_image_path).is_file()


def test_a_reupload_of_another_type_replaces_the_file(client, run, tmp_path):
    client.post(url(), content=PNG, headers={"content-type": "image/png"})
    client.post(url(replace=True), content=JPEG, headers={"content-type": "image/jpeg"})

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


def test_a_reupload_succeeds_when_the_prior_file_is_already_gone(client, run, tmp_path):
    client.post(url(), content=PNG, headers={"content-type": "image/png"})
    (tmp_path / run.baseline_image_path).unlink()

    res = client.post(url(replace=True), content=JPEG, headers={"content-type": "image/jpeg"})

    assert res.status_code == 204
    assert _decodes_as((tmp_path / run.baseline_image_path).read_bytes(), "JPEG")


@pytest.mark.parametrize("body", [
    b'<svg xmlns="http://www.w3.org/2000/svg"><image href="http://169.254.169.254/x"/></svg>',
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
    b"not an image",
])
def test_a_body_that_is_not_a_real_png_or_jpeg_is_a_415_and_stores_nothing(client, run, tmp_path, body):
    # Labelled image/png, but an SVG (which the PDF renderer would parse), a
    # truncated PNG or plain bytes: only a decodable PNG or JPEG is stored
    res = client.post(url(), content=body, headers={"content-type": "image/png"})

    assert res.status_code == 415
    assert run.baseline_image_path is None
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_a_stored_image_is_reencoded_dropping_trailing_bytes(client, run, tmp_path):
    client.post(url(), content=PNG + b"<svg/>", headers={"content-type": "image/png"})

    assert b"<svg" not in (tmp_path / run.baseline_image_path).read_bytes()


def test_an_upload_for_a_run_is_stored_on_that_run_only(client, run):
    assert client.post(url(), content=PNG, headers={"content-type": "image/png"}).status_code == 204
    assert run.baseline_image_path is not None
    assert client.get(url()).status_code == 200


def test_an_upload_for_a_run_that_is_not_there_is_a_404(client, run):
    # A frame captured for an older Run, uploaded after a retake made a newer
    # one, is not stored on the newer Run
    res = client.post(url(taken_at=TAKEN - timedelta(seconds=30)), content=PNG,
                      headers={"content-type": "image/png"})

    assert res.status_code == 404
    assert run.baseline_image_path is None


def test_an_upload_or_read_without_the_run_is_a_422(client, run):
    bare = f"/sessions/{SESSION}/cameras/cam1/baseline-image"
    assert client.post(bare, content=PNG, headers={"content-type": "image/png"}).status_code == 422
    assert client.get(bare).status_code == 422


def test_two_uploads_for_one_run_never_share_a_file(client, run, tmp_path):
    client.post(url(), content=PNG, headers={"content-type": "image/png"})
    first = run.baseline_image_path
    client.post(url(replace=True), content=PNG, headers={"content-type": "image/png"})

    # A new file each time, the replaced one removed only after the new one is recorded
    assert run.baseline_image_path != first
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == [tmp_path / run.baseline_image_path]


def test_a_failed_save_keeps_the_previous_image(client, run, tmp_path, monkeypatch):
    client.post(url(), content=PNG, headers={"content-type": "image/png"})
    before = run.baseline_image_path

    def fail(db):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(runs_repo, "save", fail)
    with pytest.raises(RuntimeError):
        client.post(url(replace=True), content=JPEG, headers={"content-type": "image/jpeg"})

    assert [p for p in tmp_path.rglob("*") if p.is_file()] == [tmp_path / before]


def test_a_stored_png_carries_no_icc_profile(client, run, tmp_path):
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (4, 3)).save(out, format="PNG", icc_profile=b"untrusted profile bytes")

    client.post(url(), content=out.getvalue(), headers={"content-type": "image/png"})

    with Image.open(tmp_path / run.baseline_image_path) as stored:
        assert "icc_profile" not in stored.info


def test_a_second_upload_for_a_run_without_replace_is_a_409_and_keeps_the_first(client, run, tmp_path):
    # Another tab opened later captures the live picture for the same Run
    client.post(url(), content=PNG, headers={"content-type": "image/png"})
    first = run.baseline_image_path

    res = client.post(url(), content=JPEG, headers={"content-type": "image/jpeg"})

    assert res.status_code == 409
    assert run.baseline_image_path == first
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == [tmp_path / first]
