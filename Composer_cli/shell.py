from __future__ import annotations

from os import PathLike
from typing import Optional, Sequence, Tuple, Union
import subprocess
from pathlib import Path
from typing import Sequence, Optional, Tuple
import shlex
import sys
import shutil

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
        command = self._format_shell_command(cmd, cwd)

        if sys.platform == "darwin":
            if title and close_existing:
                self.close_terminal_windows(title)

            escaped = command.replace('"', '\\"')
            script_lines = [
                'tell application "Terminal"',
                "activate",
                f'do script "{escaped}"',
            ]
            if title:
                script_lines.append(f'set custom title of front window to "{title}"')
            script_lines.append("end tell")
            subprocess.run(["osascript", "-e", "\n".join(script_lines)], check=False)
            return

        if sys.platform.startswith("linux"):
            if self._open_new_terminal_linux(command, title):
                return

        subprocess.Popen(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

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

    def _format_shell_command(self, cmd: Sequence[str], cwd: Optional[Path]) -> str:
        command = " ".join(shlex.quote(part) for part in cmd)
        if cwd:
            command = f"cd {shlex.quote(str(cwd))} && {command}"
        return command

    def _open_new_terminal_linux(self, command: str, title: Optional[str]) -> bool:
        shell_command = ["bash", "-lc", command]

        candidates: list[list[str]] = []

        if shutil.which("gnome-terminal"):
            args = ["gnome-terminal"]
            if title:
                args += ["--title", title]
            candidates.append(args + ["--"] + shell_command)

        if shutil.which("tilix"):
            args = ["tilix"]
            if title:
                args += ["-t", title]
            candidates.append(args + ["-e"] + shell_command)

        if shutil.which("konsole"):
            args = ["konsole"]
            if title:
                args += ["--title", title]
            candidates.append(args + ["-e"] + shell_command)

        if shutil.which("xfce4-terminal"):
            args = ["xfce4-terminal"]
            if title:
                args += ["--title", title]
            candidates.append(args + ["-e"] + shell_command)

        if shutil.which("alacritty"):
            args = ["alacritty"]
            if title:
                args += ["-t", title]
            candidates.append(args + ["-e"] + shell_command)

        if shutil.which("kitty"):
            args = ["kitty"]
            if title:
                args += ["--title", title]
            candidates.append(args + shell_command)

        if shutil.which("xterm"):
            args = ["xterm"]
            if title:
                args += ["-T", title]
            candidates.append(args + ["-e"] + shell_command)

        if shutil.which("lxterminal"):
            args = ["lxterminal"]
            if title:
                args += ["-t", title]
            candidates.append(args + ["-e"] + shell_command)

        for candidate in candidates:
            try:
                subprocess.Popen(candidate)
                return True
            except Exception:
                continue

        return False