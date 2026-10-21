import asyncio
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.config.settings import settings
from app.services import camera_sync, mediamtx
from app.services import recordings as recording_svc
from tests.fakes import NOW, FakeMediaMTX, make_camera


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
    monkeypatch.setattr(mediamtx, "config_path_names", lambda: {"static"})
    mtx = FakeMediaMTX(monkeypatch, {"static": camera_sync.playback_only_config()})

    camera_sync.sync(None)                      # no camera: not deleted
    db_state.cameras = [make_camera("static")]
    camera_sync.sync(None)                      # a camera of that name: not patched
    assert mtx.calls == []


def test_without_mediamtx_yml_only_paths_running_run_record_count_as_cameras(monkeypatch, db_state):
    monkeypatch.setattr(mediamtx, "config_path_names", lambda: None)  # file unreadable
    mtx = FakeMediaMTX(monkeypatch, {
        "running": camera_sync.path_config(make_camera("running"), record=False),
        "unsure": camera_sync.playback_only_config(),
    })

    camera_sync.sync(None)

    assert mtx.calls == [("delete", "running")]  # "unsure" is left alone


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
        threading.Thread(target=lambda: paths.append(recording_svc.replay_file("cam1", NOW, 12.5)))
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
        recording_svc.replay_file("cam1", NOW, 10.0)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("offset_s, duration_s", [
    (0, recording_svc.MAX_PART_S + 1),   # longer than any part offered
    (550, 100),                          # runs past the session's end
    (-5, 10),                            # starts before the session
])
def test_a_replay_part_must_lie_within_the_session(monkeypatch, offset_s, duration_s):
    from fastapi.testclient import TestClient
    from app.core.deps import get_db
    from app.main import app
    from app.services import sessions as session_svc

    start = NOW - timedelta(minutes=10)
    recorded = SimpleNamespace(recording_intervals=[SimpleNamespace(started_at=start, ended_at=NOW)])
    monkeypatch.setattr(session_svc, "get_session_or_404", lambda sid, db: recorded)
    app.dependency_overrides[get_db] = lambda: None
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/sessions/{uuid.uuid4()}/recordings/cam1/video",
                params={"start": (start + timedelta(seconds=offset_s)).isoformat(), "duration_s": duration_s},
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 422


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
    monkeypatch.setattr(mediamtx, "config_path_names", lambda: {"loopdemo"})
    start = NOW - timedelta(hours=1)
    window = (start, start + timedelta(minutes=20))

    inside = _recording(tmp_path / "recordings" / "cam1", start + timedelta(minutes=5))
    other_camera = _recording(tmp_path / "recordings" / "cam2", start + timedelta(minutes=6))
    # A camera renamed or deleted since: its folder no camera row names any more
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
