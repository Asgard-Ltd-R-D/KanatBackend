"""The Detection Service's logs: one JSON object a line in detection.log, and
a readable line on the console, as the WebApp backend's
(WebApp/backend/app/core/logs.py), beside its backend.log and the app's
frontend.log, which the app's Logs tab reads (WebApp/frontend/electron/logreader.ts).

detection.log is in --log-dir (/var/log/kanat in its container on the
range PC), else KANAT_LOG_DIR, else the repo's WebApp/logs when it exists;
with none, the service logs to the console only. The command line
(new_bullet_holes.py) logs to the console only: its runs are not the range's.

What happens while the service runs is logged, at the level it deserves; the
command line's report stays printed. A log call adds its own fields with
`extra`, which become JSON fields the Logs tab shows:

    log.warning("Bullet Hole not posted", extra={"session_id": session_id})

A field may not take the name of a LogRecord attribute (`name`, `message`,
`args`, `module`...). A line logged without a session_id carries the active
Run's (`current_session`), whichever thread logged it.
"""
import json
import logging
import logging.handlers
import os
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

LOG_FILE = "detection.log"
# As the backend's and the app's: rotated daily, keeping ~a week of past days
BACKUP_DAYS = 7

# The active Session, set by service.py. One Session's Runs are active at a
# time -- the backend keeps one active Session, and the service refuses a Run
# for another while any remain -- and those Runs, one per camera, are every Run
# there is, so every line logged meanwhile is that Session's, each Run's Stream
# reader thread and poster included
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


class SharedFileHandler(logging.Handler):
    """Appends each line to `path`, which several processes share: the supervisor,
    the service and, in process mode, every Run's process. It holds no file open,
    so a day's rotation, by whichever of them writes first after midnight (UTC),
    is a rename that always works, Windows included, and none goes on writing to
    the renamed file. A `TimedRotatingFileHandler` per process loses lines
    instead: a rename the others block fails on every line. Past days are kept
    as `detection.log.YYYY-MM-DD`, BACKUP_DAYS of them."""
    def __init__(self, path, backups=BACKUP_DAYS):
        super().__init__()
        self.path, self.backups = Path(path), backups

    def emit(self, record):
        try:
            line = self.format(record) + "\n"
            self._rotate_if_a_new_day()
            with open(self.path, "a", encoding="utf-8") as file:
                file.write(line)
        except Exception:
            self.handleError(record)

    def _rotate_if_a_new_day(self):
        try:
            last_written = datetime.fromtimestamp(self.path.stat().st_mtime, timezone.utc).date()
        except OSError:   # no file yet
            return
        if last_written == datetime.now(timezone.utc).date():
            return
        past = self.path.with_name(f"{self.path.name}.{last_written.isoformat()}")
        try:
            # A link, not a rename: it fails if `past` exists, atomically, where a rename would
            # replace a day another process has just archived with today's new file
            os.link(self.path, past)
        except OSError:   # another process rotated it first (or the filesystem has no links): leave it
            return
        for _ in range(5):
            try:
                os.unlink(self.path)   # the lines other processes append meanwhile are in `past` too
                break
            except OSError:   # held open this instant (Windows): tried again
                time.sleep(0.05)
        for old in sorted(self.path.parent.glob(f"{self.path.name}.*"))[:-self.backups]:
            try:
                old.unlink()
            except OSError:
                pass


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
        file = SharedFileHandler(directory / LOG_FILE)
    except OSError as e:
        logging.getLogger(__name__).warning("Logging to %s failed, console only: %s", directory, e)
        return None
    file.setFormatter(JsonFormatter())
    root.addHandler(file)
    return directory / LOG_FILE
