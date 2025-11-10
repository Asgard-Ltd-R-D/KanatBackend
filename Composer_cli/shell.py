from __future__ import annotations

from os import PathLike
from typing import Optional, Sequence, Tuple, Union
import subprocess
from pathlib import Path
from typing import Sequence, Optional, Tuple
import shlex
import sys

StrOrBytesPath = Union[str, bytes, PathLike[str], PathLike[bytes]]


class SubprocessShell:
    def run(self, cmd: Sequence[str], cwd: Optional[Path] = None, check: bool = True) -> int:
        res = subprocess.run(list(cmd), cwd=str(cwd) if cwd else None)
        if check and res.returncode != 0:
            raise subprocess.CalledProcessError(res.returncode, cmd)
        return res.returncode

    def run_capture(self, cmd: Sequence[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        p = subprocess.run(list(cmd), cwd=str(cwd) if cwd else None, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def popen_stream(self, cmd: Sequence[str], cwd: Optional[Path] = None) -> int:
        proc = subprocess.Popen(list(cmd), cwd=str(cwd) if cwd else None)
        return proc.wait()

    def open_new_terminal(
        self,
        cmd: Sequence[str],
        cwd: Optional[Path] = None,
        title: Optional[str] = None,
        close_existing: bool = False,
    ) -> None:
        if sys.platform != "darwin":
            subprocess.Popen(list(cmd), cwd=str(cwd) if cwd else None)
            return

        if title and close_existing:
            self.close_terminal_windows(title)

        cmd_parts = list(cmd)
        command = " ".join(shlex.quote(part) for part in cmd_parts)
        if cwd:
            command = f"cd {shlex.quote(str(cwd))} && {command}"
        escaped = command.replace('"', '\\"')
        title_line = f'set custom title of front window to "{title}"' if title else ""
        script_lines = [
            'tell application "Terminal"',
            "activate",
            f'do script "{escaped}"',
        ]
        if title_line:
            script_lines.append(title_line)
        script_lines.append("end tell")
        subprocess.run(["osascript", "-e", "\n".join(script_lines)], check=False)

    def close_terminal_windows(self, title: str) -> None:
        if sys.platform != "darwin":
            return
        script = f'''
tell application "Terminal"
    repeat with w in windows
        if custom title of w is "{title}" then
            close w
        end if
    end repeat
end tell
'''
        subprocess.run(["osascript", "-e", script], check=False)