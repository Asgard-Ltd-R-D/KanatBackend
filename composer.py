#!/usr/bin/env python3
from __future__ import annotations
import sys
import io
import subprocess
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
from Composer_cli.utils.messages import error


def _configure_stdio() -> None:
    """Ensure stdout/stderr can emit unicode without crashing on narrow encodings."""
    preferred_encoding = "utf-8"
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding=preferred_encoding, errors="replace")
        except (AttributeError, ValueError):
            buffer = getattr(stream, "buffer", None)
            if buffer is None:
                continue
            wrapper = io.TextIOWrapper(buffer, encoding=preferred_encoding, errors="replace")
            setattr(sys, name, wrapper)


_configure_stdio()


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
              python composer.py --gui
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument("--gui", action="store_true", help="Launch the graphical dashboard")

    sub = p.add_subparsers(dest="command")

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
    p_rel.add_argument(
        "platform",
        choices=["win-x64", "linux-x64", "linux-musl-x64", "osx-arm64", "linux-arm64", "win-arm64", "osx-x64"],
    )

    return p


def _hide_terminal_window() -> None:
    if sys.platform != "darwin":
        return
    if not getattr(sys, "frozen", False):
        return
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Terminal" to if (count of windows) > 0 then set miniaturized of front window to true',
            ],
            check=False,
        )
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv and getattr(sys, "frozen", False):
        argv = ["--gui"]
        _hide_terminal_window()

    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "gui", False):
        try:
            from Composer_cli.gui import launch_gui
        except Exception as exc:  # pragma: no cover - GUI import fallback
            error(f"Unable to launch GUI: {exc}")
            return 1
        launch_gui()
        return 0

    if not getattr(args, "command", None):
        parser.print_help()
        return 1

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
