#!/usr/bin/env python3
from __future__ import annotations
import sys
import argparse
import textwrap

from Composer_cli.app import ComposerApp
from Composer_cli.commands.base import CommandRegistry
from Composer_cli.commands.up import UpCommand
from Composer_cli.commands.stop import StopCommand
from Composer_cli.commands.kill import KillCommand
from Composer_cli.commands.status import StatusCommand
from Composer_cli.commands.build import BuildCommand
from Composer_cli.commands.release import ReleaseCommand


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="composer",
        description="composer - Build and run PacketProcessing with Docker Compose",
        epilog=textwrap.dedent(
            """\
            Examples:
              python composer.py up prod -d
              python composer.py status
              python composer.py build
              python composer.py release osx-arm64
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = p.add_subparsers(dest="command", required=True)

    # up
    p_up = sub.add_parser("up", help="Run environment (builds/loads if needed)")
    p_up.add_argument(
        "environment",
        choices=["dev", "prod"],
        nargs="?",
        default="prod",
        help="Environment to start (default: prod)",
    )
    p_up.add_argument("-d", "--detached", action="store_true")

    # stop
    p_stop = sub.add_parser("stop", help="Stop environment")
    p_stop.add_argument(
        "environment",
        choices=["dev", "prod"],
        nargs="?",
        default="prod",
        help="Environment to stop (default: prod)",
    )

    # kill
    p_kill = sub.add_parser("kill", help="Kill environment (containers + DLLs)")
    p_kill.add_argument(
        "environment",
        choices=["dev", "prod"],
        nargs="?",
        default="prod",
        help="Environment to kill (default: prod)",
    )

    # status
    sub.add_parser("status", help="Show system status")

    # build (build both environments)
    sub.add_parser("build", help="Build both environments (offline-first)")

    # release
    p_rel = sub.add_parser("release", help="Create release packages for a platform")
    p_rel.add_argument("platform", choices=["win-x64", "linux-x64", "linux-musl-x64", "osx-arm64"])

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    # Register commands
    registry = CommandRegistry()
    registry.register(UpCommand())
    registry.register(StopCommand())
    registry.register(KillCommand())
    registry.register(StatusCommand())
    registry.register(BuildCommand())
    registry.register(ReleaseCommand())

    app = ComposerApp(registry)
    return app.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
