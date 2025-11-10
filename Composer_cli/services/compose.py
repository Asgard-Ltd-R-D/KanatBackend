from __future__ import annotations
from ..abstractions import ComposeService, ComposeContext
from ..shell import SubprocessShell

class DefaultComposeService(ComposeService):
    def __init__(self, shell: SubprocessShell | None = None) -> None:
        self.sh = shell or SubprocessShell()

    def build(self, ctx: ComposeContext, no_cache: bool = False) -> bool:
        cmd = ["docker", "compose", "-p", ctx.project_name, "-f", str(ctx.compose_file), "build"]
        if no_cache:
            cmd.append("--no-cache")
        return self.sh.run(cmd, cwd=ctx.work_dir, check=False) == 0

    def up(self, ctx: ComposeContext, detached: bool, build_if_missing: bool = True) -> bool:
        cmd = ["docker", "compose", "-p", ctx.project_name, "-f", str(ctx.compose_file), "up"]
        if detached:
            cmd.append("-d")
        cmd.extend(["--pull", "never"])
        return self.sh.run(cmd, cwd=ctx.work_dir, check=False) == 0

    def stop(self, ctx: ComposeContext) -> bool:
        cmd = ["docker", "compose", "-p", ctx.project_name, "-f", str(ctx.compose_file), "stop"]
        return self.sh.run(cmd, cwd=ctx.work_dir, check=False) == 0

    def remove(self, ctx: ComposeContext) -> bool:
        cmd = ["docker", "compose", "-p", ctx.project_name, "-f", str(ctx.compose_file), "rm", "-f"]
        return self.sh.run(cmd, cwd=ctx.work_dir, check=False) == 0

    def logs_follow(self, ctx: ComposeContext) -> None:
        cmd = ["docker", "compose", "-p", ctx.project_name, "-f", str(ctx.compose_file), "logs", "-f"]
        self.sh.popen_stream(cmd, cwd=ctx.work_dir)