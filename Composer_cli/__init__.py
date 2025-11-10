from __future__ import annotations

# Public API surface of the package
from .app import ComposerApp
from .paths import Paths

# Re-export protocol types for typing-friendly imports (optional)
from .abstractions import (
    ComposeContext,
    BuildResult,
    Shell,
    Progress,
    ProgressTask,
    DockerService,
    DotnetService,
    ComposeService,
    PackagingService,
    EnvManager,
    ComposerUseCases,
)

__all__ = [
    "ComposerApp",
    "Paths",
    "ComposeContext",
    "BuildResult",
    "Shell",
    "Progress",
    "ProgressTask",
    "DockerService",
    "DotnetService",
    "ComposeService",
    "PackagingService",
    "EnvManager",
    "ComposerUseCases",
]