"""The log export: the whole log folder, zipped, for support (routers/logs.py)."""
import io
import zipfile

from app.config.settings import settings


def test_export_zips_every_file_in_the_log_folder(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    (tmp_path / "backend.log").write_text('{"message":"today"}\n')
    (tmp_path / "backend.log.2026-11-01").write_text('{"message":"a past day"}\n')
    (tmp_path / "frontend.log").write_text('{"message":"app"}\n')

    res = client.get("/logs/export")

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert res.headers["content-disposition"].startswith('attachment; filename="kanat-logs-')
    names = set(zipfile.ZipFile(io.BytesIO(res.content)).namelist())
    assert names == {"backend.log", "backend.log.2026-11-01", "frontend.log"}


def test_export_of_a_missing_folder_is_an_empty_zip(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "log_dir", str(tmp_path / "nope"))

    res = client.get("/logs/export")

    assert res.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(res.content)).namelist() == []
