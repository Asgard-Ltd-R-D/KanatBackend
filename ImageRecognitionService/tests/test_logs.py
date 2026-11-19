"""The Detection Service's logs (detection/logs.py): detection.log as JSON
lines in the WebApp's log shape, each carrying the active Run's Session."""
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import pytest

from detection import logs

SESSION = uuid.UUID("2012f47e-7b77-412a-8754-f4dac17f5d36")


@pytest.fixture
def logged(tmp_path, monkeypatch):
    """Logging configured to write in tmp_path, put back as it was after;
    returns detection.log's lines read so far."""
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    monkeypatch.setattr(logs, "current_session", None)
    path = logs.configure(tmp_path)
    yield lambda: [json.loads(line) for line in path.read_text().splitlines()]
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)
    for handler in before:
        root.addHandler(handler)
    root.setLevel(level)


def test_the_folder_is_the_given_one_then_kanat_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KANAT_LOG_DIR", str(tmp_path / "env"))
    assert logs.log_dir(tmp_path / "given") == tmp_path / "given"
    assert logs.log_dir() == tmp_path / "env"


def test_a_line_is_one_json_object_in_the_webapps_shape(logged):
    logging.getLogger("detection.live").warning("Stream dropped: no frame since %s", "09:00:05",
                                                extra={"frames_lost": 3})

    (line,) = logged()
    assert line["time"].endswith("+00:00")
    assert {k: v for k, v in line.items() if k != "time"} == {
        "level": "warning", "service": "detection", "logger": "detection.live",
        "message": "Stream dropped: no frame since 09:00:05", "frames_lost": 3}


def test_a_line_logged_while_a_run_is_active_carries_its_session(logged, monkeypatch):
    monkeypatch.setattr(logs, "current_session", SESSION)
    logging.getLogger("detection.board").info("1 Target(s)")
    # A call's own session_id is kept: the poster names its own
    logging.getLogger("detection.post").info("posted", extra={"session_id": "another"})

    assert [line["session_id"] for line in logged()] == [str(SESSION), "another"]


def test_an_exception_is_logged_with_its_traceback(logged):
    try:
        raise ValueError("no baseline")
    except ValueError:
        logging.getLogger("detection.service").exception("Run failed")

    (line,) = logged()
    assert line["level"] == "error"
    assert line["exception"].startswith("Traceback (most recent call last)")
    assert line["exception"].endswith("ValueError: no baseline")


def test_the_command_line_logs_to_the_console_only(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        assert logs.configure(tmp_path, to_file=False) is None
        assert not any(isinstance(h, logging.FileHandler) for h in root.handlers)
        assert not (tmp_path / logs.LOG_FILE).exists()
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in before:
            root.addHandler(handler)


def _record(message):
    return logging.LogRecord("t", logging.INFO, "", 0, message, None, None)


def test_several_writers_share_one_file_and_lose_no_line(tmp_path):
    """The supervisor, the service and each Run's process all write detection.log."""
    path = tmp_path / "detection.log"
    handlers = [logs.SharedFileHandler(path) for _ in range(4)]
    for n in range(20):
        for number, handler in enumerate(handlers):
            handler.handle(_record(f"writer {number} line {n}"))
    assert len(path.read_text(encoding="utf-8").splitlines()) == 80


def test_the_first_line_of_a_new_day_rotates_the_file_and_no_writer_loses_a_line(tmp_path):
    path = tmp_path / "detection.log"
    first, second = logs.SharedFileHandler(path), logs.SharedFileHandler(path)
    first.handle(_record("yesterday"))
    two_days = time.time() - 36 * 3600
    os.utime(path, (two_days, two_days))
    day = datetime.fromtimestamp(two_days, timezone.utc).date().isoformat()
    first.handle(_record("today, first writer"))   # this one rotates
    second.handle(_record("today, second writer"))   # and the other carries on in the new file
    assert "yesterday" in (tmp_path / f"detection.log.{day}").read_text(encoding="utf-8")
    today = path.read_text(encoding="utf-8")
    assert "first writer" in today and "second writer" in today and "yesterday" not in today


def test_only_the_last_days_are_kept(tmp_path):
    path = tmp_path / "detection.log"
    for n in range(10):
        (tmp_path / f"detection.log.2026-01-{n + 10:02d}").write_text("old")
    handler = logs.SharedFileHandler(path, backups=3)
    handler.handle(_record("past"))
    long_ago = time.time() - 36 * 3600
    os.utime(path, (long_ago, long_ago))
    handler.handle(_record("now"))
    kept = sorted(p.name for p in tmp_path.glob("detection.log.*"))
    assert len(kept) == 3 and kept[-1] == f"detection.log.{datetime.fromtimestamp(long_ago, timezone.utc).date()}"


def test_a_day_another_process_just_archived_is_never_replaced(tmp_path, monkeypatch):
    """Two writers both see yesterday's file after midnight: the second must not
    replace the archive the first made, with a view of the folder that is stale."""
    path = tmp_path / "detection.log"
    long_ago = time.time() - 36 * 3600
    day = datetime.fromtimestamp(long_ago, timezone.utc).date().isoformat()
    archive = tmp_path / f"detection.log.{day}"
    archive.write_text("yesterday's lines\n")   # the first writer has archived the day
    path.write_text("today's first line\n")      # and started today's file,
    os.utime(path, (long_ago, long_ago))           # which the second writer still sees as yesterday's
    monkeypatch.setattr(logs.Path, "exists", lambda self: False)   # a stale view of the folder
    logs.SharedFileHandler(path).handle(_record("second writer"))
    assert archive.read_text() == "yesterday's lines\n"
    assert "today's first line" in path.read_text() and "second writer" in path.read_text()
