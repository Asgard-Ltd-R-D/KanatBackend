from __future__ import annotations

import os
from typing import Optional, Sequence

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
    explicit = _platforms_from_env()
    if explicit:
        # Preserve existing behaviour for callers that expect a single string.
        return explicit[0]
    return docker_platform_for_rid(current_build_rid())


def docker_platforms_for_current_build() -> Optional[Sequence[str]]:
    """
    Resolve all Docker platforms requested for the current build context.

    Preference order:
      1. Explicit KANAT_DOCKER_PLATFORMS env (comma-separated list)
      2. Single platform inferred from KANAT_BUILD_PLATFORM / KANAT_TARGET_RID
    """
    explicit = _platforms_from_env()
    if explicit:
        return explicit
    inferred = docker_platform_for_rid(current_build_rid())
    if inferred:
        return (inferred,)
    return None


def _platforms_from_env() -> Optional[Sequence[str]]:
    raw = os.getenv("KANAT_DOCKER_PLATFORMS", "")
    if not raw:
        return None
    platforms = tuple(item.strip() for item in raw.split(",") if item.strip())
    return platforms or None

