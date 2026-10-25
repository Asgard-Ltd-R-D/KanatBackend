import asyncio
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.config.settings import settings
from app.services import camera_sync, mediamtx
from app.services import recordings as recording_svc
from tests.fakes import NOW, FakeMediaMTX, make_camera

# The real reader, kept before conftest swaps it for a stand-in in each test
read_config_paths = mediamtx.config_paths


# --- recording follows the sessions ---

def test_starting_to_record_patches_only_record(monkeypatch, db_state):
    # Patching record alone does not restart the camera's GStreamer
    db_state.cameras, db_state.record = [make_camera()], True
    mtx = FakeMediaMTX(monkeypatch, {"cam1": camera_sync.path_config(make_camera(), record=False)})

    camera_sync.sync(None)

    assert mtx.calls == [("patch", "cam1", ["record"])]


def test_a_disabled_camera_keeps_a_path_its_recordings_play_from(monkeypatch, db_state):
    # MediaMTX's playback server only plays recordings of a configured path
    db_state.cameras = [make_camera(enabled=False)]
    mtx = FakeMediaMTX(monkeypatch, {"cam1": camera_sync.path_config(make_camera(), record=False)})

    camera_sync.sync(None)

    assert mtx.paths["cam1"]["runOnInit"] == ""  # GStreamer stops
    assert mtx.paths["cam1"]["record"] is False


def test_a_deleted_camera_that_was_disabled_loses_its_path_too(monkeypatch, db_state):
    mtx = FakeMediaMTX(monkeypatch, {"cam1": camera_sync.playback_only_config()})

    camera_sync.sync(None)

    assert mtx.calls == [("delete", "cam1")]


def test_a_mediamtx_yml_path_with_a_cameras_settings_is_still_never_touched(monkeypatch, db_state):
    # Same settings as a disabled camera's path, but mediamtx.yml defines it
    monkeypatch.setattr(mediamtx, "config_paths", lambda: mediamtx.ConfigPaths(frozenset({"static"})))
    mtx = FakeMediaMTX(monkeypatch, {"static": camera_sync.playback_only_config()})

    camera_sync.sync(None)                      # no camera: not deleted
    db_state.cameras = [make_camera("static")]
    camera_sync.sync(None)                      # a camera of that name: not patched
    assert mtx.calls == []


def test_without_mediamtx_yml_the_sync_changes_no_path(monkeypatch, db_state):
    # Unreadable, or a regexp not trusted: any name might be one of its paths,
    # which MediaMTX lists only under the regexp
    monkeypatch.setattr(mediamtx, "config_paths", lambda: None)
    monkeypatch.setattr(camera_sync, "_config_unknown", False)
    mtx = FakeMediaMTX(monkeypatch, {
        "~^external[[:digit:]]+$": camera_sync.path_config(make_camera("external"), record=False),
        "stale": camera_sync.path_config(make_camera("stale"), record=False),
        "cam1": camera_sync.playback_only_config(),
    })
    db_state.cameras = [make_camera("external1"), make_camera("cam1")]

    camera_sync.sync(None)

    assert mtx.calls == []      # nothing added, patched or deleted
    monkeypatch.setattr(mediamtx, "config_paths", lambda: mediamtx.ConfigPaths())
    camera_sync.sync(None)      # known again: applied
    assert ("add", "external1") in [call[:2] for call in mtx.calls]


def test_recording_intervals_follow_the_record_switch_and_the_session(monkeypatch):
    from app.models import Session
    from app.services import sessions as session_svc

    t0 = NOW - timedelta(hours=1)
    session = Session(status="active", record=True, started_at=t0, ended_at=None)
    session_svc._follow_recording(session, t0)                       # started recording
    assert [(i.started_at, i.ended_at) for i in session.recording_intervals] == [(t0, None)]

    session.record = False
    session_svc._follow_recording(session, t0 + timedelta(minutes=5))  # switched off
    session.record = True
    session_svc._follow_recording(session, t0 + timedelta(minutes=8))  # on again
    session.status, session.ended_at = "completed", t0 + timedelta(minutes=20)
    session_svc._follow_recording(session, t0 + timedelta(minutes=21))  # ended

    assert [(i.started_at, i.ended_at) for i in session.recording_intervals] == [
        (t0, t0 + timedelta(minutes=5)),
        (t0 + timedelta(minutes=8), t0 + timedelta(minutes=20)),
    ]


def test_deleting_a_session_locks_it_before_reading_its_recording_windows(monkeypatch):
    # A recording switched on at the same moment then either commits before the
    # windows are read, or waits and finds the session gone
    from app.models import RecordingInterval
    from app.repositories import sessions as sessions_repo
    from app.services import sessions as session_svc

    t0 = NOW - timedelta(hours=1)
    session = SimpleNamespace(name="Range A", recording_intervals=[RecordingInterval(started_at=t0, ended_at=t0 + timedelta(minutes=5))])
    deleted = []
    monkeypatch.setattr(sessions_repo, "get", lambda db, session_id: pytest.fail("read without the lock"))
    monkeypatch.setattr(sessions_repo, "get_for_update", lambda db, session_id: session)
    monkeypatch.setattr(sessions_repo, "delete", lambda db, s: deleted.append(s))

    assert session_svc.delete_session(uuid.uuid4(), None) == [(t0, t0 + timedelta(minutes=5))]
    assert deleted == [session]

    monkeypatch.setattr(sessions_repo, "get_for_update", lambda db, session_id: None)
    with pytest.raises(HTTPException) as gone:
        session_svc.delete_session(uuid.uuid4(), None)
    assert gone.value.status_code == 404


# --- a session's recordings ---

def test_recordings_are_cut_to_the_session(monkeypatch):
    start, end = NOW - timedelta(minutes=10), NOW
    spans = {
        # began a minute before the session, ran 3 minutes
        "cam1": [{"start": (start - timedelta(minutes=1)).isoformat(), "duration": 180.0}],
        "cam2": [],
    }
    monkeypatch.setattr(mediamtx, "list_recordings", lambda alias, s, e: spans[alias])

    result = recording_svc.session_recordings([(start, end)], [make_camera("cam1"), make_camera("cam2")])

    assert [r.alias for r in result] == ["cam1"]
    assert result[0].spans[0].start == start
    assert result[0].spans[0].duration_s == 120.0


def test_a_long_recording_is_offered_in_parts(monkeypatch):
    start = NOW - timedelta(minutes=25)
    monkeypatch.setattr(mediamtx, "list_recordings", lambda alias, s, e: [{"start": start.isoformat(), "duration": 1500.0}])

    spans = recording_svc.session_recordings([(start, NOW)], [make_camera()])[0].spans

    assert [s.duration_s for s in spans] == [600.0, 600.0, 300.0]
    assert spans[1].start == start + timedelta(minutes=10)


# --- replaying a part ---

class FakeVideo:
    def iter_bytes(self):
        yield b"mp4 "
        yield b"bytes"

    def close(self):
        pass


def test_a_replayed_part_is_fetched_once_however_many_ask(monkeypatch, tmp_path):
    # The player asks for several byte ranges of a part at the same time
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path))
    fetched = []

    def open_recording(alias, start, duration_s):
        fetched.append(alias)
        return FakeVideo()

    monkeypatch.setattr(mediamtx, "open_recording", open_recording)
    paths = []
    threads = [
        threading.Thread(target=lambda: paths.append(recording_svc.replay_file("cam1", NOW, 12.5, still_allowed=lambda: True)))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert fetched == ["cam1"]
    assert len(set(paths)) == 1
    assert paths[0].read_bytes() == b"mp4 bytes"


class BrokenVideo:
    """A playback download that fails halfway, as when MediaMTX restarts."""

    def iter_bytes(self):
        yield b"half a "
        raise httpx.ReadError("connection lost")

    def close(self):
        pass


def test_a_download_that_breaks_leaves_no_file_and_reports_unreachable(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path))
    monkeypatch.setattr(mediamtx, "open_recording", lambda alias, start, duration_s: BrokenVideo())

    with pytest.raises(mediamtx.MediaMTXUnreachable):
        recording_svc.replay_file("cam1", NOW, 10.0, still_allowed=lambda: True)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("alias, offset_s, duration_s, status", [
    ("cam1", 60, 120.0, 200),                                # the part listed for this session
    ("loopdemo", 60, 120.0, 404),                            # another path recording then: not listed
    ("cam1", 61, 120.0, 404),                                # another stretch of the camera
    ("cam1", 60, 300.0, 404),                                # a longer stretch
    ("cam1", 60, recording_svc.MAX_PART_S + 1, 422),         # longer than any part offered
])
def test_only_a_part_listed_for_the_session_is_served(monkeypatch, tmp_path, alias, offset_s, duration_s, status):
    from fastapi.testclient import TestClient
    from app.core.deps import get_db
    from app.main import app
    from app.services import cameras as camera_svc
    from app.services import sessions as session_svc

    start = NOW - timedelta(minutes=10)
    recorded = SimpleNamespace(recording_intervals=[SimpleNamespace(started_at=start, ended_at=NOW)])
    monkeypatch.setattr(session_svc, "get_session_or_404", lambda sid, db: recorded)
    monkeypatch.setattr(camera_svc, "list_cameras", lambda db: [make_camera("cam1")])
    # Every path recorded the same stretch, cam1 and mediamtx.yml's loopdemo alike
    span = {"start": (start + timedelta(seconds=60)).isoformat(), "duration": 120.0}
    monkeypatch.setattr(mediamtx, "list_recordings", lambda path, s, e: [span])
    part = tmp_path / "part.mp4"
    part.write_bytes(b"video")
    monkeypatch.setattr(recording_svc, "replay_file", lambda alias, start, duration_s, still_allowed: part)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(close=lambda: None)
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/sessions/{uuid.uuid4()}/recordings/{alias}/video",
                params={"start": (start + timedelta(seconds=offset_s)).isoformat(), "duration_s": duration_s},
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == status


def test_deleting_a_sessions_video_holds_no_database_connection(monkeypatch):
    # The video's deletion may wait for a replay download: by then the
    # request's session is closed, the other sessions' windows already read
    from fastapi.testclient import TestClient
    from app.core.deps import get_db
    from app.main import app
    from app.services import sessions as session_svc

    request_db = SimpleNamespace(open=True)
    request_db.close = lambda: setattr(request_db, "open", False)
    mine, others = [(NOW - timedelta(hours=1), NOW)], [(NOW - timedelta(hours=3), NOW - timedelta(hours=2))]
    # A completed Session: no Run to end
    monkeypatch.setattr(session_svc, "get_session_or_404", lambda sid, db: SimpleNamespace(status="completed"))
    monkeypatch.setattr(session_svc, "delete_session", lambda sid, db: mine)
    monkeypatch.setattr(camera_sync, "sync_soon", lambda db: None)
    monkeypatch.setattr(session_svc, "other_recorded_windows", lambda sid, db: db.open and others)
    deleted = []

    def delete_session_video(windows, other_windows):
        assert not request_db.open
        deleted.append((windows, other_windows))

    monkeypatch.setattr(recording_svc, "delete_session_video", delete_session_video)
    app.dependency_overrides[get_db] = lambda: request_db
    try:
        with TestClient(app) as client:
            res = client.delete(f"/sessions/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 204 and deleted == [(mine, others)]


def test_a_replay_download_holds_no_database_connection(monkeypatch, tmp_path):
    # The request's session is closed before the part is fetched, and the
    # check under the part's lock uses a session of its own, just for it
    from contextlib import contextmanager

    from fastapi.testclient import TestClient
    from app.core.deps import get_db
    from app.main import app
    from app.repositories import sessions as sessions_repo
    from app.routers import recordings as recordings_router
    from app.services import cameras as camera_svc
    from app.services import sessions as session_svc

    start = NOW - timedelta(minutes=10)
    recorded = SimpleNamespace(recording_intervals=[SimpleNamespace(started_at=start, ended_at=NOW)])
    monkeypatch.setattr(session_svc, "get_session_or_404", lambda sid, db: recorded)
    monkeypatch.setattr(camera_svc, "list_cameras", lambda db: [make_camera("cam1")])
    monkeypatch.setattr(mediamtx, "list_recordings", lambda path, s, e: [{"start": start.isoformat(), "duration": 600.0}])
    request_db = SimpleNamespace(open=True)
    request_db.close = lambda: setattr(request_db, "open", False)
    check_db = SimpleNamespace(open=False)

    @contextmanager
    def short_db():
        check_db.open = True
        yield check_db
        check_db.open = False

    monkeypatch.setattr(recordings_router, "short_db", short_db)
    monkeypatch.setattr(sessions_repo, "exists", lambda db, sid: db is check_db and db.open)
    part = tmp_path / "part.mp4"
    part.write_bytes(b"video")

    def replay_file(alias, start, duration_s, still_allowed):
        assert not request_db.open        # released before the download
        assert still_allowed()
        assert not check_db.open          # and the check's session closed after it
        return part

    monkeypatch.setattr(recording_svc, "replay_file", replay_file)
    app.dependency_overrides[get_db] = lambda: request_db
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/sessions/{uuid.uuid4()}/recordings/cam1/video",
                params={"start": start.isoformat(), "duration_s": 600.0},
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200 and res.content == b"video"


# --- deleting a session's video ---

def _recording(folder, began):
    """A recording file named as MediaMTX names it: its start, in local time."""
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / f"{began.astimezone().strftime('%Y-%m-%d_%H-%M-%S-%f')}.mp4"
    file.write_bytes(b"video")
    return file


def test_deleting_a_session_deletes_only_its_own_video(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path / "recordings"))
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(mediamtx, "config_paths", lambda: mediamtx.ConfigPaths(frozenset({"loopdemo"})))
    start = NOW - timedelta(hours=1)
    window = (start, start + timedelta(minutes=20))

    inside = _recording(tmp_path / "recordings" / "cam1", start + timedelta(minutes=5))
    other_camera = _recording(tmp_path / "recordings" / "cam2", start + timedelta(minutes=6))
    # A camera deleted since: its folder no camera row names any more
    renamed = _recording(tmp_path / "recordings" / "old-name", start + timedelta(minutes=4))
    # mediamtx.yml's own path: MediaMTX keeps and expires it
    static = _recording(tmp_path / "recordings" / "loopdemo", start + timedelta(minutes=8))
    before = _recording(tmp_path / "recordings" / "cam1", start - timedelta(minutes=30))
    after = _recording(tmp_path / "recordings" / "cam1", start + timedelta(minutes=40))
    # Starts in this Session but runs on into another one: kept for the other
    shared = _recording(tmp_path / "recordings" / "cam1", start + timedelta(minutes=15))
    other_session = (start + timedelta(minutes=16), start + timedelta(minutes=30))

    cache = tmp_path / "cache"
    cache.mkdir()
    stamp = (start + timedelta(minutes=5)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    copy = cache / f"cam1_{stamp}_60.000.mp4"
    copy.write_bytes(b"video")
    renamed_copy = cache / f"old-name_{stamp}_60.000.mp4"
    renamed_copy.write_bytes(b"video")

    deleted = recording_svc.delete_session_video([window], [other_session])

    assert deleted == 3
    assert not inside.exists() and not other_camera.exists() and not renamed.exists()
    assert not copy.exists() and not renamed_copy.exists()
    assert before.exists() and after.exists() and shared.exists() and static.exists()


def test_a_segment_two_sessions_shared_goes_with_the_last_of_them(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path / "recordings"))
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path / "cache"))
    start = NOW - timedelta(hours=1)
    # One 10-minute segment from +0: A records +0..+5, B records +3..+20
    shared = _recording(tmp_path / "recordings" / "cam1", start)
    a = (start, start + timedelta(minutes=5))
    b = (start + timedelta(minutes=3), start + timedelta(minutes=20))

    assert recording_svc.delete_session_video([a], [b]) == 0   # A deleted: B still needs it
    assert shared.exists()
    assert recording_svc.delete_session_video([b], []) == 1    # B deleted: nobody does
    assert not shared.exists()


def test_a_session_that_did_not_record_deletes_and_replays_nothing(monkeypatch, tmp_path):
    # Two sessions at once: the other one records, this one never did, so the
    # footage in this one's time is the other's alone
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path / "recordings"))
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path / "cache"))
    start = NOW - timedelta(hours=1)
    others = _recording(tmp_path / "recordings" / "cam1", start + timedelta(minutes=5))
    monkeypatch.setattr(mediamtx, "list_recordings", lambda alias, s, e: [{"start": start.isoformat(), "duration": 600.0}])

    assert recording_svc.session_recordings([], [make_camera()]) == []
    assert recording_svc.delete_session_video([], [(start, start + timedelta(minutes=20))]) == 0
    assert others.exists()


def test_with_mediamtx_yml_unreadable_no_recording_folder_is_touched(monkeypatch, tmp_path):
    # Which folders are MediaMTX's own is unknown, so none is deleted from
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path / "recordings"))
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(mediamtx, "config_paths", lambda: None)
    start = NOW - timedelta(days=2)
    inside = _recording(tmp_path / "recordings" / "static", start + timedelta(minutes=5))

    assert recording_svc.delete_session_video([(start, start + timedelta(minutes=20))], []) == 0
    assert recording_svc.remove_unused_recordings([]) == 0
    assert inside.exists()


def test_without_a_recordings_folder_deleting_a_session_skips_its_files(monkeypatch):
    # e.g. the backend in a container, where the repo layout is not there
    monkeypatch.setattr(settings, "recordings_dir", "")
    monkeypatch.setattr(recording_svc, "_recordings_dir", lambda: None)

    assert recording_svc.delete_session_video([(NOW, NOW)], []) == 0


def test_day_old_recordings_of_a_removed_camera_are_deleted(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path))
    old = _recording(tmp_path / "gone", NOW - timedelta(days=2))
    recent = _recording(tmp_path / "gone", NOW - timedelta(hours=1))
    kept = _recording(tmp_path / "cam1", NOW - timedelta(days=2))  # still a camera: MediaMTX expires it

    assert recording_svc.remove_unused_recordings(["cam1"]) == 1
    assert not old.exists() and recent.exists() and kept.exists()


# --- daylight saving ---

def test_the_repeated_hour_at_the_end_of_daylight_saving_is_read_from_the_write_time(monkeypatch, tmp_path):
    # Israel, 25 Oct 2026: 02:00 goes back to 01:00, so 01:30 happens twice
    monkeypatch.setenv("TZ", "Asia/Jerusalem")
    time.tzset()
    try:
        file = tmp_path / "2026-10-25_01-30-00-000000.mp4"
        file.write_bytes(b"video")
        second = datetime(2026, 10, 24, 23, 30, tzinfo=timezone.utc)  # 01:30 +02:00
        first = datetime(2026, 10, 24, 22, 30, tzinfo=timezone.utc)   # 01:30 +03:00

        written = (second + timedelta(minutes=5)).timestamp()
        os.utime(file, (written, written))
        assert recording_svc._file_start(file) == second

        written = (first + timedelta(minutes=5)).timestamp()
        os.utime(file, (written, written))
        assert recording_svc._file_start(file) == first
    finally:
        monkeypatch.undo()
        time.tzset()


# --- the replay cache ---

def test_the_replay_cache_drops_the_least_recently_played_beyond_its_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "replay_cache_max_gb", 25 / 1024**3)  # 25 bytes
    now = time.time()
    for name, age in [("old", 300), ("mid", 200), ("new", 100)]:
        file = tmp_path / f"{name}.mp4"
        file.write_bytes(b"x" * 10)
        os.utime(file, (now - age, now - age))
    abandoned = tmp_path / "gone.part"
    abandoned.write_bytes(b"x")
    os.utime(abandoned, (now - 7200, now - 7200))

    recording_svc._prune_cache(tmp_path)

    assert sorted(f.name for f in tmp_path.iterdir()) == ["mid.mp4", "new.mp4"]


def test_a_copy_goes_when_its_recording_is_a_day_old_however_recently_watched(tmp_path):
    expired = tmp_path / recording_svc._cache_name("cam1", NOW - timedelta(days=1, minutes=5), 60)
    expired.write_bytes(b"video")  # just written, i.e. watched now
    recent = tmp_path / recording_svc._cache_name("cam1", NOW - timedelta(hours=23), 60)
    recent.write_bytes(b"video")
    unwatched_since = time.time() - 2 * 24 * 3600
    os.utime(recent, (unwatched_since, unwatched_since))  # not watched for 2 days

    recording_svc._prune_cache(tmp_path)

    assert not expired.exists()
    assert recent.exists()  # its recording still exists, so the copy stays


def test_the_sync_loop_cleans_the_cache_once_per_interval(monkeypatch):
    cleaned = []
    monkeypatch.setattr(settings, "camera_sync_interval_s", 0.01)
    monkeypatch.setattr(camera_sync, "_sync_once", lambda: None)
    monkeypatch.setattr(recording_svc, "clean_cache", lambda: cleaned.append(1))

    async def run_for(seconds):
        try:
            await asyncio.wait_for(camera_sync.run_forever(), seconds)
        except TimeoutError:
            pass

    monkeypatch.setattr(recording_svc, "CACHE_CLEAN_INTERVAL_S", 600)
    # A machine booted 5 s ago, as a fresh CI runner or range PC: the clock
    # reads less than the interval, and the first round must still clean
    monkeypatch.setattr(camera_sync, "_clock", lambda: 5.0)
    asyncio.run(run_for(0.2))  # about 20 rounds
    assert len(cleaned) == 1   # on the first round only

    cleaned.clear()
    monkeypatch.setattr(recording_svc, "CACHE_CLEAN_INTERVAL_S", 0)
    asyncio.run(run_for(0.2))
    assert len(cleaned) > 1    # every round once the interval has passed


# --- review: real YAML, a file's real end, the served part kept ---

@pytest.mark.parametrize("text, names", [
    ("paths:\n  loopdemo:\n    source: publisher\n", {"loopdemo"}),
    ("paths:\n    loopdemo:\n        source: publisher\n", {"loopdemo"}),        # four spaces
    ('paths:\n  "quoted":\n    source: publisher\n', {"quoted"}),               # quoted key
    ("paths: {inline: {source: publisher}, other: {}}\n", {"inline", "other"}),  # inline mapping
    ("logLevel: info\n", set()),                                                 # no paths
    ("paths: [\n", None),                                                        # not valid YAML: unknown
])
def test_mediamtx_yml_path_names_are_read_as_yaml(monkeypatch, tmp_path, text, names):
    config = tmp_path / "mediamtx.yml"
    config.write_text(text)
    monkeypatch.setattr(settings, "mediamtx_config", str(config))

    paths = read_config_paths()
    assert (None if paths is None else paths.names) == names


def _config_paths(monkeypatch, tmp_path, text):
    config = tmp_path / "mediamtx.yml"
    config.write_text(text)
    monkeypatch.setattr(settings, "mediamtx_config", str(config))
    return read_config_paths()


def test_a_regexp_path_in_mediamtx_yml_defines_every_name_it_matches(monkeypatch, tmp_path):
    paths = _config_paths(monkeypatch, tmp_path, 'paths:\n  "~^external[0-9]+$":\n    source: publisher\n  all_others:\n')

    assert paths.defines("external1") and paths.defines("external42")
    assert not paths.defines("cam1") and not paths.defines("external")
    assert paths.catch_all and not paths.defines("anything")   # the catch-all leaves names to cameras


@pytest.mark.parametrize("pattern", [
    "(?P<x",                 # not even valid
    "^external[[:digit:]]+$",  # Go's POSIX class; Python reads a different set
    "(?i)^external1$",       # flags
    "\\bexternal",            # word boundary: Unicode in Python, ASCII in Go
    "^external\\pN$",         # Unicode classes
    "^external1\\z",          # \z: Go only
    "(?P<n>external)1",      # named groups
])
def test_a_regexp_python_may_read_differently_leaves_mediamtx_yml_unknown(monkeypatch, tmp_path, pattern):
    text = "paths:\n  " + json.dumps("~" + pattern) + ":\n"
    assert _config_paths(monkeypatch, tmp_path, text) is None


@pytest.mark.parametrize("pattern, matching, other", [
    ("^external[0-9]+$", "external1", "external"),
    ("^cam\\d{2}$", "cam12", "cam\u0661\u0662"),   # \d is ASCII digits, as in Go
    ("^(?:door|gate)_[a-z]+$", "gate_east", "gate_East"),
    ("ext[^0-9]", "my-extA", "ext1"),          # unanchored, as Go's MatchString
])
def test_a_regexp_with_the_same_meaning_in_go_is_matched(monkeypatch, tmp_path, pattern, matching, other):
    paths = _config_paths(monkeypatch, tmp_path, "paths:\n  " + json.dumps("~" + pattern) + ":\n")

    assert paths.defines(matching) and not paths.defines(other)


def test_regexp_and_all_others_definitions_are_never_deleted_by_the_sync(monkeypatch, tmp_path, db_state):
    # MediaMTX lists each definition under its key; these look like camera paths
    _config_paths(monkeypatch, tmp_path, 'paths:\n  "~^external[0-9]+$":\n  all_others:\n')
    monkeypatch.setattr(mediamtx, "config_paths", read_config_paths)
    mtx = FakeMediaMTX(monkeypatch, {
        "~^external[0-9]+$": camera_sync.path_config(make_camera("external"), record=False),
        "all_others": camera_sync.playback_only_config(),
    })

    camera_sync.sync(None)

    assert mtx.calls == []


def test_a_camera_named_like_a_regexp_path_is_refused_and_never_applied(monkeypatch, db_state):
    monkeypatch.setattr(camera_sync, "_conflicts", set())
    regexp = mediamtx.ConfigPaths(patterns=(re.compile("^external[0-9]+$"),))
    monkeypatch.setattr(mediamtx, "config_paths", lambda: regexp)
    mtx = FakeMediaMTX(monkeypatch, {})

    assert camera_sync.taken_by_config("external1")
    assert not camera_sync.taken_by_config("cam1")
    db_state.cameras = [make_camera("external1")]   # created while MediaMTX was down
    camera_sync.sync(None)
    assert mtx.calls == []                          # not added over the regexp's path


def test_folders_a_regexp_path_records_into_are_never_deleted(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path / "recordings"))
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path / "cache"))
    regexp = mediamtx.ConfigPaths(patterns=(re.compile("^external[0-9]+$"),))
    monkeypatch.setattr(mediamtx, "config_paths", lambda: regexp)
    start = NOW - timedelta(days=2)
    external = _recording(tmp_path / "recordings" / "external1", start + timedelta(minutes=5))
    camera = _recording(tmp_path / "recordings" / "cam1", start + timedelta(minutes=5))

    recording_svc.remove_unused_recordings([])                          # no camera has either name
    recording_svc.delete_session_video([(start, start + timedelta(minutes=20))], [])

    assert external.exists() and not camera.exists()


def test_with_all_others_in_mediamtx_yml_no_recording_folder_is_touched(monkeypatch, tmp_path):
    # Its paths may record under any name, so no folder is known to be a camera's
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path / "recordings"))
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(mediamtx, "config_paths", lambda: mediamtx.ConfigPaths(catch_all=True))
    start = NOW - timedelta(days=2)
    published = _recording(tmp_path / "recordings" / "someone", start + timedelta(minutes=5))

    recording_svc.remove_unused_recordings([])
    recording_svc.delete_session_video([(start, start + timedelta(minutes=20))], [])

    assert published.exists()


def test_a_recording_stopped_early_ends_at_its_last_write(monkeypatch, tmp_path):
    # A stopped at +5 (its file last written then); B started at +7, before
    # MediaMTX's next file at +8: A's file is A's alone
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path / "recordings"))
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path / "cache"))
    start = NOW - timedelta(hours=1)
    a_file = _recording(tmp_path / "recordings" / "cam1", start)
    written = (start + timedelta(minutes=5)).timestamp()
    os.utime(a_file, (written, written))
    b_file = _recording(tmp_path / "recordings" / "cam1", start + timedelta(minutes=8))
    a = (start, start + timedelta(minutes=5))
    b = (start + timedelta(minutes=7), start + timedelta(minutes=20))

    assert recording_svc.delete_session_video([a], [b]) == 1
    assert not a_file.exists() and b_file.exists()


def test_a_part_larger_than_the_cache_limit_is_still_served(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "replay_cache_max_gb", 1 / 1024**3)  # 1 byte
    older = tmp_path / recording_svc._cache_name("cam1", NOW - timedelta(minutes=30), 60)
    older.write_bytes(b"older video")
    monkeypatch.setattr(mediamtx, "open_recording", lambda alias, start, duration_s: FakeVideo())

    path = recording_svc.replay_file("cam1", NOW - timedelta(minutes=5), 60, still_allowed=lambda: True)

    assert path.exists() and path.read_bytes() == b"mp4 bytes"   # kept, though over the limit
    assert not older.exists()                                     # the rest goes


def test_parts_played_at_once_all_stay_whatever_the_cache_limit(monkeypatch, tmp_path):
    # Three players, each on its own part; together they are over the limit,
    # and none of their parts is removed under them
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "replay_cache_max_gb", 1 / 1024**3)  # 1 byte
    monkeypatch.setattr(mediamtx, "open_recording", lambda alias, start, duration_s: FakeVideo())
    unplayed = tmp_path / recording_svc._cache_name("cam1", NOW - timedelta(minutes=50), 60)
    unplayed.write_bytes(b"older video")

    parts = [
        recording_svc.replay_file("cam1", NOW - timedelta(minutes=m), 60, still_allowed=lambda: True)
        for m in (30, 20, 10)
    ]
    recording_svc.clean_cache()

    assert all(p.read_bytes() == b"mp4 bytes" for p in parts)
    assert not unplayed.exists()


def test_a_part_no_longer_played_goes_with_the_cache_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "replay_cache_max_gb", 1 / 1024**3)  # 1 byte
    monkeypatch.setattr(mediamtx, "open_recording", lambda alias, start, duration_s: FakeVideo())
    path = recording_svc.replay_file("cam1", NOW - timedelta(minutes=5), 60, still_allowed=lambda: True)

    # Its player stopped asking for it longer than IN_USE_S ago
    recording_svc._in_use[path] = time.monotonic() - 1
    recording_svc.clean_cache()

    assert not path.exists() and recording_svc._in_use == {}


def test_a_part_played_while_the_cache_is_pruned_stays(monkeypatch, tmp_path):
    # A request marks the part in use after pruning started scanning the folder
    # but before it reached the limit: the part is not removed under it
    monkeypatch.setattr(settings, "replay_cache_max_gb", 1 / 1024**3)  # 1 byte
    part = tmp_path / recording_svc._cache_name("cam1", NOW - timedelta(minutes=5), 60)
    part.write_bytes(b"mp4 bytes")
    read_name = recording_svc._read_cache_name

    def scanned(file):
        recording_svc._mark_in_use(file)  # the request arrives mid-scan
        return read_name(file)

    monkeypatch.setattr(recording_svc, "_read_cache_name", scanned)
    recording_svc._prune_cache(tmp_path)

    assert part.exists()


def test_a_part_being_played_stays_past_the_day_until_it_is_no_longer_played(tmp_path):
    part = tmp_path / recording_svc._cache_name("cam1", NOW - timedelta(days=1, minutes=5), 60)
    part.write_bytes(b"mp4 bytes")
    recording_svc._mark_in_use(part)  # just returned to a player

    recording_svc._prune_cache(tmp_path)
    assert part.exists()

    recording_svc._in_use[part] = time.monotonic() - 1  # its player stopped
    recording_svc._prune_cache(tmp_path)
    assert not part.exists()


def test_deleting_a_session_waits_for_a_replay_download_in_progress(monkeypatch, tmp_path):
    # The part is still downloading when its session is deleted: the delete
    # waits for it, and the finished copy goes too
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path / "recordings"))
    started, release = threading.Event(), threading.Event()

    class SlowVideo:
        def iter_bytes(self):
            yield b"first half "
            started.set()
            release.wait(5)
            yield b"second half"

        def close(self):
            pass

    monkeypatch.setattr(mediamtx, "open_recording", lambda alias, start, duration_s: SlowVideo())
    part_start = NOW - timedelta(minutes=5)
    download = threading.Thread(target=lambda: recording_svc.replay_file("cam1", part_start, 60, still_allowed=lambda: True))
    download.start()
    started.wait(5)
    deleting = threading.Thread(target=lambda: recording_svc.delete_session_video([(part_start, NOW)], []))
    deleting.start()
    deleting.join(0.2)
    assert deleting.is_alive()          # waiting for the download, not overtaking it

    release.set()
    download.join(5)
    deleting.join(5)
    assert list(tmp_path.glob("*.mp4")) == [] and list(tmp_path.glob("*.part")) == []


def test_a_replay_that_starts_after_its_session_was_deleted_fetches_nothing(monkeypatch, tmp_path):
    # Authorised before the delete committed, but reaching the part only after
    # the delete had looked at the downloads in progress: the session is gone
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path))
    fetched = []
    monkeypatch.setattr(mediamtx, "open_recording", lambda *a: fetched.append(a) or FakeVideo())

    with pytest.raises(recording_svc.PartWithdrawn):
        recording_svc.replay_file("cam1", NOW, 60, still_allowed=lambda: False)

    assert fetched == [] and list(tmp_path.iterdir()) == []


def test_part_locks_are_released_once_nobody_uses_them(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "replay_cache_dir", str(tmp_path))
    monkeypatch.setattr(mediamtx, "open_recording", lambda alias, start, duration_s: FakeVideo())

    for minutes in range(5):  # five different parts, each played twice
        for _ in range(2):
            recording_svc.replay_file("cam1", NOW - timedelta(minutes=minutes), 60, still_allowed=lambda: True)
    recording_svc.delete_session_video([(NOW - timedelta(hours=1), NOW)], [])

    assert recording_svc._locks == {}
