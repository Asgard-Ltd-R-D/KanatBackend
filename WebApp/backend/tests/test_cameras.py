import pytest
from pydantic import ValidationError

from app.schemas.camera import CameraInput
from app.services import camera_sync, mediamtx
from app.services import cameras as camera_svc
from tests.fakes import FakeMediaMTX, make_camera


# --- the path each camera gets ---

def test_a_camera_path_runs_run_record_as_kanatfrontend_built_it():
    config = camera_sync.path_config(make_camera(iface="eth1"), record=False)

    assert config["runOnInit"] == (
        "bash -lc '\n"
        'exec ./run_record.sh --mcast-ip "226.226.226.112" --mcast-port "112"'
        ' --rtsp-url "rtsp://127.0.0.1:${RTSP_PORT}/cam1" --iface "eth1"\n'
        "'"
    )
    assert config["runOnInitRestart"] is True
    assert config["record"] is False
    assert config["recordDeleteAfter"] == "1d"


def test_no_iface_leaves_the_flag_out():
    assert "--iface" not in camera_sync.path_config(make_camera(), record=False)["runOnInit"]


# --- syncing MediaMTX to the database ---

def test_a_new_camera_is_added(monkeypatch, db_state):
    mtx = FakeMediaMTX(monkeypatch)
    db_state.cameras = [make_camera()]

    camera_sync.sync(None)

    assert mtx.calls == [("add", "cam1")]


def test_an_unchanged_camera_is_left_alone(monkeypatch, db_state):
    db_state.cameras = [make_camera()]
    mtx = FakeMediaMTX(monkeypatch, {"cam1": camera_sync.path_config(make_camera(), record=False)})

    camera_sync.sync(None)

    assert mtx.calls == []


def test_a_removed_camera_is_deleted_but_paths_from_mediamtx_yml_are_kept(monkeypatch, db_state):
    mtx = FakeMediaMTX(monkeypatch, {
        "old": camera_sync.path_config(make_camera("old"), record=False),
        "loopdemo": {"runOnDemand": "./run_loopdemo.sh", "runOnInit": ""},
    })

    camera_sync.sync(None)

    assert mtx.calls == [("delete", "old")]
    assert "loopdemo" in mtx.paths


def test_a_camera_named_like_a_mediamtx_yml_path_leaves_that_path_alone(monkeypatch, db_state):
    # e.g. created while MediaMTX was down, so the API could not refuse the name
    monkeypatch.setattr(camera_sync, "_conflicts", set())
    monkeypatch.setattr(mediamtx, "config_paths", lambda: mediamtx.ConfigPaths(frozenset({"loopdemo"})))
    static = {"runOnDemand": "./run_loopdemo.sh", "runOnInit": ""}
    db_state.cameras = [make_camera("loopdemo")]
    mtx = FakeMediaMTX(monkeypatch, {"loopdemo": dict(static)})

    camera_sync.sync(None)
    assert mtx.calls == []                 # not patched into a camera
    db_state.cameras = []
    camera_sync.sync(None)
    assert mtx.calls == []                 # and not deleted with it
    assert mtx.paths["loopdemo"] == static


def test_a_failed_sync_does_not_fail_the_request(monkeypatch, db_state):
    def unreachable():
        raise mediamtx.MediaMTXUnreachable("down")

    monkeypatch.setattr(mediamtx, "list_path_configs", unreachable)

    camera_sync.sync_soon(None)  # no exception: the loop retries


# --- what the operator may enter ---

@pytest.mark.parametrize("field, value", [
    ("alias", "cam;rm -rf ~"),
    ("alias", "cam 1"),
    ("alias", "-cam"),
    ("mcast_ip", "226.226.226"),
    ("mcast_ip", "192.168.1.10"),        # unicast: not a group a camera multicasts to
    ("mcast_ip", "226.226.226.1\" --x"),
    ("mcast_port", 0),
    ("mcast_port", 70000),
    ("iface", "eth0\"; reboot"),
    ("iface", "eth 0"),
])
def test_values_that_could_break_the_command_are_refused(field, value):
    body = {"alias": "cam1", "mcast_ip": "226.226.226.112", "mcast_port": 112, field: value}
    with pytest.raises(ValidationError):
        CameraInput(**body)


def test_a_blank_iface_means_none():
    assert CameraInput(alias="cam1", mcast_ip="226.226.226.112", mcast_port=112, iface="  ").iface is None


def test_a_name_from_mediamtx_yml_cannot_be_a_camera(monkeypatch):
    monkeypatch.setattr(mediamtx, "list_path_configs", lambda: {
        "loopdemo": {"runOnDemand": "./run_loopdemo.sh", "runOnInit": ""},
        "cam1": camera_sync.path_config(make_camera(), record=False),
    })

    assert camera_sync.taken_by_config("loopdemo") is True
    assert camera_sync.taken_by_config("cam1") is False   # a camera's own path
    assert camera_sync.taken_by_config("new") is False


# --- the status shown in Settings ---

def test_each_camera_shows_whether_video_is_arriving(monkeypatch):
    # "quiet" stays ready in MediaMTX, but its bytes stopped growing
    counters = {"live1": 100, "quiet": 500}
    monkeypatch.setattr(mediamtx, "path_states", lambda: {
        name: {"ready": True, "inboundBytes": n} for name, n in counters.items()
    })
    cameras = [make_camera("live1"), make_camera("quiet"), make_camera("off", enabled=False)]
    camera_svc.watch_traffic()

    counters["live1"] += 1000
    assert [c.status for c in camera_svc.with_status(cameras)] == ["live", "no_signal", "disabled"]


def test_a_camera_that_stops_sending_turns_to_no_signal(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(camera_svc.time, "monotonic", lambda: clock[0])
    counter = {"n": 100}
    monkeypatch.setattr(mediamtx, "path_states", lambda: {"cam1": {"ready": True, "inboundBytes": counter["n"]}})
    camera_svc.watch_traffic()
    counter["n"] = 200
    camera_svc.watch_traffic()

    clock[0] = camera_svc.STALE_S - 1
    assert camera_svc.with_status([make_camera()])[0].status == "live"
    clock[0] = camera_svc.STALE_S + 1
    assert camera_svc.with_status([make_camera()])[0].status == "no_signal"


def test_without_mediamtx_the_state_is_unreachable(monkeypatch):
    def unreachable():
        raise mediamtx.MediaMTXUnreachable("down")

    monkeypatch.setattr(mediamtx, "path_states", unreachable)

    assert camera_svc.with_status([make_camera()])[0].status == "unreachable"



def test_a_cameras_name_cannot_be_changed(monkeypatch):
    # It names the camera's stream, which the detection model reads, and its recordings
    from fastapi import HTTPException

    monkeypatch.setattr(camera_svc, "get_camera_or_404", lambda camera_id, db: make_camera("lane1"))
    body = CameraInput(alias="north", mcast_ip="226.226.226.112", mcast_port=112)

    with pytest.raises(HTTPException) as refused:
        camera_svc.update_camera(None, body, None)
    assert refused.value.status_code == 409
