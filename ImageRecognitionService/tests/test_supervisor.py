"""Checks for the Detection Service's supervisor: a fake service process, a fake
`/status` and a clock the fake `/status` moves, so nothing waits in real time."""
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from detection import supervisor
from detection.supervisor import Supervisor


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class _Child:
    """A service process: gone once `code` is set; `killed` if the supervisor killed it."""
    def __init__(self):
        self.code, self.killed = None, False

    def poll(self):
        return self.code

    def kill_tree(self):
        self.killed = True


class _World:
    """Starts `children` services one after another and ends the test after
    `spawns` of them; each `/status` poll moves the clock 2 s and answers what
    `answer(child, spawn_number, now)` says: a list of Runs, or None."""
    def __init__(self, answer, spawns=2):
        self.clock, self.children, self.stop, self.answer, self.limit = _Clock(), [], threading.Event(), answer, spawns
        self.supervisor = Supervisor(self.spawn, self.fetch, poll_every_s=0, clock=self.clock)
        self.supervisor.run  # noqa: B018 (the real loop is run by `go`)

    def spawn(self):
        if len(self.children) == self.limit:
            self.stop.set()
        child = _Child()
        self.children.append(child)
        return child

    def fetch(self):
        self.clock.now += 2
        return self.answer(self.children[-1], len(self.children), self.clock.now)

    def go(self):
        # A restart's wait is real time on `stop.wait`: make it instant
        real_wait, self.stop.wait = self.stop.wait, lambda timeout=None: real_wait(0)
        self.supervisor.run(self.stop)
        return self


def _run(camera="cam-a", state="watching", looked_at="t0"):
    return {"session_id": "s", "camera": camera, "state": state, "looked_at": looked_at}


def test_a_healthy_service_is_left_alone():
    ticks = []

    def answer(child, n, now):
        ticks.append(now)
        if len(ticks) > 200:
            child.code = 1   # end the test: it has run 400 s without a restart
        return [_run(looked_at=f"t{now}")]
    world = _World(answer, spawns=1).go()
    assert world.supervisor.restarts == 1   # only the end of the test
    assert len(ticks) >= 200


def test_a_service_that_exits_is_started_again():
    world = _World(lambda child, n, now: setattr(child, "code", 3) or [], spawns=3).go()
    assert len(world.children) >= 3
    assert all(c.killed for c in world.children)   # whatever was left of each is cleaned up


def test_a_service_that_never_answers_is_restarted_after_the_startup_grace():
    world = _World(lambda child, n, now: None, spawns=2).go()
    first_restart_at = supervisor.STARTUP_GRACE_S
    assert world.children[0].killed
    assert world.clock.now >= first_restart_at


def test_a_service_that_stops_answering_is_restarted():
    def answer(child, n, now):
        return [] if now < 20 else None
    world = _World(answer, spawns=2).go()
    assert world.children[0].killed
    assert 20 + supervisor.API_DEAD_AFTER_S <= world.clock.now < supervisor.STARTUP_GRACE_S + 20 + 40


def test_runs_with_no_progress_are_not_the_supervisors_to_judge():
    """A camera that is off leaves its Run looking at nothing: the service's own
    check tells that from a stuck Run, so the supervisor must not restart for it."""
    def answer(child, n, now):
        if now > 600:
            child.code = 1   # end the test: 10 minutes with nothing moving, no restart
        return [_run(looked_at="same"), _run("cam-b", looked_at="same")]
    world = _World(answer, spawns=1).go()
    assert world.supervisor.restarts == 1   # the end of the test only


def test_a_service_that_keeps_dying_is_restarted_after_a_longer_wait_each_time():
    waits = []
    world = _World(lambda child, n, now: setattr(child, "code", 1) or [], spawns=8)
    real_wait = world.stop.wait
    world.stop.wait = lambda timeout=None: (waits.append(timeout), real_wait(0))[1]
    world.supervisor.run(world.stop)
    delays = [w for w in waits if w]   # the poll's waits are 0
    assert delays[:7] == [1, 2, 4, 8, 16, 30, 30]   # the first wait is the shortest; doubling, then capped


def test_a_restart_is_logged_for_the_logs_tab_with_why_and_when(caplog):
    world = _World(lambda child, n, now: setattr(child, "code", 3) or [], spawns=1)
    world.go()
    line = next(r for r in caplog.records if "stopped" in r.getMessage())
    assert line.levelname == "ERROR"
    assert "it exited with code 3" in line.getMessage() and "every camera's Run restarts" in line.getMessage()
    assert (line.reason, line.restarts, line.wait_s) == ("it exited with code 3", 1, supervisor.BACKOFF_MIN_S)


def test_a_stop_signal_stops_the_supervisor_so_it_stops_the_service():
    stop = threading.Event()
    before = {n: signal.getsignal(getattr(signal, n)) for n in ("SIGTERM", "SIGINT")}
    try:
        supervisor._stop_on_signals(stop)
        signal.raise_signal(signal.SIGTERM)
        assert stop.is_set()
    finally:
        for name, handler in before.items():
            signal.signal(getattr(signal, name), handler)


@pytest.mark.skipif(os.name != "nt", reason="Windows jobs")
def test_the_service_dies_with_a_supervisor_that_is_killed():
    """The supervisor is killed hard (no signal, no cleanup): the service it
    started, and what that started, must go with it."""
    psutil = pytest.importorskip("psutil")
    root = Path(__file__).resolve().parents[1]
    code = os.linesep.join([
        "import sys, time",
        "from detection import supervisor",
        "c = supervisor._spawn([sys.executable, '-c', 'import time; time.sleep(120)'])",
        "print(c._process.pid, flush=True)",
        "time.sleep(120)"])
    boss = subprocess.Popen([sys.executable, "-c", code], cwd=root, stdout=subprocess.PIPE, text=True)
    try:
        child = int(boss.stdout.readline())
        family = [child] + [c.pid for c in psutil.Process(child).children(recursive=True)]
        assert all(psutil.pid_exists(pid) for pid in family)
        boss.kill()   # TerminateProcess: nothing in it runs
        boss.wait(10)
        deadline = time.time() + 10
        while time.time() < deadline and any(psutil.pid_exists(pid) for pid in family):
            time.sleep(0.2)
        assert not any(psutil.pid_exists(pid) for pid in family)
    finally:
        boss.kill()


class _Process:
    pid, code = 4242, 0

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        return self.code


def test_on_posix_the_service_leads_a_process_group_of_its_own(monkeypatch):
    started = {}
    monkeypatch.setattr(supervisor, "_IS_WINDOWS", False)
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda command, **kw: started.update(kw) or _Process())
    supervisor._spawn(["service"])
    assert started == {"start_new_session": True}   # so its Runs' processes can be killed with it


def test_on_posix_the_whole_group_is_killed_even_when_the_service_is_already_gone(monkeypatch):
    """A Run in a native call that never returns never sees its Pipe close: it is
    only reached by killing its group, which the service's exit leaves alive."""
    killed = []
    monkeypatch.setattr(supervisor, "_IS_WINDOWS", False)
    monkeypatch.setattr(supervisor.os, "killpg", lambda pgid, sig: killed.append((pgid, sig)), raising=False)
    monkeypatch.setattr(supervisor.signal, "SIGKILL", 9, raising=False)
    supervisor._Child(_Process()).kill_tree()   # poll() answers 0: the service itself has exited
    assert killed == [(4242, 9)]


def test_a_stop_ends_the_runs_before_the_service_is_killed():
    """An ordinary stop is not a freeze: each Run is asked to end (judge, post) first."""
    order, stop = [], threading.Event()

    class _Service(_Child):
        def kill_tree(self):
            order.append("killed")

    def end_run(session_id, camera):
        order.append(f"end {camera}")

    def spawn():
        stop.set()   # the stop arrives while the service runs
        return _Service()

    supervisor_ = Supervisor(spawn, lambda: [_run("cam-a"), _run("cam b")], poll_every_s=0, end_run=end_run)
    supervisor_.run(stop)
    assert sorted(order[:-1]) == ["end cam b", "end cam-a"] and order[-1] == "killed"


def test_a_freeze_kills_the_service_without_asking_it_to_end_its_runs():
    asked = []
    world = _World(lambda child, n, now: None, spawns=1)   # never answers: frozen
    world.supervisor._end_run = lambda *a: asked.append(a)
    world.go()
    assert world.children[0].killed and asked == []


@pytest.mark.skipif(os.name != "nt", reason="Windows jobs")
def test_what_a_service_that_is_already_gone_left_behind_is_killed_with_its_job(tmp_path):
    """A Run stuck in a native call outlives a service that crashes: its job kills it."""
    psutil = pytest.importorskip("psutil")
    pidfile = tmp_path / "run.pid"
    code = os.linesep.join([
        "import os, subprocess, sys",
        "run = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])",
        f"open({str(pidfile)!r}, 'w').write(str(run.pid))",
        "os._exit(3)"])   # the service crashes, its Run is left running
    child = supervisor._spawn([sys.executable, "-c", code])
    try:
        deadline = time.time() + 20
        while time.time() < deadline and (child.poll() is None or not pidfile.exists()):
            time.sleep(0.1)
        left = int(pidfile.read_text())
        assert child.poll() is not None and psutil.pid_exists(left)
        child.kill_tree()
        deadline = time.time() + 10
        while time.time() < deadline and psutil.pid_exists(left):
            time.sleep(0.1)
        assert not psutil.pid_exists(left)
    finally:
        child.kill_tree()
