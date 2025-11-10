from __future__ import annotations

import os
import shutil
import tarfile
from pathlib import Path
from typing import Tuple

from ..abstractions import DockerService, PackagingService
from ..progress import Progress
from ..shell import SubprocessShell
from ..paths import Paths, RELEASE_DIR

ALLOWED_PLATFORMS = {"win-x64", "linux-x64", "linux-musl-x64", "osx-arm64"}
CUSTOM_IMAGE = ("kanatbackend-questdb", "kanatbackend-questdb.tar")
SHARED_IMAGES = (
    ("postgres:15-alpine", "postgres_15-alpine.tar"),
    ("datalust/seq:latest", "datalust_seq_latest.tar"),
)


class DefaultPackagingService(PackagingService):
    """
    Create versioned release packages that bundle PacketProcessingService outputs,
    Docker images, and compose assets for offline deployment.
    """

    def __init__(
        self,
        shell: SubprocessShell | None = None,
        progress: Progress | None = None,
        paths: Paths | None = None,
        docker: DockerService | None = None,
    ) -> None:
        self.sh = shell or SubprocessShell()
        self.progress = progress or Progress()
        self.paths = paths or Paths()
        self.docker = docker or self._fallback_docker_service()

    def create_release(self, platform: str) -> bool:
        if platform not in ALLOWED_PLATFORMS:
            print(f"✗ Unsupported platform '{platform}'. Expected one of {sorted(ALLOWED_PLATFORMS)}")
            return False

        if not self._validate_release_builds():
            return False

        skip_docker = self._skip_docker()

        if not skip_docker:
            if not self._ensure_custom_image():
                return False

            if not self._ensure_shared_images():
                return False
        else:
            self._notify_docker_skipped()

        success = True

        for env in ("dev", "prod"):
            package_dir = self.paths.deploy_dir / env
            if package_dir.exists():
                shutil.rmtree(package_dir)
            package_dir.mkdir(parents=True, exist_ok=True)

            if not self._write_packetprocessing_tar(env, platform, package_dir):
                success = False
                continue

        self._refresh_root_assets()
        if not skip_docker and not self._export_shared_images():
            success = False

        if success:
            print(f"✓ Release packages created under {self.paths.deploy_dir}")
        else:
            print("✗ Some release artifacts failed to build")
        return success

    # -------- helpers --------
    def _fallback_docker_service(self) -> DockerService:
        from .docker import DefaultDockerService  # local import to avoid cycle

        return DefaultDockerService(self.sh)

    def _validate_release_builds(self) -> bool:
        required = {
            "dev": RELEASE_DIR / "dev" / "PacketProcessingService.dll",
            "prod": RELEASE_DIR / "prod" / "PacketProcessingService.dll",
        }
        missing = [env for env, path in required.items() if not path.exists()]
        if missing:
            missing_str = ", ".join(missing)
            print(f"✗ Missing PacketProcessingService builds for: {missing_str}. Run 'composer build' first.")
            return False
        return True

    def _ensure_shared_images(self) -> bool:
        ok = True
        for image, _ in SHARED_IMAGES:
            if self.docker.image_exists(image):
                continue
            print(f"⚠ Docker image '{image}' missing; pulling…")
            if self.sh.run(["docker", "pull", image], check=False) != 0:
                print(f"✗ Failed to pull docker image '{image}'")
                ok = False
        return ok

    def _write_packetprocessing_tar(self, env: str, platform: str, package_dir: Path) -> bool:
        source_dir = self.paths.release_dir / env
        if not source_dir.exists():
            print(f"✗ Release output missing for environment '{env}'")
            return False

        tar_path = package_dir / f"packetprocessing_{env}_{platform}.tar"
        try:
            with tarfile.open(tar_path, "w") as tar:
                for path in sorted(source_dir.rglob("*")):
                    arcname = path.relative_to(source_dir)
                    tar.add(path, arcname=str(arcname))
        except Exception as exc:
            print(f"✗ Failed to create PacketProcessingService archive for {env}: {exc}")
            return False
        return True

    def _export_shared_images(self) -> bool:
        items: list[Tuple[str, Path]] = [
            (CUSTOM_IMAGE[0], self.paths.deploy_dir / CUSTOM_IMAGE[1])
        ]
        for image, name in SHARED_IMAGES:
            items.append((image, self.paths.deploy_dir / name))

        ok = True
        for image, target in items:
            target.parent.mkdir(parents=True, exist_ok=True)
            cache_name = self._sanitized_image_name(image)
            cache_tar = self.paths.image_cache_dir / f"{cache_name}.tar"
            if cache_tar.exists():
                shutil.copy2(cache_tar, target)
                continue
            if self.docker.save_image_tar(image, target):
                continue
            print(f"✗ Failed to export docker image '{image}' to {target.name}")
            ok = False
        return ok

    def _ensure_custom_image(self) -> bool:
        image, _ = CUSTOM_IMAGE
        if self.docker.image_exists(image):
            return True
        if not self.paths.questdb_dir.exists():
            print(f"✗ QuestDB directory not found at {self.paths.questdb_dir}")
            return False
        print(f"⚠ Docker image '{image}' missing; building with buildx…")
        dockerfile = self.paths.questdb_dir / "Dockerfile"
        if not self.docker.build_image(image, self.paths.questdb_dir, dockerfile):
            print(f"✗ Failed to build docker image '{image}' from QuestDB Dockerfile")
            return False
        cache_name = self._sanitized_image_name(image)
        cache_tar = self.paths.image_cache_dir / f"{cache_name}.tar"
        if not cache_tar.exists():
            self.docker.save_image_tar(image, cache_tar)
        return True

    def _refresh_root_assets(self) -> None:
        """Ensure root-level compose files and QuestDB directory are up to date in packages."""
        for env in ("dev", "prod"):
            package_dir = self.paths.deploy_dir / env
            if package_dir.exists():
                for item in package_dir.iterdir():
                    if item.name.startswith("packetprocessing_"):
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

        for src in (self.paths.compose_dev, self.paths.compose_prod):
            if src.exists():
                shutil.copy2(src, self.paths.deploy_dir / src.name)
        if self.paths.questdb_dir.exists():
            questdb_target = self.paths.deploy_dir / "QuestDB"
            if questdb_target.exists():
                shutil.rmtree(questdb_target)
            shutil.copytree(self.paths.questdb_dir, questdb_target)

    @staticmethod
    def _sanitized_image_name(image: str) -> str:
        return image.replace("/", "_").replace(":", "_")

    @staticmethod
    def _skip_docker() -> bool:
        value = os.getenv("KANAT_SKIP_DOCKER", "")
        return value.lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _notify_docker_skipped() -> None:
        print("⚠ Docker image packaging skipped (KANAT_SKIP_DOCKER set).")