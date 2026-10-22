"""A completed Session's Groups (SOW 2.1.3, #247) in GET /sessions/{id}, with
the database replaced. The points are those of the Detection Service's own
tests/test_groups.py, so the two ports of the arithmetic cannot drift apart."""
import io
import math
import uuid
from types import SimpleNamespace

import openpyxl

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.main import app
from app.repositories import sessions as sessions_repo
from app.services import export
from tests.fakes import NOW
from tests.test_schema import URL, alembic_config, db_url  # noqa: F401 (db_url is a fixture)

SESSION_ID = uuid.uuid4()


class FakeDB:
    def close(self):
        pass


def on(target, x, y, source="model"):
    return {"target_index": target, "x_mm": x, "y_mm": y, "source": source}


MISS = on(None, None, None)
MANUAL = on(None, None, None, source="manual")
# A 6 x 8 mm rectangle around (10, -5) plus its centre: every corner is a 3-4-5
# triangle away from the MPI, so the distances are 5, 5, 5, 5 and 0
RECTANGLE = [on(0, 13, -1), on(0, 7, -1), on(0, 13, -9), on(0, 7, -9), on(0, 10, -5)]


@pytest.fixture
def client(monkeypatch):
    """GET /sessions/{SESSION_ID} answers a completed Session holding `client.holes`."""
    def get_with_bullets(db, session_id):
        holes = [
            SimpleNamespace(id=uuid.uuid4(), session_id=SESSION_ID, rank=rank, first_seen_at=NOW,
                            position_x=700.0, position_y=560.0, created_at=NOW, **fields)
            for rank, fields in enumerate(c.holes, start=1)
        ]
        return SimpleNamespace(
            id=SESSION_ID, name="Range 1", status="completed", started_at=NOW, ended_at=NOW,
            record=False, camera_id=None, created_at=NOW, bullet_holes=holes, active_bullet_holes=holes,
        )

    monkeypatch.setattr(sessions_repo, "get_with_bullets", get_with_bullets)
    app.dependency_overrides[get_db] = FakeDB
    with TestClient(app) as c:
        c.holes = []
        yield c
    app.dependency_overrides.clear()


def grouping(client, holes):
    client.holes = holes
    res = client.get(f"/sessions/{SESSION_ID}")
    assert res.status_code == 200
    return res.json()["grouping"]


def test_a_hand_computable_group_gives_known_statistics(client):
    got = grouping(client, RECTANGLE)

    assert got["misses"] == got["without_position"] == 0
    [g] = got["groups"]
    assert g["target_index"] == 0 and g["n"] == 5
    assert (g["mpi_x_mm"], g["mpi_y_mm"]) == pytest.approx((10.0, -5.0))
    assert g["cep_mm"] == pytest.approx(5.0)                   # median of 0, 5, 5, 5, 5
    assert g["mean_radius_mm"] == pytest.approx(4.0)           # 20 / 5
    assert g["rms_radius_mm"] == pytest.approx(math.sqrt(20))  # sqrt(100 / 5)
    assert g["extreme_spread_mm"] == pytest.approx(10.0)       # the rectangle's diagonal


def test_one_bullet_hole_gives_an_mpi_and_no_spread(client):
    [g] = grouping(client, [on(0, 2, -3)])["groups"]

    assert g["n"] == 1
    assert (g["mpi_x_mm"], g["mpi_y_mm"]) == pytest.approx((2.0, -3.0))
    assert g["cep_mm"] is g["mean_radius_mm"] is g["rms_radius_mm"] is g["extreme_spread_mm"] is None


def test_two_targets_are_two_groups_in_target_order(client):
    got = grouping(client, [on(1, 50, 50), on(0, 0, 0), on(0, 6, 8)])["groups"]

    assert [(g["target_index"], g["n"]) for g in got] == [(0, 2), (1, 1)]
    assert (got[0]["mpi_x_mm"], got[0]["mpi_y_mm"]) == pytest.approx((3.0, 4.0))
    assert got[0]["extreme_spread_mm"] == pytest.approx(10.0)


def test_misses_and_bullet_holes_without_a_position_are_in_no_group_and_counted(client):
    # A detected one on a Target without millimetres: no print scale configured
    unscaled = on(0, None, None)
    got = grouping(client, RECTANGLE + [MISS, MISS, MANUAL, unscaled])

    assert (got["misses"], got["without_position"]) == (2, 2)
    [g] = got["groups"]
    assert g["n"] == 5
    assert (g["mpi_x_mm"], g["mpi_y_mm"]) == pytest.approx((10.0, -5.0))


def test_a_session_without_a_bullet_hole_on_a_target_has_no_group(client):
    assert grouping(client, [MISS, MANUAL]) == {"groups": [], "misses": 1, "without_position": 1}
    assert grouping(client, []) == {"groups": [], "misses": 0, "without_position": 0}


def groups_sheet(client):
    res = client.get(f"/sessions/{SESSION_ID}/export/excel")
    assert res.status_code == 200
    return list(openpyxl.load_workbook(io.BytesIO(res.content))["Groups"].iter_rows(values_only=True))


def test_the_excel_groups_sheet_holds_the_detail_numbers(client):
    got = grouping(client, RECTANGLE + [on(1, 2, -3), MISS, MANUAL])

    rows = groups_sheet(client)
    assert rows[1:3] == [
        (f"Target {g['target_index'] + 1}", g["n"], g["mpi_x_mm"], g["mpi_y_mm"], g["cep_mm"],
         g["mean_radius_mm"], g["rms_radius_mm"], g["extreme_spread_mm"])
        for g in got["groups"]
    ]
    assert rows[-2:] == [("Misses", got["misses"]) + (None,) * 6,
                         ("Without a Position", got["without_position"]) + (None,) * 6]


def test_the_pdf_renders_with_a_groups_section(client, monkeypatch):
    rendered = []
    real = export.weasyprint.HTML

    def html(string, base_url):
        rendered.append(string)
        return real(string=string, base_url=base_url)

    monkeypatch.setattr(export.weasyprint, "HTML", html)
    client.holes = RECTANGLE + [MISS]

    res = client.get(f"/sessions/{SESSION_ID}/export/pdf")

    assert res.status_code == 200 and res.content.startswith(b"%PDF")
    [page] = rendered
    assert "<h2>Groups</h2>" in page
    # MPI, CEP, Mean Radius, RMS radius (sqrt 20) and Extreme Spread, to 0.1 mm
    for cell in ("Target 1", "10.0", "-5.0", "5.0", "4.0", "4.5"):
        assert f"<td>{cell}</td>" in page
    assert "Misses: 1" in page


def test_without_a_group_the_pdf_still_gives_the_two_counts(client, monkeypatch):
    rendered = []
    monkeypatch.setattr(export.weasyprint, "HTML",
                        lambda string, base_url: rendered.append(string) or SimpleNamespace(write_pdf=lambda: b"%PDF"))
    client.holes = [MISS, MANUAL, MANUAL]

    assert client.get(f"/sessions/{SESSION_ID}/export/pdf").status_code == 200
    assert "<td>Target" not in rendered[0]
    assert "Misses: 1" in rendered[0] and "Without a Position: 2" in rendered[0]


@pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
def test_a_deleted_bullet_hole_leaves_its_group(db_url):
    """On a real PostgreSQL: only the query keeps a deleted Bullet Hole out."""
    command.upgrade(alembic_config(), "head")
    engine = create_engine(db_url)
    ids = [uuid.uuid4() for _ in range(3)]
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO sessions (id, name, status, started_at, ended_at)"
            " VALUES (:id, 'Range 1', 'completed', now(), now())"
        ), {"id": SESSION_ID})
        for rank, (hole_id, (x, y)) in enumerate(zip(ids, [(0, 0), (6, 8), (60, 80)]), start=1):
            conn.execute(text(
                "INSERT INTO bullet_holes (id, session_id, first_seen_at, position_x, position_y,"
                " target_index, x_mm, y_mm, source, rank)"
                " VALUES (:id, :session, now(), 700, 560, 0, :x, :y, 'model', :rank)"
            ), {"id": hole_id, "session": SESSION_ID, "x": x, "y": y, "rank": rank})

    def real_db():
        with DBSession(engine) as db:
            yield db

    app.dependency_overrides[get_db] = real_db
    try:
        with TestClient(app) as c:
            assert c.delete(f"/sessions/{SESSION_ID}/bullets/{ids[2]}").status_code == 204
            [g] = c.get(f"/sessions/{SESSION_ID}").json()["grouping"]["groups"]
            excel_n = groups_sheet(c)[1][1]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert g["n"] == excel_n == 2
    assert (g["mpi_x_mm"], g["mpi_y_mm"]) == pytest.approx((3.0, 4.0))
    assert g["extreme_spread_mm"] == pytest.approx(10.0)
