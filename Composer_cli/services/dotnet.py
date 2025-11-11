from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from ..abstractions import DotnetService, BuildResult
from ..shell import SubprocessShell
from ..utils.messages import info, error, warn


class DefaultDotnetService(DotnetService):
    def __init__(self, project_dir: Path, shell: SubprocessShell | None = None) -> None:
        self.project_dir = project_dir
        self.sh = shell or SubprocessShell()

    def is_available(self) -> bool:
        code, out, _ = self.sh.run_capture(["dotnet", "--version"])
        return code == 0 and bool(out.strip())

    def publish(self, rid: str | None, output: Path) -> BuildResult:
        cmd = ["dotnet", "publish", "-c", "Release", "-o", str(output)]
        if rid:
            cmd += ["-r", rid, "--self-contained", "false"]
        rc = self.sh.run(cmd, cwd=self.project_dir, check=False)
        return BuildResult(ok=(rc == 0), message=f"dotnet publish rc={rc}")

    def build_environment(self, env: str, release_dir: Path) -> bool:
        """Publish PacketProcessingService for an environment and mirror assets into the release directory."""
        release_dir.mkdir(parents=True, exist_ok=True)
        res = self.publish(self._infer_rid(), release_dir)
        if not res.ok:
            error(f"Build {env} failed: {res.message}")
            return False
        self.sync_runtime_assets(env, release_dir)
        return True

    def sync_runtime_assets(self, env: str, release_dir: Path) -> None:
        """Copy appsettings.* and wwwroot contents into the release directory."""
        dotnet_env = "Development" if env == "dev" else "Production"
        for name in ("appsettings.json", f"appsettings.{dotnet_env}.json"):
            src = self.project_dir / name
            if src.exists():
                shutil.copy2(src, release_dir / name)

        www_src = self.project_dir / "wwwroot"
        if www_src.exists():
            www_dest = release_dir / "wwwroot"
            if www_dest.exists():
                shutil.rmtree(www_dest)
            shutil.copytree(www_src, www_dest)

    def run_packetprocessing(self, dll_path: Path, environment: str, detach: bool = False) -> int:
        """Launch PacketProcessingService.dll via sudo and stream its output until completion."""
        if not dll_path.exists():
            error(f"PacketProcessingService.dll not found at {dll_path}")
            return 1
        if detach:
            self.terminate_packetprocessing(dll_path, environment)
        dotnet_env = "Development" if environment == "dev" else "Production"
        info(f"Starting PacketProcessingService ({dotnet_env})...")
        cmd = ["dotnet", str(dll_path), "--environment", dotnet_env]
        if detach:
            self.sh.open_new_terminal(
                cmd,
                cwd=dll_path.parent,
                title=self._terminal_title(environment),
                close_existing=True,
            )
            pid_file = dll_path.parent / "PacketProcessingService.pid"
            pid_file.write_text("detached\n")
            return 0
        rc = self.sh.popen_stream(cmd, cwd=dll_path.parent)
        if rc != 0:
            error(f"PacketProcessingService exited with code {rc}")
        return rc

    def terminate_packetprocessing(self, dll_path: Path, environment: str) -> None:
        """Stop PacketProcessingService by terminating the process and closing its terminal window."""
        # Attempt to kill the running process
        if dll_path.exists():
            if os.name == "nt":
                self._terminate_packetprocessing_windows(dll_path)
            else:
                try:
                    self.sh.run(["pkill", "-f", str(dll_path)], check=False)
                except FileNotFoundError:
                    pass

        # Remove PID markers if present
        pid_file = dll_path.parent / "PacketProcessingService.pid"
        if pid_file.exists():
            try:
                pid_file.unlink()
            except OSError:
                pass

        # Close any terminal windows associated with this environment
        self.sh.close_terminal_windows(self._terminal_title(environment))

    def project_exists(self) -> bool:
        return self.project_dir.exists()

    def is_process_running(self, dll_path: Path) -> tuple[bool, str, str]:
        if os.name == "nt":
            return self._is_process_running_windows(dll_path)
        try:
            cmd = ["pgrep", "-f", str(dll_path)]
            rc, _, _ = self.sh.run_capture(cmd)
        except FileNotFoundError:
            return False, "", ""
        if rc != 0:
            return False, "", ""
        env = "Development" if "dev" in dll_path.parts else "Production"
        port = "10901" if env == "Development" else "10900"
        return True, env, port

    def _infer_rid(self) -> str | None:
        """Infer a runtime identifier that matches the current host OS and architecture."""
        rid_override = os.getenv("KANAT_TARGET_RID")
        if rid_override:
            return rid_override
        os_name = platform.system()
        arch = platform.machine()
        if os_name == "Linux":
            return "linux-x64"
        if os_name == "Darwin":
            return "osx-arm64" if arch == "arm64" else "osx-x64"
        if os_name == "Windows":
            return "win-x64"
        return None

    @staticmethod
    def _terminal_title(environment: str) -> str:
        env_name = "DEV" if environment == "dev" else "PROD"
        return f"PacketProcessingService {env_name}"

    def _terminate_packetprocessing_windows(self, dll_path: Path) -> None:
        ps = self._powershell_command()
        if not ps:
            warn("PowerShell not found; unable to terminate PacketProcessingService on Windows automatically.")
            return
        pattern = dll_path.name.replace("'", "''")
        script = (
            "Get-CimInstance Win32_Process | "
            f"Where-Object {{ $_.CommandLine -like '*{pattern}*' }} | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )
        try:
            self.sh.run(ps + ["-NoProfile", "-Command", script], check=False)
        except FileNotFoundError:
            pass

    def _is_process_running_windows(self, dll_path: Path) -> tuple[bool, str, str]:
        ps = self._powershell_command()
        if not ps:
            return False, "", ""
        pattern = dll_path.name.replace("'", "''")
        script = (
            "$p = Get-CimInstance Win32_Process | "
            f"Where-Object {{ $_.CommandLine -like '*{pattern}*' }} | "
            "Select-Object -First 1;"
            "if ($p) { $p.ProcessId }"
        )
        try:
            rc, out, _ = self.sh.run_capture(ps + ["-NoProfile", "-Command", script])
        except FileNotFoundError:
            return False, "", ""
        if rc != 0 or not out.strip():
            return False, "", ""
        env = "Development" if "dev" in dll_path.parts else "Production"
        port = "10901" if env == "Development" else "10900"
        return True, env, port

    def _powershell_command(self) -> list[str] | None:
        if os.name != "nt":
            return None
        for name in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
            resolved = shutil.which(name)
            if resolved:
                return [resolved]
        return None