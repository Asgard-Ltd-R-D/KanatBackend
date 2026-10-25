"""The Detection Service's logs: one JSON object a line in detection.log, and
a readable line on the console, as the WebApp backend's
(WebApp/backend/app/core/logs.py), beside its backend.log and the app's
frontend.log, where Grafana Alloy ships them to Loki (WebApp/observability).

detection.log is in --log-dir, else KANAT_LOG_DIR (/var/log/kanat on the
range PC), else the repo's WebApp/logs when it exists; with none, the service
logs to the console only. The command line (new_bullet_holes.py) logs to the
console only: its runs are not the range's.

What happens while the service runs is logged, at the level it deserves; the
command line's report stays printed. A log call adds its own fields with
`extra`, which become JSON fields that Grafana filters on:

    log.warning("Bullet Hole not posted", extra={"session_id": session_id})

A field may not take the name of a LogRecord attribute (`name`, `message`,
`args`, `module`...). A line logged without a session_id carries the active
Run's (`current_session`), whichever thread logged it.
"""
import json
import logging
import logging.handlers
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

LOG_FILE = "detection.log"
# As the backend's and the app's: 10 files of 10 MB at most
MAX_BYTES = 10 * 1024 * 1024
BACKUPS = 10

# The Session whose Run is active, set by service.py: there is one Run at a
# time (ADR-0008), so every line logged meanwhile is that Session's, the
# Stream's reader thread and the poster's included
current_session: uuid.UUID | None = None

# The attributes every LogRecord has: anything else on one came from `extra`
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "taskName"}


def _fields(record: logging.LogRecord) -> dict:
    """The fields the log call added with `extra`."""
    return {key: value for key, value in vars(record).items() if key not in _STANDARD and not key.startswith("_")}


def _plain(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    return str(value)


class JsonFormatter(logging.Formatter):
    """One JSON object a line: time, level, service, logger, message, the
    Session, the call's own fields, and the exception if any."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": "detection",
            "logger": record.name,
            "message": record.getMessage(),
        }
        if current_session is not None:
            entry["session_id"] = str(current_session)
        entry.update({key: _plain(value) for key, value in _fields(record).items()})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """A readable line for the terminal: time, level, logger, message, fields."""

    def format(self, record: logging.LogRecord) -> str:
        when = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        fields = " ".join(f"{key}={_plain(value)}" for key, value in _fields(record).items())
        line = f"{when} {record.levelname:<7} {record.name}: {record.getMessage()}" + (f"  {fields}" if fields else "")
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def log_dir(configured: Path | None = None) -> Path | None:
    if configured:
        return configured
    if os.environ.get("KANAT_LOG_DIR"):
        return Path(os.environ["KANAT_LOG_DIR"])
    dev = Path(__file__).resolve().parents[2] / "WebApp" / "logs"
    return dev if dev.is_dir() else None


def configure(configured: Path | None = None, to_file: bool = True, level: str = "INFO") -> Path | None:
    """Sends every logger to the console and, with `to_file`, to detection.log.
    Returns the file's path, or None without one. Safe to call again: the
    handlers are replaced, not added."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(ConsoleFormatter())
    root.addHandler(console)

    directory = log_dir(configured) if to_file else None
    if directory is None:
        return None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file = logging.handlers.RotatingFileHandler(
            directory / LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
        )
    except OSError as e:
        logging.getLogger(__name__).warning("Logging to %s failed, console only: %s", directory, e)
        return None
    file.setFormatter(JsonFormatter())
    root.addHandler(file)
    return directory / LOG_FILE
