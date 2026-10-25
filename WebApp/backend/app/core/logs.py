"""The backend's logs: one JSON object a line in backend.log, and a readable
line on the console.

backend.log is in the WebApp's log folder, WebApp/logs unless LOG_DIR says
otherwise (/var/log/kanat on the range PC), beside the app's own
frontend.log (frontend/electron/logs.ts). Grafana Alloy ships the folder to
Loki, and Grafana shows it (WebApp/observability).

A log call adds its own fields with `extra`, and they become JSON fields that
Grafana filters on:

    log.info("Session created", extra={"session_id": session.id, "record": True})

A field may not take the name of a LogRecord attribute (`name`, `message`,
`args`, `module`...): use e.g. `session_name`. Every line logged while a request
is handled also carries its `request_id` (core/request_log.py).
"""
import contextvars
import json
import logging
import logging.handlers
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from app.config.settings import settings

# The request being handled, set by core/request_log.py
request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

LOG_FILE = "backend.log"
# Rotated at this size, keeping this many old files: at most ~110 MB on disk,
# and Loki keeps its own copy for its retention period
MAX_BYTES = 10 * 1024 * 1024
BACKUPS = 10

# What every LogRecord has, so that what is left over came from `extra`
# color_message: uvicorn's own copy of its message, with terminal colours
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName", "color_message"}


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
    request's id, the call's own fields, and the exception if any."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": "backend",
            "logger": record.name,
            "message": record.getMessage(),
        }
        if (current := request_id.get()) is not None:
            entry["request_id"] = current
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


class _RequestFailure(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage() != "Exception in ASGI application"


def log_dir() -> Path:
    # app/core/logs.py -> WebApp/logs
    return Path(settings.log_dir) if settings.log_dir else Path(__file__).resolve().parents[3] / "logs"


def configure_logging() -> None:
    """Sends every logger (the app's, uvicorn's) to the console and the JSON
    file. Safe to call again: the handlers are replaced, not added."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(settings.log_level.upper())

    console = logging.StreamHandler()
    console.setFormatter(ConsoleFormatter())
    root.addHandler(console)

    directory = log_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file = logging.handlers.RotatingFileHandler(
            directory / LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
        )
        file.setFormatter(JsonFormatter())
        root.addHandler(file)
    except OSError as e:
        logging.getLogger(__name__).warning("Logging to %s failed, console only: %s", directory, e)

    # uvicorn's own messages (startup, errors) go the same way; its access log
    # is replaced by core/request_log.py, which says more
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # ...but a request that raised is already logged, with its traceback, by
    # core/request_log.py: uvicorn's second report of it is dropped
    errors = logging.getLogger("uvicorn.error")
    if not any(isinstance(f, _RequestFailure) for f in errors.filters):
        errors.addFilter(_RequestFailure())
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    # httpx logs every request it makes, e.g. to MediaMTX every 5 s
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
