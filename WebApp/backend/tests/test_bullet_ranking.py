"""How Bullet Holes are ranked, on a real (in-memory SQLite) database: a board's
ranks follow when each hole was first seen, not the order the backend heard of
them. A shot the model confirms late, though it was seen early, takes its place
among the earlier ones, and the holes after it move down a rank. A manual hole
is stamped with the moment it is stored, so it ranks last."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers every table on Base)
from app.core.database import Base
from app.models import BulletHole, Session
from app.schemas.bullet_hole import BulletCreate
from app.services import bullets as svc

T0 = datetime(2026, 11, 16, 9, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as db:
        yield db
    engine.dispose()


def make_session(db, status="active"):
    session = Session(id=uuid.uuid4(), name="Range", status=status, started_at=T0)
    db.add(session)
    db.commit()
    return session


def create(db, session, seconds, camera="lane1", source="model", **fields):
    """A hole first seen `seconds` after T0, reported to the backend now: the hole
    and how many OTHER holes of its board moved to a new rank."""
    body = BulletCreate(
        version="v2", first_seen_at=T0 + timedelta(seconds=seconds), position={"x": 1.0, "y": 2.0},
        camera=camera, source=source, **fields,
    )
    return svc.create_bullet(session.id, body, db)


def shoot(db, session, seconds, **kwargs):
    return create(db, session, seconds, **kwargs)[0]


def ranks(db, session, camera="lane1"):
    """(seconds after T0, rank) of the board's stored holes, in rank order, read
    from the database rather than from holes the test already holds."""
    db.expire_all()
    rows = db.query(BulletHole).filter(
        BulletHole.session_id == session.id, BulletHole.camera_alias == camera, BulletHole.deleted_at.is_(None),
    ).order_by(BulletHole.rank).all()
    return [(int((r.first_seen_at - T0).total_seconds()), r.rank) for r in rows]


def test_holes_reported_in_the_order_they_were_seen_rank_1_2_3(db):
    session = make_session(db)
    for seconds in (5, 10, 15):
        shoot(db, session, seconds)

    assert ranks(db, session) == [(5, 1), (10, 2), (15, 3)]


def test_a_hole_confirmed_late_but_seen_first_takes_rank_1_and_the_others_move_down(db):
    session = make_session(db)
    shoot(db, session, 10)   # confirmed first, seen second
    shoot(db, session, 15)
    late = shoot(db, session, 5)   # seen first, confirmed last

    assert late.rank == 1
    assert ranks(db, session) == [(5, 1), (10, 2), (15, 3)]


def test_a_hole_seen_between_two_stored_ones_slots_in_between(db):
    session = make_session(db)
    shoot(db, session, 5)
    shoot(db, session, 20)
    middle = shoot(db, session, 12)

    assert middle.rank == 2
    assert ranks(db, session) == [(5, 1), (12, 2), (20, 3)]


def test_two_holes_first_seen_at_the_same_moment_keep_their_arrival_order(db):
    session = make_session(db)
    first = shoot(db, session, 7)
    second = shoot(db, session, 7)

    assert (first.rank, second.rank) == (1, 2)
    db.refresh(first)
    assert first.rank == 1


def test_each_board_is_ranked_on_its_own(db):
    session = make_session(db)
    shoot(db, session, 10, camera="lane1")
    shoot(db, session, 10, camera="lane2")
    shoot(db, session, 5, camera="lane1")   # moves only lane1's holes

    assert ranks(db, session, "lane1") == [(5, 1), (10, 2)]
    assert ranks(db, session, "lane2") == [(10, 1)]


def test_the_sessions_hole_list_reads_in_rank_order(db):
    session = make_session(db)
    for seconds in (10, 15, 5):
        shoot(db, session, seconds)
    db.expire_all()

    loaded = db.get(Session, session.id)
    assert [b.rank for b in loaded.bullet_holes] == [1, 2, 3]
    assert [b.rank for b in loaded.active_bullet_holes] == [1, 2, 3]


def test_a_deleted_hole_is_left_out_of_the_numbering(db):
    session = make_session(db)
    a, b, c = (shoot(db, session, s) for s in (5, 10, 15))
    svc.delete_bullet(session.id, b.id, db)
    late = shoot(db, session, 7)   # seen between a and the deleted b

    assert late.rank == 2
    assert ranks(db, session) == [(5, 1), (7, 2), (15, 3)]


def test_a_manual_hole_is_stamped_now_and_ranks_last_whatever_time_the_client_sends(db):
    session = make_session(db)
    shoot(db, session, 5)
    shoot(db, session, 10)
    session.status = "completed"
    db.commit()
    before = datetime.now(timezone.utc)

    # The client claims the hole was seen long ago: the backend stamps its own clock
    manual = shoot(db, session, -10_000_000, source="manual")

    assert manual.rank == 3
    assert before - timedelta(seconds=1) <= manual.first_seen_at <= datetime.now(timezone.utc) + timedelta(seconds=1)
    assert [r for _, r in ranks(db, session)] == [1, 2, 3]


def test_manual_holes_added_one_after_another_keep_the_order_added(db):
    session = make_session(db)
    shoot(db, session, 5)
    session.status = "completed"
    db.commit()
    added = [shoot(db, session, 0, source="manual") for _ in range(3)]

    assert [h.rank for h in added] == [2, 3, 4]


def test_ranks_stored_out_of_time_order_before_this_change_are_put_right_by_the_next_hole(db):
    session = make_session(db)
    # Ranked by arrival, as every Session was before: the later shot holds rank 1
    for rank, seconds in ((1, 20), (2, 10)):
        db.add(BulletHole(
            id=uuid.uuid4(), session_id=session.id, camera_alias="lane1", first_seen_at=T0 + timedelta(seconds=seconds),
            position_x=1.0, position_y=2.0, source="model", rank=rank,
        ))
    db.commit()

    shoot(db, session, 30)

    assert ranks(db, session) == [(10, 1), (20, 2), (30, 3)]


def test_a_hole_says_how_many_other_holes_it_moved(db):
    session = make_session(db)
    assert create(db, session, 10)[1] == 0     # the first on its board
    assert create(db, session, 15)[1] == 0     # the newest: nothing moves
    assert create(db, session, 5)[1] == 2      # seen before both: both move down
    assert create(db, session, 20)[1] == 0
    assert create(db, session, 12)[1] == 2     # between: only the two after it (15 and 20) move down
    assert ranks(db, session) == [(5, 1), (10, 2), (12, 3), (15, 4), (20, 5)]


def test_a_manual_hole_a_retried_one_and_a_hole_on_another_board_move_no_other_hole(db):
    session = make_session(db)
    create(db, session, 5, idempotency_key="k1")
    create(db, session, 10, camera="lane2")
    assert create(db, session, 3, camera="lane2")[1] == 1             # lane2's own later hole moves
    assert create(db, session, 5, idempotency_key="k1")[1] == 0       # a retry changes nothing
    session.status = "completed"
    db.commit()
    assert create(db, session, 0, source="manual")[1] == 0            # stamped now: the newest


def test_a_hole_reported_again_with_the_same_key_changes_no_rank(db):
    session = make_session(db)
    shoot(db, session, 10, idempotency_key="k1")
    shoot(db, session, 20)
    again = shoot(db, session, 10, idempotency_key="k1")

    assert again.rank == 1
    assert ranks(db, session) == [(10, 1), (20, 2)]
