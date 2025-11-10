from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List

try:
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
except ImportError:
    import subprocess

    def _install_tkinter() -> None:
        """Attempt to install tkinter using pip. This may require system packages on some platforms."""
        python_executable = sys.executable or "python3"
        try:
            subprocess.check_call([python_executable, "-m", "pip", "install", "tk"])
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("Tkinter is required to launch the Composer GUI and could not be installed automatically.") from exc

    _install_tkinter()

    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

from ..paths import Paths


STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_MISSING = "missing"

STATUS_COLORS = {
    STATUS_ACTIVE: "#2ecc71",    # green
    STATUS_INACTIVE: "#e74c3c",  # red
    STATUS_MISSING: "#7f8c8d",   # gray
}


@dataclass(frozen=True)
class ComponentStatus:
    key: str
    name: str
    state: str
    ip: str
    port: str
    pid: str
    message: str = ""

    @property
    def details(self) -> str:
        return f"IP: {self.ip} | Port: {self.port} | PID: {self.pid}"


@dataclass(frozen=True)
class ContainerConfig:
    key: str
    label: str
    container_template: str
    default_port: str


CONTAINER_CONFIGS: tuple[ContainerConfig, ...] = (
    ContainerConfig(key="questdb", label="QuestDB", container_template="questdb-packets-{env}", default_port="9003"),
    ContainerConfig(key="postgres", label="Postgres", container_template="postgres-range-{env}", default_port="5432"),
    ContainerConfig(key="seq", label="Seq", container_template="seq-{env}", default_port="5341"),
)


class CommandRunner:
    """Execute composer commands via the existing CLI or packaged executable."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._script = project_root / "composer.py"
        self._exe = project_root / "composer"
        self._exe_win = project_root / "composer.exe"

    def _base_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable or "composer"]
        if self._exe.exists():
            return [str(self._exe)]
        if self._exe_win.exists():
            return [str(self._exe_win)]
        if self._script.exists():
            interpreter = sys.executable or "python3"
            return [interpreter, str(self._script)]
        raise FileNotFoundError("composer entrypoint not found (expecting composer/composer.exe or composer.py)")

    def run(self, args: list[str], log: Callable[[str], None]) -> int:
        command = self._base_command() + args
        log(f"$ {' '.join(command)}")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            log(f"✗ Failed to spawn process: {exc}")
            return 1

        assert process.stdout is not None
        for line in process.stdout:
            log(line.rstrip())
        return process.wait()

    def run_sequence(self, commands: Iterable[list[str]], log: Callable[[str], None]) -> int:
        rc = 0
        for args in commands:
            rc = self.run(args, log)
            if rc != 0:
                break
        return rc


def launch_gui() -> None:
    dashboard = ComposerDashboard()
    dashboard.run()


class ComposerDashboard:
    refresh_interval_ms = 4000

    def __init__(self) -> None:
        self.paths = Paths()
        self.root = tk.Tk()
        self.root.title("Composer Dashboard")
        self.root.geometry("1080x640")

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._closing = False
        self._operation_thread: threading.Thread | None = None
        self._runner = CommandRunner(self.paths.project_root)
        self._action_buttons: list[ttk.Button] = []
        self._env_radios: list[ttk.Radiobutton] = []
        self._status_rows: dict[str, ComponentRow] = {}

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.env_var = tk.StringVar(value="dev")

        self._build_layout()
        self._render_action_buttons()
        self._refresh_component_statuses()
        self._queue_log("Composer GUI ready. Select an environment to begin.")
        self._start_log_pump()
        self._schedule_status_refresh()

    # ----- UI construction -----
    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = ttk.Frame(main, width=280)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))

        # Controls (environment + actions)
        controls = ttk.Frame(left)
        controls.pack(fill=tk.X, pady=(0, 12))

        env_frame = ttk.Frame(controls)
        env_frame.pack(side=tk.LEFT, anchor=tk.NW)
        env_label = ttk.Label(env_frame, text="Environment:")
        env_label.pack(side=tk.LEFT, padx=(0, 8))

        dev_radio = ttk.Radiobutton(
            env_frame,
            text="Development",
            value="dev",
            variable=self.env_var,
            command=self._on_environment_change,
        )
        prod_radio = ttk.Radiobutton(
            env_frame,
            text="Production",
            value="prod",
            variable=self.env_var,
            command=self._on_environment_change,
        )
        dev_radio.pack(side=tk.LEFT, padx=(0, 6))
        prod_radio.pack(side=tk.LEFT)
        self._env_radios = [dev_radio, prod_radio]

        self.actions_frame = ttk.Frame(controls)
        self.actions_frame.pack(side=tk.RIGHT, anchor=tk.NE)

        # Log area
        log_container = ttk.Frame(left)
        log_container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(log_container, text="Activity Log").pack(anchor=tk.W)

        self.log_text = ScrolledText(log_container, wrap=tk.NONE, height=20, font=("Menlo", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.log_text.configure(state=tk.DISABLED)

        # Component sidebar
        ttk.Label(right, text="Components", font=("TkDefaultFont", 12, "bold")).pack(anchor=tk.W)

        for cfg in ("packetprocessing", "questdb", "postgres", "seq"):
            row = ComponentRow(right)
            row.pack(fill=tk.X, pady=6)
            self._status_rows[cfg] = row

    # ----- Event handlers -----
    def _on_environment_change(self) -> None:
        self._queue_log(f"Switched to {self._env_label(self.env_var.get())}")
        self._refresh_component_statuses()

    def _on_close(self) -> None:
        self._closing = True
        self.root.destroy()

    # ----- Logging -----
    def _queue_log(self, message: str) -> None:
        self._log_queue.put(message)

    def _start_log_pump(self) -> None:
        def pump() -> None:
            processed = False
            while True:
                try:
                    line = self._log_queue.get_nowait()
                except queue.Empty:
                    break
                else:
                    self._append_log(line)
                    processed = True
            if not self._closing:
                delay = 50 if processed else 150
                self.root.after(delay, pump)

        self.root.after(150, pump)

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{line}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ----- Buttons -----
    def _render_action_buttons(self) -> None:
        for child in self.actions_frame.winfo_children():
            child.destroy()
        self._action_buttons.clear()

        if _needs_quick_build(self.paths):
            btn = ttk.Button(self.actions_frame, text="Quick Build", command=self._handle_quick_build)
            btn.pack(side=tk.LEFT, padx=4)
            self._action_buttons.append(btn)
        else:
            up_btn = ttk.Button(self.actions_frame, text="Up", command=self._handle_up)
            stop_btn = ttk.Button(self.actions_frame, text="Stop", command=self._handle_stop)
            restart_btn = ttk.Button(self.actions_frame, text="Restart", command=self._handle_restart)
            kill_btn = ttk.Button(self.actions_frame, text="Kill", command=self._handle_kill)
            for btn in (up_btn, stop_btn, restart_btn, kill_btn):
                btn.pack(side=tk.LEFT, padx=4)
                self._action_buttons.append(btn)

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in self._action_buttons:
            btn.configure(state=state)
        for radio in self._env_radios:
            radio.configure(state=state)

    # ----- Operations -----
    def _handle_quick_build(self) -> None:
        self._start_operation("Quick Build", [["build"]])

    def _handle_up(self) -> None:
        env = self.env_var.get()
        self._start_operation(f"Up {env}", [["up", env, "-d"]])

    def _handle_stop(self) -> None:
        env = self.env_var.get()
        self._start_operation(f"Stop {env}", [["stop", env]])

    def _handle_restart(self) -> None:
        env = self.env_var.get()
        self._start_operation(f"Restart {env}", [["stop", env], ["up", env, "-d"]])

    def _handle_kill(self) -> None:
        env = self.env_var.get()
        self._start_operation(f"Kill {env}", [["kill", env]])

    def _start_operation(self, label: str, command_groups: Iterable[list[str]]) -> None:
        if self._operation_thread and self._operation_thread.is_alive():
            self._queue_log("⚠ An operation is already in progress.")
            return

        self._queue_log(f"== {label} ==")
        self._set_controls_enabled(False)

        def task() -> None:
            try:
                rc = self._runner.run_sequence(command_groups, self._queue_log)
            except Exception as exc:  # pragma: no cover - safety net for unexpected failures
                self._queue_log(f"✗ {label} failed: {exc}")
                rc = 1
            self._queue_log(f"{label} {'completed' if rc == 0 else 'failed'}")
            self.root.after(0, self._on_operation_complete, rc)

        self._operation_thread = threading.Thread(target=task, daemon=True)
        self._operation_thread.start()

    def _on_operation_complete(self, exit_code: int) -> None:
        self._operation_thread = None
        self._set_controls_enabled(True)
        self._render_action_buttons()
        self._refresh_component_statuses()
        if exit_code != 0:
            self._queue_log("⚠ Check logs above for details.")

    # ----- Status updates -----
    def _schedule_status_refresh(self) -> None:
        if self._closing:
            return
        self._refresh_component_statuses()
        self.root.after(self.refresh_interval_ms, self._schedule_status_refresh)

    def _refresh_component_statuses(self) -> None:
        env = self.env_var.get()
        statuses = _gather_component_statuses(self.paths, env)
        for status in statuses:
            row = self._status_rows.get(status.key)
            if not row:
                continue
            row.update(status)

    # ----- Helpers -----
    def _env_label(self, env: str) -> str:
        return "Development" if env == "dev" else "Production"

    def run(self) -> None:
        self.root.mainloop()


class ComponentRow(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, padding=(14, 12))
        self.columnconfigure(1, weight=1)

        self.indicator = tk.Canvas(self, width=16, height=16, highlightthickness=0)
        self._circle = self.indicator.create_oval(2, 2, 14, 14, fill=STATUS_COLORS[STATUS_MISSING], outline="")
        self.indicator.grid(row=0, column=0, rowspan=2, sticky=tk.NW, padx=(0, 8))

        self.name_label = ttk.Label(self, text="Component", font=("TkDefaultFont", 10, "bold"))
        self.name_label.grid(row=0, column=1, sticky=tk.W)

        self.details_label = ttk.Label(self, text="", font=("TkDefaultFont", 9))
        self.details_label.grid(row=1, column=1, sticky=tk.W)

        self.message_label = ttk.Label(self, text="", font=("TkDefaultFont", 8), foreground="#7f8c8d")
        self.message_label.grid(row=2, column=1, sticky=tk.W, pady=(2, 0))

    def update(self, status: ComponentStatus) -> None:
        color = STATUS_COLORS.get(status.state, STATUS_COLORS[STATUS_MISSING])
        self.indicator.itemconfigure(self._circle, fill=color)
        self.name_label.configure(text=status.name)
        self.details_label.configure(text=status.details)
        self.message_label.configure(text=status.message or "")


def _needs_quick_build(paths: Paths) -> bool:
    release_dir = paths.release_dir
    if not release_dir.exists():
        return True
    for env in ("dev", "prod"):
        env_dir = release_dir / env
        if not env_dir.exists():
            return True
        dll = env_dir / "PacketProcessing.dll"
        if not dll.exists():
            return True
    return False


def _gather_component_statuses(paths: Paths, env: str) -> List[ComponentStatus]:
    statuses: list[ComponentStatus] = [
        _packetprocessing_status(paths, env),
    ]
    for cfg in CONTAINER_CONFIGS:
        statuses.append(_container_status(cfg, env))
    return statuses


def _packetprocessing_status(paths: Paths, env: str) -> ComponentStatus:
    release_dir = paths.release_dir / env
    dll_path = release_dir / "PacketProcessing.dll"
    name = f"PacketProcessing ({env})"
    port = "10901" if env == "dev" else "10900"

    if not release_dir.exists() or not dll_path.exists():
        return ComponentStatus(
            key="packetprocessing",
            name=name,
            state=STATUS_MISSING,
            ip="-",
            port="-",
            pid="-",
            message="Artifacts missing. Run Quick Build.",
        )

    running, pid = _detect_process(dll_path)
    state = STATUS_ACTIVE if running else STATUS_INACTIVE

    return ComponentStatus(
        key="packetprocessing",
        name=name,
        state=state,
        ip="127.0.0.1" if running else "-",
        port=port if running else port,
        pid=pid if running else "-",
        message="Running" if running else "Not running",
    )


def _detect_process(dll_path: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["pgrep", "-fl", str(dll_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "-"

    if result.returncode != 0 or not result.stdout.strip():
        return False, "-"

    line = result.stdout.strip().splitlines()[0]
    pid = line.split(maxsplit=1)[0]
    return True, pid


def _container_status(cfg: ContainerConfig, env: str) -> ComponentStatus:
    container_name = cfg.container_template.format(env=env)
    name = f"{cfg.label} ({env})"

    try:
        result = subprocess.run(
            ["docker", "inspect", container_name],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ComponentStatus(
            key=cfg.key,
            name=name,
            state=STATUS_MISSING,
            ip="-",
            port="-",
            pid="-",
            message="Docker not available",
        )

    if result.returncode != 0 or not result.stdout.strip():
        return ComponentStatus(
            key=cfg.key,
            name=name,
            state=STATUS_MISSING,
            ip="-",
            port="-",
            pid="-",
            message="Container not found",
        )

    try:
        data = json.loads(result.stdout)[0]
    except (json.JSONDecodeError, IndexError):
        return ComponentStatus(
            key=cfg.key,
            name=name,
            state=STATUS_MISSING,
            ip="-",
            port="-",
            pid="-",
            message="Unable to inspect container",
        )

    state_info = data.get("State", {})
    running = bool(state_info.get("Running"))
    pid = str(state_info.get("Pid") or "-")
    status_text = state_info.get("Status") or ("running" if running else "stopped")

    net_settings = data.get("NetworkSettings", {})
    networks = net_settings.get("Networks") or {}
    if networks:
        first_network = next(iter(networks.values()))
        ip = first_network.get("IPAddress") or "-"
    else:
        ip = "-"

    ports = net_settings.get("Ports") or {}
    port_display = cfg.default_port
    if ports:
        first_key = next(iter(ports.keys()))
        mapping = ports.get(first_key)
        if isinstance(mapping, list) and mapping:
            host_port = mapping[0].get("HostPort") or ""
            port_display = host_port or first_key
        else:
            port_display = first_key

    state = STATUS_ACTIVE if running else STATUS_INACTIVE

    return ComponentStatus(
        key=cfg.key,
        name=name,
        state=state,
        ip=ip if running else "-",
        port=port_display,
        pid=pid if running else "-",
        message=status_text.capitalize(),
    )


