from __future__ import annotations
from .base import Command

class UpCommand(Command):
    name = "up"
    help = "Run environment (builds/loads if needed)"

    def run(self, usecases, args) -> int:
        env = getattr(args, "environment", None) or "prod"
        det = getattr(args, "detached", False)
        return usecases.up(env, det, args)