"""The Detection Service's supervisor (`python -m detection.supervisor`).

It starts the Detection Service as a child process, and starts it again
whenever it is gone or stuck. It is the one thing outside the service, so it
still works when the service itself is frozen (a native GPU or stream call that
never returns holds every thread of a process, the service's own stall check
included).

It restarts the service when:
  - the service exits, however it did;
  - it never answers `/status` within STARTUP_GRACE_S of starting (the model
    loads first), or stops answering for API_DEAD_AFTER_S;

It does not judge the Runs: a Run with no video to look at (its camera is off)
is not a fault, and restarting the service for it would stop every other camera.
The service's own stall check, which can tell the two apart, ends a stuck Run (or,
in thread mode, exits for this to start it again). This only catches what that
check cannot, a service frozen as a whole.

A service that keeps dying at once is restarted after a longer wait each time
(up to BACKOFF_MAX_S), so a broken install does not spin.

`--run-mode thread|process` is the service's own. In thread mode the service is
started with `--exit-on-stall`, since a stuck thread cannot be killed: the
service exits, and this starts it again. Everything else after the supervisor's
own options is passed to the service as it is.
"""
import argparse
import ctypes
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

from detection import logs

log = logging.getLogger("detection.supervisor")

STARTUP_GRACE_S = 120   # PROVISIONAL: a cold start loads the model before the API binds
POLL_EVERY_S = 2
API_DEAD_AFTER_S = 15   # PROVISIONAL
STALL_AFTER_S = 10      # the service's own default (service.STALL_AFTER_S), repeated: importing it loads cv2
BACKOFF_MIN_S = 1
BACKOFF_MAX_S = 30
HEALTHY_AFTER_S = 60    # a service that ran this long was fine: its next restart starts from BACKOFF_MIN_S
DEFAULT_PORT = 8010


class _Child:
    """The service's process, as the supervisor needs it: is it gone, and kill
    it with everything it started (its Runs' processes, in process mode)."""
    def __init__(self, process):
        self._process = process

    def poll(self):
        return self._process.poll()

    def kill_tree(self):
        if self._process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(self._process.pid), "/T", "/F"],
                               capture_output=True, check=False)
            else:
                self._process.kill()
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            log.error("The Detection Service (pid %d) did not die when killed", self._process.pid)


CREATE_SUSPENDED = 0x00000004
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_job = None   # held for the supervisor's life: when it ends, however it does, Windows closes it


def _kill_when_the_supervisor_ends():
    """A Windows job that kills every process in it when its last handle closes,
    which is when the supervisor ends, however: a stop, a crash, a kill from the
    Task Manager. Without it the service it started would live on, holding its
    port and the GPU, and the next supervisor's service could not start."""
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _Basic), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
    info = _Extended()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                            ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
    return job


def die_with_me(process):
    """Puts a just-started, still suspended `process` in the job that dies with
    the supervisor, so does everything it starts after (the service's Run
    processes). Answers whether it did; a failure is logged, not raised: the
    service runs either way, only unguarded against the supervisor's death."""
    global _job
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    from ctypes import wintypes
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    try:
        if _job is None:
            _job = _kill_when_the_supervisor_ends()
        if not kernel32.AssignProcessToJobObject(_job, int(process._handle)):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        return True
    except OSError as e:
        log.warning("The Detection Service will keep running if the supervisor is killed (Windows refused "
                    "the guard: %s)", e)
        return False


def _resume(process):
    """A process started with CREATE_SUSPENDED, let go."""
    ctypes.WinDLL("ntdll").NtResumeProcess(ctypes.c_void_p(int(process._handle)))


def _spawn(command):
    if os.name != "nt":
        return _Child(subprocess.Popen(command))
    # Suspended until it is in the job: Windows' python.exe starts the real
    # interpreter as its own child at once, which is only in the job if the job
    # was there first
    process = subprocess.Popen(command, creationflags=CREATE_SUSPENDED)
    try:
        die_with_me(process)
    finally:
        _resume(process)
    return _Child(process)


def _fetch_status(host, port, timeout=5):
    """The Runs `/status` lists, or None when it does not answer."""
    try:
        with urlopen(f"http://{host}:{port}/status", timeout=timeout) as response:
            return json.loads(response.read())["runs"]
    except Exception:
        return None


class Supervisor:
    """`spawn()` starts the service and answers its `_Child`; `fetch()` answers
    `/status`'s Runs, or None; `clock` is monotonic seconds. All three are the
    tests' to replace."""
    def __init__(self, spawn, fetch, poll_every_s=POLL_EVERY_S, clock=time.monotonic):
        self._spawn, self._fetch, self._clock = spawn, fetch, clock
        self._poll_every_s = poll_every_s
        self.restarts, self.child = 0, None

    def run(self, stop):
        """Keep the service running until `stop` is set."""
        delay = BACKOFF_MIN_S
        while not stop.is_set():
            started = self._clock()
            child = self.child = self._spawn()
            log.info("The Detection Service started")
            reason = self._watch(child, stop, started)
            child.kill_tree()
            if stop.is_set():
                return
            self.restarts += 1
            lived = self._clock() - started
            # Waits `delay`, the first time BACKOFF_MIN_S, then twice as long each time it dies
            # again at once; a service that had run well starts again from BACKOFF_MIN_S
            wait = BACKOFF_MIN_S if lived >= HEALTHY_AFTER_S else delay
            delay = min(wait * 2, BACKOFF_MAX_S)
            log.error("The Detection Service stopped (%s) after running %.0f s: starting it again in %g s "
                      "(restart %d); every camera's Run restarts with it",
                      reason, lived, wait, self.restarts,
                      extra={"reason": reason, "lived_s": round(lived), "wait_s": wait, "restarts": self.restarts})
            if stop.wait(wait):
                return

    def _watch(self, child, stop, started):
        """Why the service has to be started again, once it does."""
        answered = None
        while not stop.wait(self._poll_every_s):
            code = child.poll()
            if code is not None:
                return f"it exited with code {code}"
            now = self._clock()
            if self._fetch() is None:
                if answered is None and now - started >= STARTUP_GRACE_S:
                    return f"it did not answer within {STARTUP_GRACE_S} s of starting"
                if answered is not None and now - answered >= API_DEAD_AFTER_S:
                    return f"it stopped answering for {API_DEAD_AFTER_S} s"
                continue
            answered = now
        return "stopped"


def _stop_on_signals(stop):
    """A stop from the service manager or the app (SIGTERM, Windows' SIGBREAK) or
    Ctrl+C ends the loop, so `main` stops the service as well, not leaves it."""
    def handler(signum, frame):
        log.info("The supervisor was asked to stop (signal %s)", signal.Signals(signum).name)
        stop.set()
    for name in ("SIGTERM", "SIGBREAK", "SIGINT"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), handler)


def main(argv=None):
    p = argparse.ArgumentParser("The Detection Service's supervisor: starts it, and starts it "
                                "again when it exits or is stuck. Other options go to the service.")
    p.add_argument("--run-mode", choices=("thread", "process"), default="thread")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--stall-after", type=float, default=STALL_AFTER_S)
    p.add_argument("--log-dir", type=Path, default=None)
    a, rest = p.parse_known_args(argv)
    log_file = logs.configure(a.log_dir)
    command = [sys.executable, "-m", "detection.service", "--run-mode", a.run_mode,
               "--host", a.host, "--port", str(a.port), "--stall-after", str(a.stall_after)]
    if a.log_dir:
        command += ["--log-dir", str(a.log_dir)]
    if a.run_mode == "thread":
        command.append("--exit-on-stall")   # a stuck thread cannot be killed: the service exits, this restarts it
    command += rest
    log.info("Supervising the Detection Service (%s mode): %s", a.run_mode, " ".join(command),
             extra={"log_file": str(log_file)})
    supervisor = Supervisor(lambda: _spawn(command), lambda: _fetch_status(a.host, a.port))
    stop = threading.Event()
    _stop_on_signals(stop)
    try:
        supervisor.run(stop)
    except KeyboardInterrupt:
        stop.set()
    finally:
        log.info("The supervisor is stopping: the Detection Service is stopped with it")
        if supervisor.child is not None:
            supervisor.child.kill_tree()   # never leave the service running with no one watching it


if __name__ == "__main__":
    main()
