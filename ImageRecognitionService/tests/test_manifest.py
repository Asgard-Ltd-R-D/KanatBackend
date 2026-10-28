"""Checks for the manifest's metadata lookup.

Pure functions over a hand-built manifest, plus two at the end that read the
shipped `recordings.json`. No video, no model, no torch. Nothing is refused any
more (ADR-0010): a listed recording gets its entry, an unlisted one None.
"""
import pytest

from tools import manifest
from tools.manifest import ManifestError, content_hash, lookup

ENTRY = {"file": "CamA_20260914_141546.mkv", "capture_setup": "cam-a-20260914",
         "fps": 30.0, "window": [13.0, 25.0]}


def test_the_same_bytes_under_a_different_name_find_the_same_entry(tmp_path):
    """Looked up by content: a rename keeps the Capture Setup, fps and window."""
    original, renamed = tmp_path / "original.mkv", tmp_path / "renamed.mkv"
    original.write_bytes(b"\x00 some frames \xff")
    renamed.write_bytes(b"\x00 some frames \xff")
    entries = {content_hash(str(original)): ENTRY}
    assert lookup(str(renamed), entries) == ENTRY


def test_a_file_the_manifest_does_not_list_finds_nothing(tmp_path):
    """An unlisted recording runs, with no Capture Setup; it is not refused."""
    video = tmp_path / "new.mkv"
    video.write_bytes(b"other frames")
    assert lookup(str(video), {"a" * 64: ENTRY}) is None


def test_a_missing_manifest_is_not_an_empty_one(tmp_path):
    """Empty, every listed recording would run as unlisted, with no Capture
    Setup and so no print scale, and nothing would say why."""
    with pytest.raises(ManifestError):
        manifest.load(str(tmp_path / "nothing.json"))


DOCUMENTED_FIELDS = ("file", "capture_setup", "fps", "window", "window_basis")


def test_every_shipped_entry_carries_the_documented_fields():
    """An entry missing one should fail here and say so, not `KeyError`
    somewhere downstream."""
    for sha, entry in manifest.load().items():
        missing = [f for f in DOCUMENTED_FIELDS if f not in entry]
        assert not missing, f"{entry.get('file', sha)} is missing {missing}"


def test_no_shipped_entry_carries_a_role():
    """Roles went with sealing (ADR-0010)."""
    assert not [e["file"] for e in manifest.load().values() if "role" in e]


def test_each_result_is_labelled_by_its_capture_setup():
    """ADR-0010: unseen only from a setup nothing was chosen on; unlisted
    footage has no setup to judge by."""
    assert manifest.footage(ENTRY) == "REGRESSION"
    assert manifest.footage({**ENTRY, "capture_setup": "cama-20260914-wide"}) == "UNSEEN"
    assert manifest.footage(None) == "UNLABELLED"


def test_a_pooled_result_is_unseen_only_if_all_of_it_is():
    assert manifest.pooled_footage(["UNSEEN", "REGRESSION"]) == "REGRESSION"
    assert manifest.pooled_footage(["UNSEEN", "UNLABELLED"]) == "UNLABELLED"
    assert manifest.pooled_footage(["UNSEEN", "UNSEEN"]) == "UNSEEN"
    assert manifest.pooled_footage([]) == "UNLABELLED"


def test_every_unseen_setup_is_a_shipped_one():
    """A misspelt name would label nothing unseen, and nothing would say so."""
    shipped = {e["capture_setup"] for e in manifest.load().values()}
    assert manifest.UNSEEN_SETUPS <= shipped
