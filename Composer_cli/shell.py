from __future__ import annotations

from os import PathLike
from typing import Optional, Sequence, Tuple, Union
import subprocess
from pathlib import Path
from typing import Sequence, Optional, Tuple

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

    def open_new_terminal(self, cmd: Sequence[str], cwd: Optional[Path] = None) -> None:
        script = (
            "tell application \"Terminal\" to do script \""
            + (f"cd {cwd} && " if cwd else "")
            + " ".join(cmd)
            + "\""
        )
        subprocess.run(["osascript", "-e", script])