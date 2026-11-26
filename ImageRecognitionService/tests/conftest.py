"""The Target finder is a model (ADR-0013) that CI does not install: every
test finds Targets by the template's hue instead, as `evaluate` does on the
truth photographs, which the synthetic frames are drawn in. A test marked
`target_model` runs the real one."""
import pytest

from detection import board
from tools.evaluate import _hue_targets


@pytest.fixture(autouse=True)
def hue_target_finder(request, monkeypatch):
    if "target_model" not in request.keywords:
        monkeypatch.setattr(board, "find_targets", _hue_targets)
        monkeypatch.setattr(board, "target_model", lambda: None)
