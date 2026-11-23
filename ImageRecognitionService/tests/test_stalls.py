"""Checks for the Detection Service's stall check (detection/stalls.py): a Run that
looks at nothing is ended, a thread Run that cannot be stopped exits the service,
and what is not a stall (a camera that is down, a Run draining its posts) is left
alone. Driven in-process on `service.DetectionService`, with its fixtures."""
import threading
import time

from test_service import CAMERA, CLOCK, SESSION, _watching_process_run, api  # noqa: F401 (api is a fixture)

from detection import service, stalls, webapp


def _stall_a_run(api):
    """A Run watching `CAMERA`, then stuck inside its registration: alive, and
    looking at nothing. Returns the Event that frees it."""
    assert api.start()[0] == 200
    freed, real = threading.Event(), api.registration.register

    def stuck(frame, index):
        freed.wait(10)
        return real(frame, index)

    api.registration.register = stuck
    time.sleep(0.3)   # a Look in hand finishes, then the next one sticks
    return freed


def test_a_run_that_keeps_looking_is_never_ended_as_stalled(api):
    assert api.start()[0] == 200
    now = CLOCK
    api.service.check_stalls(now)
    time.sleep(0.3)
    api.service.check_stalls(now + 1000)   # a long time on, but it looked on meanwhile
    assert [r["state"] for r in api.service.status()] == ["watching"]


def test_a_watching_run_that_looks_at_no_frame_for_the_stall_time_is_ended(api):
    freed = _stall_a_run(api)
    try:
        now = CLOCK
        api.service.check_stalls(now)
        api.service.check_stalls(now + stalls.STALL_AFTER_S - 1)
        assert len(api.service.status()) == 1   # not yet
        api.service.check_stalls(now + stalls.STALL_AFTER_S)
        assert api.service.status() == []   # ended, so the backend's reconcile starts it again
        freed.set()
        assert api.start()[0] == 200        # and the Session is free to
    finally:
        freed.set()


def test_a_stalled_runs_late_bullet_holes_are_not_posted(api):
    freed = _stall_a_run(api)
    try:
        run = next(iter(api.service._runs.values()))
        now = CLOCK
        api.service.check_stalls(now)
        api.service.check_stalls(now + stalls.STALL_AFTER_S)
        assert run.dropping and run.error.startswith("stalled")
    finally:
        freed.set()


def test_a_process_run_whose_looked_at_stands_still_is_killed(api):
    run = _watching_process_run(api.service, "2026-10-22T10:15:02.120Z")
    now = CLOCK
    api.service.check_stalls(now)
    run.remote.watched = {"registered": None, "looked_at": "2026-10-22T10:15:02.193Z"}   # it moved
    api.service.check_stalls(now + stalls.STALL_AFTER_S)
    assert not run.process.killed
    api.service.check_stalls(now + 2 * stalls.STALL_AFTER_S)
    assert run.process.killed and run.error.startswith("stalled")
    api.service._runs.clear()


def test_a_process_run_that_never_reports_a_look_is_killed_too(api):
    run = _watching_process_run(api.service, None)
    now = CLOCK
    api.service.check_stalls(now)
    api.service.check_stalls(now + stalls.STALL_AFTER_S)
    assert run.process.killed
    api.service._runs.clear()


def test_a_run_still_starting_is_not_judged_by_the_stall_check(api):
    run = _watching_process_run(api.service)
    run.enter("starting")
    now = CLOCK
    api.service.check_stalls(now)
    api.service.check_stalls(now + 10 * stalls.STALL_AFTER_S)
    assert not run.process.killed
    api.service._runs.clear()


def test_a_stalled_thread_run_exits_the_service_when_asked_to(monkeypatch, api):
    api.service._exit_on_stall = True
    exits = []
    monkeypatch.setattr(stalls.os, "_exit", exits.append)
    freed = _stall_a_run(api)
    try:
        now = CLOCK
        api.service.check_stalls(now)
        api.service.check_stalls(now + stalls.STALL_AFTER_S)
        assert exits == [3]
    finally:
        freed.set()


# --- a camera that is down is not a Run that is stuck ---

def test_a_process_run_whose_camera_is_down_is_waited_for_then_ended_alone(api):
    run = _watching_process_run(api.service, "2026-10-22T10:15:02.120Z")
    run.remote.down = True
    now = CLOCK
    api.service.check_stalls(now)
    api.service.check_stalls(min(now + stalls.STALL_AFTER_S + 1, now + stalls.CAMERA_DOWN_AFTER_S - 1))
    api.service.check_stalls(now + stalls.CAMERA_DOWN_AFTER_S - 1)
    assert not run.process.killed          # the stream is reopening itself: waited for
    api.service.check_stalls(now + stalls.CAMERA_DOWN_AFTER_S)
    assert run.process.killed              # down for good: this Run is ended
    api.service._runs.clear()


def test_a_process_run_whose_camera_comes_back_is_not_ended(api):
    run = _watching_process_run(api.service, "t0")
    run.remote.down = True
    now = CLOCK
    api.service.check_stalls(now)
    run.remote.down = False
    run.remote.watched = {"registered": None, "looked_at": "t1"}   # it looks again
    api.service.check_stalls(now + stalls.STALL_AFTER_S + 5)
    run.remote.watched = {"registered": None, "looked_at": "t2"}   # and keeps looking
    api.service.check_stalls(now + stalls.CAMERA_DOWN_AFTER_S + 5)
    assert not run.process.killed
    api.service._runs.clear()


class _DownStream:
    down = True


class _LoopOnADownStream:
    looked, source = 7, _DownStream()

    def stop(self):
        pass


def test_a_thread_run_whose_camera_is_down_never_exits_the_service(monkeypatch, api):
    """One dead camera must not stop the other cameras' Runs."""
    api.service._exit_on_stall = True
    exits = []
    monkeypatch.setattr(stalls.os, "_exit", exits.append)
    run = service._Run(SESSION, CAMERA)
    run.loop, run.baseline_view = _LoopOnADownStream(), {}
    run.enter("watching")
    api.service._runs[(SESSION, CAMERA)] = run
    now = CLOCK
    api.service.check_stalls(now)
    api.service.check_stalls(now + stalls.CAMERA_DOWN_AFTER_S + 1)
    assert exits == []                       # the service lives on
    assert api.service.status() == []        # only this Run is ended
    assert run.error.startswith("stalled")


# --- a stall is dealt with once, and the exit saves the other cameras first ---

def test_a_killed_process_run_is_not_judged_again_while_it_is_retired(api, caplog):
    """Its process takes a moment to be seen gone: the checks in between must not
    kill it and log the same error again."""
    run = _watching_process_run(api.service, "t0")
    kills = []
    run.process.kill = lambda: kills.append(1)
    now = CLOCK
    api.service.check_stalls(now)
    for second in range(stalls.STALL_AFTER_S, stalls.STALL_AFTER_S + 5):
        api.service.check_stalls(now + second)
    assert kills == [1]
    errors = [r for r in caplog.records if r.levelname == "ERROR" and "looked at no frame" in r.getMessage()]
    assert len(errors) == 1
    assert errors[0].camera == CAMERA and errors[0].session_id == SESSION and errors[0].run_mode == "process"
    api.service._runs.clear()


def test_a_run_is_retired_once(api, caplog):
    """A stalled thread Run is retired by the stall check, and again if its own
    thread ever wakes: one 'ended' line, not two."""
    caplog.set_level("INFO")
    run = service._Run(SESSION, CAMERA)
    api.service._runs[(SESSION, CAMERA)] = run
    api.service._retire(run)
    api.service._retire(run)
    assert [r.getMessage() for r in caplog.records].count(f"Run on camera {CAMERA} ended") == 1


class _SavingLoop:
    """A healthy Run's loop: finishing it ends the Run, as a drained one does."""
    def __init__(self, run, saves=True):
        self.run, self.saves, self.finished, self._looks = run, saves, False, 0

    @property
    def looked(self):   # a healthy Run looks on: every read is further than the last
        self._looks += 1
        return self._looks

    def finish(self):
        self.finished = True
        if self.saves:
            self.run.ended.set()

    def stop(self):
        if self.saves:
            self.run.ended.set()


def _healthy_thread_run(svc, camera, saves=True):
    run = service._Run(SESSION, camera)
    run.loop, run.baseline_view = _SavingLoop(run, saves), {}
    run.enter("watching")
    svc._runs[(SESSION, camera)] = run
    return run


def test_the_service_saves_the_other_cameras_before_it_exits_for_a_stuck_thread(monkeypatch, api, caplog):
    monkeypatch.setattr(service, "ENDING_TIMEOUT_S", 0.1)
    monkeypatch.setattr(stalls, "EXIT_DRAIN_S", 1)
    api.service._exit_on_stall = True
    exits = []
    monkeypatch.setattr(stalls.os, "_exit", exits.append)
    stuck = _healthy_thread_run(api.service, "stuck")
    stuck.loop = _LoopOnADownStream()      # no `finish`: it never answers
    stuck.loop.source = type("S", (), {"down": False})()   # its video arrives
    good = _healthy_thread_run(api.service, "good")
    slow = _healthy_thread_run(api.service, "slow", saves=False)   # cannot finish in time
    try:
        now = CLOCK
        api.service.check_stalls(now)
        api.service.check_stalls(now + stalls.STALL_AFTER_S)
        assert exits == [3]
        assert good.loop.finished and good.ended.is_set()
        messages = [r.getMessage() for r in caplog.records if r.levelname == "CRITICAL"]
        assert any("exiting to be restarted" in m and "stuck" in m for m in messages)
        assert any("were saved" in m and "good" in m and "slow" in m for m in messages)
        final = [r for r in caplog.records if "were saved" in r.getMessage()][0]
        assert final.saved == ["good"] and final.not_saved == ["slow"]
    finally:
        api.service._runs.clear()
        slow.ended.set()


def test_a_process_run_that_is_draining_its_posts_is_not_judged_stalled_until_the_drain_limit(api):
    run = _watching_process_run(api.service, "t0")
    run.draining = CLOCK   # it finished looking, and posts what it confirmed
    api.service.check_stalls(CLOCK)
    api.service.check_stalls(CLOCK + webapp.DRAIN_TIMEOUT_S + service.KILL_AFTER_S - 1)
    assert not run.process.killed   # no look, but within the drain limit: not a stall now
    api.service.check_stalls(CLOCK + webapp.DRAIN_TIMEOUT_S + service.KILL_AFTER_S + 1)
    api.service.check_stalls(CLOCK + webapp.DRAIN_TIMEOUT_S + service.KILL_AFTER_S + 1 + stalls.STALL_AFTER_S)
    assert run.process.killed   # a drain that never ends is still bounded
    api.service._runs.clear()


def test_a_run_whose_camera_comes_back_after_a_long_outage_gets_a_fresh_stall_time(api):
    """Back means video again, not yet a Look: the outage is not counted as the Run being stuck."""
    run = _watching_process_run(api.service, "t0")
    api.service.check_stalls(CLOCK)
    run.remote.down = True
    api.service.check_stalls(CLOCK + 1)
    api.service.check_stalls(CLOCK + 50)               # down 50 s: waited for
    run.remote.down = False                              # video again, no Look yet
    api.service.check_stalls(CLOCK + 51)
    api.service.check_stalls(CLOCK + 51 + stalls.STALL_AFTER_S - 1)
    assert not run.process.killed
    api.service.check_stalls(CLOCK + 51 + stalls.STALL_AFTER_S + 1)
    assert run.process.killed                            # video flows and it still looks at nothing: stuck
    api.service._runs.clear()


def test_a_stall_logs_in_one_line_where_the_run_is_stuck(api, caplog):
    freed = _stall_a_run(api)
    try:
        now = CLOCK
        api.service.check_stalls(now)
        with caplog.at_level("ERROR", logger="detection.stalls"):
            api.service.check_stalls(now + stalls.STALL_AFTER_S)
        record = next(r for r in caplog.records if "is stuck for" in r.getMessage())
        message = record.getMessage()
        assert f"Camera {CAMERA}" in message and "\n" not in message   # one readable line
        assert "threading.py" in message and "in wait" in message   # the file, line and function it is in
        assert any(line.endswith("in stuck") for line in record.run_stack)   # the whole stack is a field
        assert record.other_threads
        assert record.model_lock_held in (True, False)
    finally:
        freed.set()
