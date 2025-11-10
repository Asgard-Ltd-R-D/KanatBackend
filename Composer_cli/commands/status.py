from __future__ import annotations
from .base import Command

class StatusCommand(Command):
    name = "status"
    help = "Show system status"

    def run(self, usecases, args) -> int:
        return usecases.status()