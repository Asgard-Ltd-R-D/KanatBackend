from __future__ import annotations
from typing import Protocol, Dict

from Composer_cli.abstractions import ComposerUseCases

class Command(Protocol):
    name: str
    help: str
    def run(self, usecases: ComposerUseCases, args) -> int: ...

class CommandRegistry:
    def __init__(self) -> None:
        self._commands: Dict[str, Command] = {}
    def register(self, cmd: Command) -> None:
        self._commands[cmd.name] = cmd
    def get(self, name: str) -> Command | None:
        return self._commands.get(name)