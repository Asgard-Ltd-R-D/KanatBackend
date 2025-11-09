from __future__ import annotations

from .base import Command


class BuildCommand(Command):
    name = "build"
    help = "Build release binaries for dev and prod environments"

    def run(self, usecases, args) -> int:
        return usecases.build_all()

