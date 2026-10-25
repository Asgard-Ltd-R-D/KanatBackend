"""The Detection Service's logs (detection/logs.py): detection.log as JSON
lines in the WebApp's log shape, each carrying the active Run's Session."""
import json
import logging
import uuid

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
