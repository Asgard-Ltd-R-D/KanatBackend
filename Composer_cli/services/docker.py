from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence

from ..abstractions import DockerService
from ..shell import SubprocessShell
from ..utils.messages import info, warn, error


class DefaultDockerService(DockerService):
    def __init__(self, shell: SubprocessShell | None = None) -> None:
        self.sh = shell or SubprocessShell()

    def is_available(self) -> bool:
        code, out, _ = self.sh.run_capture(["docker", "--version"])
        return code == 0 and bool(out.strip())

    def images_exist(self, images: Iterable[str]) -> bool:
        return all(self.image_exists(i) for i in images)

    def image_exists(self, name: str) -> bool:
        code, out, _ = self.sh.run_capture(["docker", "images", "-q", name])
        return code == 0 and bool(out.strip())

    def load_image_tar(self, tar_path: Path) -> bool:
        return self.sh.run(["docker", "load", "-i", str(tar_path)], check=False) == 0

    def save_image_tar(self, image: str, target: Path) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        return self.sh.run(["docker", "save", "-o", str(target), image], check=False) == 0

    def build_image(
        self,
        tag: str,
        context: Path,
        dockerfile: Optional[Path] = None,
        platforms: Optional[Sequence[str]] = None,
    ) -> bool:
        cmd = ["docker", "buildx", "build", "--load", "-t", tag]
        if dockerfile:
            cmd.extend(["-f", str(dockerfile)])
        if platforms:
            cmd.extend(["--platform", ",".join(platforms)])
        cmd.append(str(context))
        return self.sh.run(cmd, check=False) == 0

    def prepare_images(
        self,
        env: str,
        required_images: Iterable[str],
        image_cache_dir: Path,
        deploy_dir: Path,
        questdb_dir: Path,
    ) -> bool:
        """Ensure all required images are available locally, preferring cache and falling back to build/pull."""
        for image in required_images:
            if self.image_exists(image):
                self._cache_image(image, image_cache_dir)
                continue
            if self._load_from_cache(image, image_cache_dir, deploy_dir):
                self._cache_image(image, image_cache_dir)
                continue

            if image.startswith("kanatbackend-questdb"):
                warn(f"Building custom image '{image}' via buildx...")
                dockerfile = questdb_dir / "Dockerfile"
                if not self.build_image(image, questdb_dir, dockerfile):
                    error(f"docker buildx build failed for {image}")
                    return False
                self._cache_image(image, image_cache_dir)
                continue

            warn(f"Pulling docker image '{image}' for {env}...")
            if not self._pull_image(image):
                error(f"Failed to pull docker image '{image}'")
                return False
            self._cache_image(image, image_cache_dir)

        return True

    def ps_table(self) -> str:
        code, out, _ = self.sh.run_capture(
            ["docker", "ps", "-a", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"]
        )
        return out if code == 0 else ""

    # ----- helpers -----

    def _cache_image(self, image: str, image_cache_dir: Path) -> None:
        if not self.image_exists(image):
            return
        tar_path = image_cache_dir / f"{self._sanitized_image_name(image)}.tar"
        if tar_path.exists():
            return
        tar_path.parent.mkdir(parents=True, exist_ok=True)
        if self.save_image_tar(image, tar_path):
            info(f"Cached docker image '{image}' at {tar_path}")

    def _load_from_cache(self, image: str, image_cache_dir: Path, deploy_dir: Path) -> bool:
        """Attempt to load an image tarball from the cache or packaged artifacts."""
        for tar_path in self._image_tar_candidates(image, image_cache_dir, deploy_dir):
            info(f"Loading docker image '{image}' from cache ({tar_path})")
            if self.load_image_tar(tar_path):
                return True
        return False

    def _image_tar_candidates(self, image: str, image_cache_dir: Path, deploy_dir: Path) -> list[Path]:
        """Return potential tarball paths for a cached image ordered by preference."""
        safe_name = self._sanitized_image_name(image)
        candidates: list[Path] = []
        visited: set[Path] = set()
        for base in (image_cache_dir, deploy_dir):
            if not base.exists():
                continue
            direct = base / f"{safe_name}.tar"
            if direct.exists() and direct not in visited:
                candidates.append(direct)
                visited.add(direct)
            for tar in base.rglob(f"{safe_name}.tar"):
                if tar not in visited:
                    candidates.append(tar)
                    visited.add(tar)
        return candidates

    def _pull_image(self, image: str) -> bool:
        """Pull a docker image from the registry."""
        return self.sh.run(["docker", "pull", image], check=False) == 0

    @staticmethod
    def _sanitized_image_name(image: str) -> str:
        """Convert an image reference into a filesystem-safe file name."""
        return image.replace("/", "_").replace(":", "_")