from __future__ import annotations
from .base import Command

class ReleaseCommand(Command):
    name = "release"
    help = "Create release packages for a platform"

    def run(self, usecases, args) -> int:
        return usecases.release(args.platform)