from __future__ import annotations

import json
import os
import signal
import time
from contextlib import suppress
from pathlib import Path
from urllib.request import urlopen

from ..shell import SubprocessShell
from ..utils.messages import info, warn, error, print_started, print_stopped

# detection.service's DEFAULT_PORT, which the WebApp backend calls too.
PORT = 8010
# How long `up` waits for the control API to answer: the imports and the
# detector's weights, ~1 s warm on the development Mac, far longer cold.
START_TIMEOUT_S = 60
# How long `stop` waits after SIGTERM, which ends any Run and drains its posts,
# before it kills the process.
STOP_TIMEOUT_S = 10
TITLE = "Detection Service"
# Its command line as `pgrep -f` sees it. On macOS the .venv's python shows as
# the framework's Python, so only the module names it.
PATTERN = r"-m detection\.service"
# Its Python processes on Windows, killed at once: Windows has no SIGTERM, and
# a console of its own cannot be sent a Ctrl-C from here. The .venv's
# python.exe is a launcher with a python.exe child, so both match.
_WINDOWS_KILL = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
                 "$_.CommandLine -like '*-m detection.service*' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
# The interpreter's version, then which of its heaviest requirements it lacks.
_PROBE = ("import importlib.util, sys; print('%d.%d' % sys.version_info[:2], "
          "*[m for m in ('cv2', 'ultralytics') if not importlib.util.find_spec(m)])")


class DefaultDetectionService:
    """The Detection Service (ADR-0008): `python -m detection.service`, run from
    ImageRecognitionService/ on its own .venv, at the Python version its
    .python-version declares (#222). Nothing supervises or restarts it."""

    def __init__(self, service_dir: Path, shell: SubprocessShell | None = None) -> None:
        self.service_dir = service_dir
        self.sh = shell or SubprocessShell()
        self.python = service_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def problem(self) -> str | None:
        """Why it cannot run here, or None."""
        if not self.python.exists():
            return (f"no Python at {self.python}: build its .venv as "
                    "ImageRecognitionService/HANDOVER.md's \"Running it\" says")
        try:
            rc, out, err = self.sh.run_capture([str(self.python), "-c", _PROBE])
        except OSError as e:
            rc, err = 1, str(e)
        if rc != 0:
            return f"{self.python} does not run: {err.strip()}"
        version, *missing = out.split()
        declared = (self.service_dir / ".python-version").read_text().strip()
        if version != declared:
            return f"{self.python} is Python {version}, but .python-version declares {declared}: rebuild the .venv"
        if missing:
            return (f"its .venv lacks {', '.join(missing)}: "
                    f"{self.python.relative_to(self.service_dir)} -m pip install -r requirements.txt")
        return None

    def is_running(self) -> bool:
        """Whether its control API answers /status."""
        try:
            with urlopen(f"http://127.0.0.1:{PORT}/status", timeout=1) as response:
                json.load(response)
            return True
        except (OSError, ValueError):
            return False

    def run_detection(self) -> int:
        """Start it in a window of its own, and wait until it answers."""
        if self.is_running():
            info(f"{TITLE} already running on 127.0.0.1:{PORT}")
            return 0
        problem = self.problem()
        if problem:
            error(f"{TITLE} not started: {problem}")
            return 1
        self.sh.open_new_terminal(
            [str(self.python), "-m", "detection.service"],
            cwd=self.service_dir,
            title=TITLE,
            close_existing=True,
        )
        deadline = time.monotonic() + START_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.is_running():
                print_started(f"{TITLE} (127.0.0.1:{PORT})")
                return 0
            time.sleep(0.5)
        error(f"{TITLE} not answering on 127.0.0.1:{PORT} after {START_TIMEOUT_S} s: see the window it runs in")
        return 1

    def stop_detection(self) -> None:
        """SIGTERM, which ends any Run and drains its posts, then SIGKILL past
        STOP_TIMEOUT_S. On Windows, killed at once."""
        if os.name == "nt":
            # ponytail: no drain on Windows; a shutdown call on the control API would give it one
            self.sh.run(["powershell", "-NoProfile", "-Command", _WINDOWS_KILL], check=False)
        else:
            self._signal(signal.SIGTERM)
            deadline = time.monotonic() + STOP_TIMEOUT_S
            while self._pids() and time.monotonic() < deadline:
                time.sleep(0.2)
            if self._pids():
                warn(f"{TITLE} still running {STOP_TIMEOUT_S} s after SIGTERM; killing it, "
                     "and any Bullet Hole it has not posted yet is lost")
                self._signal(signal.SIGKILL)
        self.sh.close_terminal_windows(TITLE)
        print_stopped(TITLE)

    def _signal(self, sig: int) -> None:
        for pid in self._pids():
            with suppress(ProcessLookupError):
                os.kill(pid, sig)

    def _pids(self) -> list[int]:
        """Its Python processes. A shell or terminal whose command line carries
        the module (Linux's `bash -lc`, `xterm -e`) is left alone: its exit would
        SIGHUP the service before the drain."""
        _, out, _ = self.sh.run_capture(["pgrep", "-f", "--", PATTERN])
        pids = []
        for pid in out.split():
            _, comm, _ = self.sh.run_capture(["ps", "-o", "comm=", "-p", pid])
            if Path(comm.strip()).name.lower().startswith("python"):
                pids.append(int(pid))
        return pids
