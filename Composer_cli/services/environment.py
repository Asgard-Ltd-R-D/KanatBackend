from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
import os
from typing import Callable, List, Sequence

from ..abstractions import DockerService, DotnetService
from ..paths import Paths
from ..utils.messages import info, warn, error, success


class EnvironmentManager:
    """Handle building PacketProcessingService and preparing Docker artifacts for environments."""

    def __init__(self, paths: Paths, docker: DockerService, dotnet: DotnetService) -> None:
        self.paths = paths
        self.docker = docker
        self.dotnet = dotnet
        self._docker_skipped_notified = False

    def build_all(self, required_images_provider: Callable[[str], List[str]]) -> bool:
        """Build both environments and ensure required Docker images are cached."""
        skip_docker = self._skip_docker()
        for env in ("dev", "prod"):
            release_dir = self.paths.release_dir / env
            if release_dir.exists():
                shutil.rmtree(release_dir)

            if not self.dotnet.project_exists():
                if not self._rehydrate_release_from_packages(env, release_dir):
                    error(f"Missing package artifacts for '{env}'. Run build on a source machine first.")
                    return False
            else:
                if not self.dotnet.build_environment(env, release_dir):
                    return False
            if not self.dotnet.project_exists():
                self.dotnet.sync_runtime_assets(env, release_dir)

            required_images = required_images_provider(env)
            if skip_docker:
                self._maybe_notify_docker_skipped()
                continue
            if not self.docker.prepare_images(
                env,
                required_images,
                self.paths.image_cache_dir,
                self.paths.deploy_dir,
                self.paths.questdb_dir,
            ):
                return False
        success("Build complete for dev and prod environments")
        return True

    def ensure_releases_present(self, required_images_provider: Callable[[str], List[str]]) -> bool:
        """Ensure release DLLs exist for dev and prod, triggering a build if necessary."""
        dev = self.paths.release_dir / "dev" / "PacketProcessingService.dll"
        prod = self.paths.release_dir / "prod" / "PacketProcessingService.dll"
        if dev.exists() and prod.exists():
            return True
        if not self.dotnet.project_exists():
            for env in ("dev", "prod"):
                release_dir = self.paths.release_dir / env
                if release_dir.exists():
                    shutil.rmtree(release_dir)
                if not self._rehydrate_release_from_packages(env, release_dir):
                    error(f"Missing package artifacts for '{env}'. Run build on a source machine first.")
                    return False
            return True
        warn("Release binaries missing; running full build...")
        return self.build_all(required_images_provider)

    def ensure_environment_ready(self, env: str, required_images: List[str]) -> bool:
        """Verify artifacts for an environment and prepare Docker images."""
        dll_dir = self.paths.release_dir / env
        dll_path = dll_dir / "PacketProcessingService.dll"
        have_dll = dll_path.exists()

        dotnet_env = "Development" if env == "dev" else "Production"
        config_files = ("appsettings.json", f"appsettings.{dotnet_env}.json")
        assets_missing = any(not (dll_dir / name).exists() for name in config_files) or not (dll_dir / "wwwroot").exists()

        if not have_dll and self._rehydrate_release_from_packages(env, dll_dir):
            have_dll = dll_path.exists()
            assets_missing = False

        if self.dotnet.project_exists():
            if not have_dll:
                warn(f"Building PacketProcessingService for '{env}'...")
                if not self.dotnet.build_environment(env, dll_dir):
                    return False
            elif assets_missing:
                warn(f"Syncing runtime assets for '{env}'...")
                self.dotnet.sync_runtime_assets(env, dll_dir)
        elif not have_dll:
            error(f"Missing package artifacts for '{env}'. Run build on a source machine first.")
            return False
        else:
            self.dotnet.sync_runtime_assets(env, dll_dir)

        if self._skip_docker():
            self._maybe_notify_docker_skipped()
            return True

        return self.docker.prepare_images(
            env,
            required_images,
            self.paths.image_cache_dir,
            self.paths.deploy_dir,
            self.paths.questdb_dir,
        )

    def _skip_docker(self) -> bool:
        value = os.getenv("KANAT_SKIP_DOCKER", "")
        return value.lower() in {"1", "true", "yes", "on"}

    def _maybe_notify_docker_skipped(self) -> None:
        if self._docker_skipped_notified:
            return
            warn("Docker image preparation skipped (KANAT_SKIP_DOCKER set).")
        self._docker_skipped_notified = True

    def _rehydrate_release_from_packages(self, env: str, target_dir: Path) -> bool:
        """Restore release binaries for an environment from packaged artifacts."""
        direct_dir = self.paths.deploy_dir / env
        tarballs: list[Path] = []
        if direct_dir.exists():
            tarballs = list(direct_dir.glob(f"packetprocessing_{env}_*.tar"))
            if tarballs:
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                target_dir.mkdir(parents=True, exist_ok=True)
                self._extract_package_contents(tarballs, target_dir)
                return True

        prefix = f"{env}_"
        if not self.paths.deploy_dir.exists():
            return False
        candidates = sorted(
            (p for p in self.paths.deploy_dir.iterdir() if p.is_dir() and p.name.startswith(prefix)),
            key=lambda p: p.name,
            reverse=True,
        )
        for candidate in candidates:
            tarballs = list(candidate.glob(f"packetprocessing_{env}_*.tar"))
            if not tarballs:
                continue
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            self._extract_package_contents(tarballs, target_dir)
            return True
        return False

    def _extract_package_contents(self, tarballs: Sequence[Path], target_dir: Path) -> None:
        """Extract package tarballs into the given release directory."""
        for tar_file in sorted(tarballs):
            info(f"Extracting {tar_file.name} into {target_dir}")
            with tarfile.open(tar_file, "r") as archive:
                archive.extractall(target_dir)

