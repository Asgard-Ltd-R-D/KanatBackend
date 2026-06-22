from __future__ import annotations

from pathlib import Path

import shutil
import time

from .abstractions import ComposerUseCases, ComposeContext
from .paths import Paths
from .progress import Progress
from .shell import SubprocessShell
from .services.compose import DefaultComposeService
from .services.docker import DefaultDockerService
from .services.dotnet import DefaultDotnetService
from .services.video import DefaultVideoService
from .services.environment import EnvironmentManager
from .services.envmanage import DefaultEnvManager
from .services.packaging import DefaultPackagingService
from .utils.parse_compose import required_images_from_compose
from .utils.messages import info, warn, error, success

class ComposerApp(ComposerUseCases):
    """Orchestrates build, compose, and runtime operations for PacketProcessingService."""

    def __init__(self, command_registry, paths: Paths | None = None) -> None:
        """Wire default service implementations; callers may inject alternatives (e.g. tests)."""
        self.paths = paths or Paths()
        self.shell = SubprocessShell()
        self.progress = Progress()

        docker_service = DefaultDockerService(self.shell)
        dotnet_service = DefaultDotnetService(self.paths.packet_processing_dir, self.shell)

        self.docker = docker_service
        self.dotnet = dotnet_service
        self.video = DefaultVideoService(self.paths.video_service_dir, self.shell)
        self.compose = DefaultComposeService(self.shell)
        self.env = DefaultEnvManager(self.shell)
        self.packager = DefaultPackagingService(self.shell, self.progress, self.paths, docker_service)
        self.environments = EnvironmentManager(self.paths, docker_service, dotnet_service)

        self.registry = command_registry

    def run(self, args) -> int:
        """Dispatch the parsed CLI args to their registered command handler."""
        cmd = getattr(args, "command", None)
        handler = self.registry.get(cmd) if cmd else None
        if not handler:
            error("Unknown command")
            return 1
        return handler.run(self, args)

    def _compose_ctx(self, env: str) -> ComposeContext:
        """Build a compose context describing files and project naming for the environment."""
        compose_file = self._resolve_compose_file(env)
        work_dir = compose_file.parent
        project_name = f"kanatbackend-{env}"
        return ComposeContext(environment=env, compose_file=compose_file, work_dir=work_dir, project_name=project_name)

    def up(self, environment: str, detached: bool, args: any = None) -> int:
        """Ensure prerequisites exist, start Docker services, and optionally launch PacketProcessingService."""
        if not self.docker.is_available():
            error("Docker is not available")
            return 1
        if not self.dotnet.is_available():
            error(".NET SDK is not available")
            return 1

        # Ensure other env is not running
        other = "dev" if environment == "prod" else "prod"
        other_ctx = self._compose_ctx(other)
        if self.env.is_running(other_ctx):
            warn(f"{other.upper()} is running; stopping it first...")
            self.env.stop_env(other_ctx)

        if not self.environments.ensure_releases_present(self._required_images_for_env):
            return 1

        if not self.environments.ensure_environment_ready(environment, self._required_images_for_env(environment)):
            return 1

        ctx = self._compose_ctx(environment)

        # Bring up (always detached so we can launch PacketProcessingService below)
        ok = self.compose.up(ctx, detached=True, build_if_missing=True)
        if not ok:
            error("docker compose up failed")
            return 1
        success("Environment started")

        dll_path = self.paths.release_dir / environment / "PacketProcessingService.dll"
        
        # Start MediaMtx if requested
        if getattr(args, "mediamtx", False):
            if self.video.is_available():
                self.video.run_mediamtx(detach=True)
            else:
                warn("MediaMtx requested but not available (binary/config missing in VideoService)")

        if detached:
            info("Launching PacketProcessingService in a new terminal window (detached mode)")
            time.sleep(8) # Await for docker containers to run
            self.dotnet.run_packetprocessing(dll_path, environment, detach=True)
            return 0

        time.sleep(8) # Await for docker containers to run
        return self.dotnet.run_packetprocessing(dll_path, environment)

    def stop(self, environment: str) -> int:
        """Issue docker compose stop for the selected environment."""
        dll_path = self.paths.release_dir / environment / "PacketProcessingService.dll"
        self.dotnet.terminate_packetprocessing(dll_path, environment)
        self.video.stop_mediamtx()
        ctx = self._compose_ctx(environment)
        self.compose.stop(ctx)
        success(f"{environment.upper()} stopped")
        return 0

    def kill(self, environment: str) -> int:
        """Stop services, remove containers, and delete release artifacts for the environment."""
        dll_path = self.paths.release_dir / environment / "PacketProcessingService.dll"
        self.dotnet.terminate_packetprocessing(dll_path, environment)
        self.video.stop_mediamtx()
        ctx = self._compose_ctx(environment)
        self.env.kill_env(ctx)
        dll_dir = self.paths.release_dir / environment
        if dll_dir.exists():
            shutil.rmtree(dll_dir)
        success(f"{environment.upper()} killed")
        return 0

    def status(self) -> int:
        """Print docker compose status along with release presence indicators."""
        print("System Status\n---------------")
        print("Docker Containers:")
        print(self.docker.ps_table() or "  <none>")
        # Quick DLL presence
        for env in ("dev", "prod"):
            dll = self.paths.release_dir / env / "PacketProcessingService.dll"
            built = dll.exists()
            running, platform, port = self.dotnet.is_process_running(dll)
            status = "[OK] Built" if built else "[MISSING] PacketProcessingService.dll"
            runtime = f", Running ({platform}) on port {port}" if running else ", Not Running"
            print(f"{env}: {status}{runtime}")
        
        # MediaMtx Status
        mtx_avail = self.video.is_available()
        mtx_running = self.video.is_running()
        mtx_status = "[OK] Available" if mtx_avail else "[MISSING] Binary/Config"
        mtx_runtime = ", Running" if mtx_running else ", Not Running"
        print(f"MediaMtx: {mtx_status}{mtx_runtime}")

        return 0

    def build_all(self) -> int:
        """Publish PacketProcessingService and ensure required Docker images exist for dev and prod."""
        if not self.dotnet.is_available():
            error(".NET SDK is not available")
            return 1
        if not self.docker.is_available():
            error("Docker is not available")
            return 1

        return 0 if self.environments.build_all(self._required_images_for_env) else 1

    def release(self, platform: str) -> int:
        """Run a full build (if needed) and invoke the packaging service for the specified platform."""
        if not self.environments.ensure_releases_present(self._required_images_for_env):
            return 1
        ok = self.packager.create_release(platform)
        return 0 if ok else 1

    # ------------- internals -------------
    def _resolve_compose_file(self, env: str) -> Path:
        """Return a packaged compose override when available, otherwise the workspace default."""
        compose_override = self._latest_package_compose(env)
        if compose_override:
            return compose_override
        return self.paths.compose_dev if env == "dev" else self.paths.compose_prod

    def _latest_package_compose(self, env: str) -> Path | None:
        """Locate the newest packaged compose file for an environment."""
        if not self.paths.deploy_dir.exists():
            return None
        prefix = f"{env}_"
        candidates = sorted(
            (p for p in self.paths.deploy_dir.iterdir() if p.is_dir() and p.name.startswith(prefix)),
            key=lambda p: p.name,
            reverse=True,
        )
        for candidate in candidates:
            compose_candidate = candidate / f"docker-compose.{env}.yml"
            if compose_candidate.exists():
                return compose_candidate
        return None

    def _required_images_for_env(self, env: str) -> list[str]:
        ctx = self._compose_ctx(env)
        return required_images_from_compose(ctx.compose_file)