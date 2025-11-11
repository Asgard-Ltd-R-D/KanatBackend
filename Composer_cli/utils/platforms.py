from __future__ import annotations

import os
from typing import Optional

_RID_TO_DOCKER_PLATFORM = {
    "linux-x64": "linux/amd64",
    "linux-musl-x64": "linux/amd64",
    "linux-arm64": "linux/arm64",
}


def current_build_rid() -> Optional[str]:
    """Return the runtime identifier selected for the current build, if any."""
    return os.getenv("KANAT_BUILD_PLATFORM") or os.getenv("KANAT_TARGET_RID")


def docker_platform_for_rid(rid: Optional[str]) -> Optional[str]:
    """Translate a .NET runtime identifier into a Docker platform string."""
    if not rid:
        return None
    return _RID_TO_DOCKER_PLATFORM.get(rid)


def docker_platform_for_current_build() -> Optional[str]:
    """Resolve the Docker platform string for the current build context."""
    return docker_platform_for_rid(current_build_rid())

