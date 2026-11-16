"""Exporting a Session's results (routers/export.py): refused while it is still
active, so no one hands out a report of a live Session."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routers import export as export_router
from app.services import export as export_svc


@pytest.mark.parametrize("fmt", ["pdf", "csv", "excel"])
def test_exporting_an_active_session_is_refused(client, monkeypatch, fmt):
    session_id = uuid.uuid4()
    active = SimpleNamespace(id=session_id, name="Range A", status="active")
    # The router bound get_session_detail by name, so patch it on the router
    monkeypatch.setattr(export_router, "get_session_detail", lambda sid, db: active)

    res = client.get(f"/sessions/{session_id}/export/{fmt}")

    assert res.status_code == 409
    assert "close it before exporting" in res.json()["detail"]


def _hole(rank, alias, x, y, *, source="model", target_index=0, x_mm=1.0, y_mm=2.0, second=0):
    return SimpleNamespace(
        rank=rank, camera_alias=alias, position_x=x, position_y=y,
        target_index=target_index, x_mm=x_mm, y_mm=y_mm, source=source,
        first_seen_at=datetime(2026, 11, 16, 9, 30, second, tzinfo=timezone.utc),
    )


def _completed_session():
    return SimpleNamespace(
        name="Range A", status="completed",
        started_at=datetime(2026, 11, 16, 9, 30, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 11, 16, 9, 42, 0, tzinfo=timezone.utc),
        bullet_holes=[
            _hole(1, "lane1", 700, 500, second=5),
            _hole(2, "lane1", 720, 520, second=12),
            _hole(1, "lane2", 400, 300, source="manual", second=8),
        ],
    )


def test_the_pdf_report_html_has_the_session_times_each_bullets_timestamp_and_mpi():
    html = export_svc._render_report_html(_completed_session())

    # The Session's own date and time, both ends, each under its readout label
    assert "Started" in html and "Ended" in html
    assert "2026-11-16 09:30:00" in html and "2026-11-16 09:42:00" in html
    # A full timestamp (date and time) for a bullet, not only the time of day
    assert "2026-11-16 09:30:05" in html
    # MPI (Group statistics) is present and labelled
    assert "Group statistics (MPI)" in html and "MPI X (mm)" in html


def test_the_pdf_report_shows_the_target_picture_with_a_marker_per_bullet():
    html = export_svc._render_report_html(_completed_session())

    # The Target picture is embedded (one data URI, reused per board)
    assert "data:image/png;base64," in html
    # A placed marker per bullet, each positioned as a percentage of the artwork
    assert html.count('class="hole"') == 3
    # lane1's first hole at (700, 500) maps to ~49.8% / ~44.6% of 1405 x 1120
    assert "left: 49.822%" in html and "top: 44.643%" in html


def test_the_pdf_report_is_organised_by_board():
    html = export_svc._render_report_html(_completed_session())

    assert html.count('class="board"') == 2
    assert "lane1" in html and "lane2" in html


def test_the_pdf_shot_log_has_no_source_column():
    html = export_svc._render_report_html(_completed_session())

    # Source was dropped from the shot log; the shot columns are # / time / X / Y
    assert "Source" not in html
    assert "Detected at (UTC)" in html


def test_the_csv_drops_source_and_appends_the_mpi_table():
    text = export_svc.generate_csv(_completed_session())
    lines = text.splitlines()

    # The shots header no longer carries a source column
    assert lines[0] == "board,rank,first_seen_at,position_x,position_y"
    # A second table with the Group statistics (MPI) is appended
    assert "mpi_x_mm,mpi_y_mm" in text
    assert "Target 1" in text


def test_the_excel_bullet_sheet_drops_source_and_mpi_lives_in_the_groups_sheet():
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(export_svc.generate_excel(_completed_session())))

    bullet_headers = [c.value for c in wb["Bullet Holes"][1]]
    assert "Source" not in bullet_headers
    assert bullet_headers == ["Board", "#", "Detected At (UTC)", "Position X", "Position Y"]
    # MPI is on the Groups sheet
    assert "MPI X (mm)" in [c.value for c in wb["Groups"][1]]
