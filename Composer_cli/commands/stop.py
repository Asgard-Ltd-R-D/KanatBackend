from __future__ import annotations
from .base import Command

class StopCommand(Command):
    name = "stop"
    help = "Stop environment"

    def run(self, usecases, args) -> int:
        env = getattr(args, "environment", None) or "prod"
        return usecases.stop(env)