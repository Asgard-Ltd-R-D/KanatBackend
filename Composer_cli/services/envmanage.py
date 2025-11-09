from __future__ import annotations
from ..abstractions import EnvManager, ComposeContext
from ..shell import SubprocessShell

class DefaultEnvManager(EnvManager):
    def __init__(self, shell: SubprocessShell | None = None) -> None:
        self.sh = shell or SubprocessShell()

    def is_running(self, ctx: ComposeContext) -> bool:
        code, out, _ = self.sh.run_capture(
            ["docker", "compose", "-p", ctx.project_name, "-f", str(ctx.compose_file), "ps", "-q"],
            cwd=ctx.work_dir
        )
        if code != 0 or not out.strip():
            return False
        for cid in out.strip().splitlines():
            c2, s, _ = self.sh.run_capture(["docker", "inspect", "--format", "{{.State.Status}}", cid])
            if c2 == 0 and s.strip() == "running":
                return True
        return False

    def stop_env(self, ctx: ComposeContext) -> bool:
        return self.sh.run(
            ["docker", "compose", "-p", ctx.project_name, "-f", str(ctx.compose_file), "stop"],
            cwd=ctx.work_dir, check=False
        ) == 0

    def kill_env(self, ctx: ComposeContext) -> bool:
        self.stop_env(ctx)
        return self.sh.run(
            ["docker", "compose", "-p", ctx.project_name, "-f", str(ctx.compose_file), "rm", "-f"],
            cwd=ctx.work_dir, check=False
        ) == 0