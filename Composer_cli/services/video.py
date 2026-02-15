from __future__ import annotations

import os
import shutil
import platform
import time
from pathlib import Path

from ..shell import SubprocessShell
from ..utils.messages import info, error, warn, success, print_started, print_stopped


class DefaultVideoService:
    def __init__(self, video_service_dir: Path, shell: SubprocessShell | None = None) -> None:
        self.service_dir = video_service_dir
        self.sh = shell or SubprocessShell()
        self.binary_name = "mediamtx.exe" if os.name == "nt" else "mediamtx"

    def is_available(self) -> bool:
        """Check if mediamtx binary exists in the service directory."""
        return (self.service_dir / self.binary_name).exists()

    def run_mediamtx(self, detach: bool = False) -> int:
        """Launch mediamtx."""
        binary_path = self.service_dir / self.binary_name
        config_path = self.service_dir / "mediamtx.yml"
        
        if not binary_path.exists():
            error(f"mediamtx binary not found at {binary_path}")
            return 1

        if not config_path.exists():
             error(f"mediamtx.yml config not found at {config_path}")
             return 1

        print_started("mediamtx")
        # mediamtx expects config file as argument or looks in current dir. 
        # We'll set CWD to service_dir.
        cmd = [str(binary_path)]
        
        if detach:
            self.sh.open_new_terminal(
                cmd,
                cwd=self.service_dir,
                title="MediaMtx Service",
                close_existing=True,
            )
            # Write a pid marker or similar if needed, but for now we rely on process name match
            return 0
        
        # In attached mode (unlikely for "up", but good for debugging)
        rc = self.sh.popen_stream(cmd, cwd=self.service_dir)
        if rc != 0:
            error(f"mediamtx exited with code {rc}")
        return rc

    def stop_mediamtx(self) -> None:
        """Stop mediamtx process."""
        if os.name == "nt":
            self._stop_windows()
        else:
            try:
                # pkill -f matches against the full command line
                self.sh.run(["pkill", "-x", self.binary_name], check=False)
            except FileNotFoundError:
                pass
        
        # Close terminal window if any
        self.sh.close_terminal_windows("MediaMtx Service")
        print_stopped("mediamtx")

    def is_running(self) -> bool:
        """Check if mediamtx is currently running."""
        try:
            if os.name == "nt":
                return self._is_running_windows()
            
            # recursive grep against process list
            cmd = ["pgrep", "-x", self.binary_name]
            rc, _, _ = self.sh.run_capture(cmd)
            return rc == 0
        except FileNotFoundError:
            return False

    def _stop_windows(self) -> None:
        self.sh.run(["taskkill", "/F", "/IM", self.binary_name], check=False)

    def _is_running_windows(self) -> bool:
        rc, out, _ = self.sh.run_capture(["tasklist", "/FI", f"IMAGENAME eq {self.binary_name}"])
        return self.binary_name in out
