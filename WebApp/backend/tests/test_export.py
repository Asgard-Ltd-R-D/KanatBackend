"""Exporting a Session's results (routers/export.py): refused while it is still
active, so no one hands out a report of a live Session."""
import uuid
from datetime import datetime, timedelta, timezone
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


def _moment(utc_text):
    return datetime.strptime(utc_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _local(utc_text):
    """A UTC 'YYYY-MM-DD HH:MM:SS' as this PC's clock reads it."""
    return _moment(utc_text).astimezone().strftime("%Y-%m-%d %H:%M:%S")




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

    # The Session's own date and time, both ends, each under its readout label,
    # converted from the stored UTC to the PC's clock, with no zone label
    assert "Started" in html and "Ended" in html
    assert _local("2026-11-16 09:30:00") in html and _local("2026-11-16 09:42:00") in html
    # A full timestamp (date and time) for a bullet, not only the time of day
    assert _local("2026-11-16 09:30:05") in html
    assert " UTC" not in html and "(UTC)" not in html and ">UTC<" not in html
    # MPI (Group statistics) is present and labelled
    assert "Group statistics (MPI)" in html and "MPI X (mm)" in html


@pytest.mark.parametrize("seconds, expected", [
    (724, "12m 4s"),        # under an hour: minutes and seconds
    (3599, "59m 59s"),
    (3600, "1h 0m 0s"),     # from an hour on: hours, never 60m+
    (7509, "2h 5m 9s"),
])
def test_the_pdf_duration_shows_hours_from_the_first_hour_on(seconds, expected):
    started = datetime(2026, 11, 16, 9, 0, 0, tzinfo=timezone.utc)
    session = SimpleNamespace(started_at=started, ended_at=started + timedelta(seconds=seconds))

    assert export_svc._session_duration(session) == expected


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
    assert "Detected at" in html


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
    assert bullet_headers == ["Board", "#", "Detected At", "Position X", "Position Y"]
    # MPI is on the Groups sheet
    assert "MPI X (mm)" in [c.value for c in wb["Groups"][1]]


def test_the_csv_times_are_on_the_pcs_clock_with_no_zone_label():
    lines = export_svc.generate_csv(_completed_session()).splitlines()

    # lane1's first hole was first seen 09:30:05 UTC; the CSV prints this PC's clock
    assert lines[1] == f"lane1,1,{_local('2026-11-16 09:30:05')},700,500"


def test_the_excel_times_are_on_the_pcs_clock_with_no_zone_label():
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(export_svc.generate_excel(_completed_session())))
    rows = [[c.value for c in row] for row in wb["Bullet Holes"].iter_rows(min_row=2)]

    assert rows[0][:3] == ["lane1", 1, _local("2026-11-16 09:30:05")]


def test_the_download_filename_dates_the_session_on_the_pcs_clock():
    # Started 23:30 UTC on the 15th: on a PC east of UTC that is already the 16th
    session = SimpleNamespace(name="Range A", started_at=datetime(2026, 11, 15, 23, 30, 0, tzinfo=timezone.utc))
    expected = _local("2026-11-15 23:30:00")[:10].replace("-", "")

    assert f"_{expected}.pdf" in export_svc._content_disposition(session, "pdf")


def test_an_exported_time_stored_without_a_timezone_is_taken_as_utc():
    naive = datetime(2026, 11, 16, 9, 30, 5)   # the database hands back UTC, whatever the driver does to it

    assert export_svc._local_clock(naive) == _local("2026-11-16 09:30:05")


def test_shots_outside_the_reference_artwork_are_still_plotted():
    # A board watching two printed targets: the second shot sits on the
    # neighbouring target, stored beyond 0-1405 in the reference target's space.
    s = SimpleNamespace(
        name="Range A", status="completed",
        started_at=datetime(2026, 11, 16, 9, 30, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 11, 16, 9, 42, 0, tzinfo=timezone.utc),
        bullet_holes=[
            _hole(1, "lane1", 700, 500, second=5),
            _hole(2, "lane1", 2000, 500, target_index=1, second=9),
        ],
    )
    html = export_svc._render_report_html(s)

    # Neither shot is clipped away by the artwork's bounds
    assert html.count('class="hole"') == 2
    # The canvas widened to cover the far shot, so the artwork is narrower than it
    # (1405 / 2000 = 70.25%)
    assert "width: 70.250%" in html
