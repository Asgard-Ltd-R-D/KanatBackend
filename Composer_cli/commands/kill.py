from __future__ import annotations
from .base import Command

class KillCommand(Command):
    name = "kill"
    help = "Kill environment (containers + DLLs)"

    def run(self, usecases, args) -> int:
        env = getattr(args, "environment", None) or "prod"
        return usecases.kill(env)