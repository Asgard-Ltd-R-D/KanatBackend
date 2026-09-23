"""Checks for split membership, the sealed guard and the run log.

Pure functions over a hand-built manifest, plus three at the end that read the
shipped `recordings.json` because the allocation itself is what they check. No
video, no model, no torch — the rule being protected here (ADR-0005: sealed
means zero pixels) is one that gets broken months later during a long sweep, by
someone who was not party to the decision, so the guard has to hold without
anything heavy being available.
"""
import pytest

import manifest
from manifest import (ManifestError, NotInManifest, SEALED, SPENT, THRESHOLD_WORK, Sealed,
                      authorise, check_allowed, content_hash, log_final_run, role_for)

MANIFEST = {
    "a" * 64: {"file": "CamA_20260914_141546.mkv", "capture_setup": "cam-a-20260914",
               "role": THRESHOLD_WORK, "fps": 30.0, "window": [13.0, 25.0]},
    "b" * 64: {"file": "CamC_20260920_090000.mkv", "capture_setup": "cam-c-20260920",
               "role": SEALED, "fps": 30.0, "window": [0.0, 40.0]},
}


def test_the_same_bytes_under_a_different_name_resolve_to_the_same_role(tmp_path):
    """A rename must not move a recording across the split boundary."""
    original, renamed = tmp_path / "sealed.mkv", tmp_path / "definitely_fine.mkv"
    original.write_bytes(b"\x00 some frames \xff")
    renamed.write_bytes(b"\x00 some frames \xff")

    entries = {content_hash(str(original)): {"role": SEALED}}
    assert role_for(entries, content_hash(str(renamed))) == SEALED


def test_different_bytes_are_a_different_recording(tmp_path):
    a, b = tmp_path / "a.mkv", tmp_path / "b.mkv"
    a.write_bytes(b"one")
    b.write_bytes(b"two")
    assert content_hash(str(a)) != content_hash(str(b))


def test_an_unknown_hash_is_an_error_not_a_default_role():
    """Silence here is how a sealed recording gets used by accident."""
    with pytest.raises(NotInManifest):
        role_for(MANIFEST, "c" * 64)


def test_scoring_a_sealed_recording_without_the_flag_is_refused():
    with pytest.raises(Sealed) as why:
        check_allowed(MANIFEST, "b" * 64)
    assert "sealed" in str(why.value).lower()
    assert "--final-run" in str(why.value)  # says how, or it just gets worked around


def test_scoring_a_sealed_recording_with_the_flag_is_permitted():
    entry = check_allowed(MANIFEST, "b" * 64, final_run=True)
    assert entry["capture_setup"] == "cam-c-20260920"


def test_threshold_work_footage_needs_no_flag():
    assert check_allowed(MANIFEST, "a" * 64)["role"] == THRESHOLD_WORK


def test_a_role_nobody_recognises_is_an_error_not_permission():
    """The guard tests for sealed and permits the rest, so a typo in the role
    would read as permission. `"Sealed"` is one shift key away."""
    for typo in ("Sealed", "seled", "held-out"):
        with pytest.raises(ManifestError):
            check_allowed({"a" * 64: {"role": typo}}, "a" * 64)


def test_a_missing_manifest_is_not_an_empty_one(tmp_path):
    """An empty dict would turn every lookup into "unknown", which reads as a
    tooling failure when it is really a missing source of truth."""
    with pytest.raises(ManifestError):
        manifest.load(str(tmp_path / "nothing.json"))


def test_an_unknown_hash_is_refused_by_the_guard_too():
    with pytest.raises(NotInManifest):
        check_allowed(MANIFEST, "c" * 64, final_run=True)


def test_two_final_runs_leave_two_entries(tmp_path):
    """Append-only: "we only looked once" is a record or it is nothing."""
    log = tmp_path / "sealed_runs.log"
    log_final_run("b" * 64, "yolo26n", "abc1234", "evaluate.py", str(log))
    first = log.read_text()
    log_final_run("b" * 64, "yolo26m", "def5678", "evaluate.py", str(log))

    lines = log.read_text().strip().splitlines()
    assert len(lines) == 2
    assert log.read_text().startswith(first)  # nothing was overwritten
    assert "yolo26n" in lines[0] and "yolo26m" in lines[1]


def test_a_log_entry_carries_the_date_the_model_and_the_commit(tmp_path):
    log = tmp_path / "sealed_runs.log"
    log_final_run("b" * 64, "yolo26m", "def5678", "evaluate.py", str(log))

    line = log.read_text().strip()
    assert line.startswith("20")          # ISO-8601, and still right in 2027
    assert "yolo26m" in line and "def5678" in line and "b" * 64 in line


def test_a_refused_run_is_not_logged_as_a_look(tmp_path):
    """The log records pixels seen. A run that was refused saw none."""
    video = tmp_path / "sealed.mkv"
    video.write_bytes(b"frames")
    entries = {content_hash(str(video)): {"role": SEALED}}
    log = tmp_path / "sealed_runs.log"

    with pytest.raises(Sealed):
        authorise(str(video), model="yolo26n", tool="evaluate.py",
                  entries=entries, log_path=str(log))
    assert not log.exists()


def test_only_sealed_footage_is_logged(tmp_path):
    """Threshold-work footage is spent already; logging every run buries the
    entries that have to be defensible."""
    video = tmp_path / "spent.mkv"
    video.write_bytes(b"frames")
    entries = {content_hash(str(video)): {"role": THRESHOLD_WORK}}
    log = tmp_path / "sealed_runs.log"

    authorise(str(video), model="yolo26n", tool="evaluate.py",
              entries=entries, log_path=str(log))
    assert not log.exists()


def test_a_permitted_final_run_is_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "git_commit", lambda: "abc1234")
    video = tmp_path / "sealed.mkv"
    video.write_bytes(b"frames")
    sha = content_hash(str(video))
    log = tmp_path / "sealed_runs.log"

    entry = authorise(str(video), final_run=True, model="yolo26n", tool="evaluate.py",
                      entries={sha: {"role": SEALED}}, log_path=str(log))
    assert entry["role"] == SEALED
    assert sha in log.read_text() and "commit=abc1234" in log.read_text()


# The allocation. The invariant is a pure function over entries, like everything
# above it; only the last two tests read `recordings.json`, because the property
# ADR-0005 turns on is one of the real allocation and nothing else checks it.
# See capture_setups.md for the grouping evidence behind that allocation.

DOCUMENTED_FIELDS = ("file", "capture_setup", "role", "fps", "window", "window_basis")


def _setups_with_two_roles(entries):
    """Capture Setups with recordings on both sides of the sealed boundary.

    The unit of the split is the Capture Setup, not the file (ADR-0005). Holding
    out one file of a Capture Setup the constants were fitted to measures
    re-detection of an arrangement already fitted, and reports it as
    generalisation. Two files from one afternoon exercise no threshold
    independently, so the whole setup goes one side of the boundary or the other.
    `spent` and `threshold-work` are both the unsealed side, so a setup may mix
    them and each file keeps its own provenance.
    """
    roles = {}
    for entry in entries.values():
        roles.setdefault(entry["capture_setup"], set()).add(entry["role"])
    return {setup: sorted(r) for setup, r in roles.items()
            if SEALED in r and len(r) > 1}


def test_a_setup_whose_files_all_carry_one_role_is_not_reported():
    assert _setups_with_two_roles(MANIFEST) == {}


def test_a_setup_split_across_the_boundary_is_reported():
    """The failure this exists to catch: two files, one afternoon, two roles."""
    split = dict(MANIFEST, **{
        "d" * 64: {"file": "CamC_20260920_090100.mkv",
                   "capture_setup": "cam-c-20260920",  # same setup as "b" * 64
                   "role": THRESHOLD_WORK, "fps": 30.0, "window": [0.0, 40.0]}})

    assert _setups_with_two_roles(split) == {
        "cam-c-20260920": [SEALED, THRESHOLD_WORK]}


def test_spent_and_threshold_work_in_one_setup_is_not_a_split():
    """Both are the unsealed side; a fitted clip keeps `spent` beside its
    unopened siblings without either being mislabelled to pass."""
    entries = {"a" * 64: {"capture_setup": "camb", "role": SPENT},
               "b" * 64: {"capture_setup": "camb", "role": THRESHOLD_WORK}}
    assert _setups_with_two_roles(entries) == {}


def test_a_setup_is_grouped_by_name_not_by_filename():
    """Two files one minute apart are one setup; the filenames differ and the
    `capture_setup` does not. Grouping on the filename would miss it."""
    entries = {"a" * 64: {"capture_setup": "camb", "role": SEALED},
               "b" * 64: {"capture_setup": "camb", "role": SEALED}}
    assert _setups_with_two_roles(entries) == {}


def test_every_shipped_entry_carries_the_documented_fields():
    """`NotInManifest` tells an operator to add a Capture Setup, role, frame
    rate and analysis window. An entry missing one should fail here and say so,
    not `KeyError` somewhere downstream."""
    for sha, entry in manifest.load().items():
        missing = [f for f in DOCUMENTED_FIELDS if f not in entry]
        assert not missing, f"{entry.get('file', sha)} is missing {missing}"
        assert role_for(manifest.load(), sha) in manifest.ROLES


def test_the_shipped_allocation_splits_no_capture_setup():
    split = _setups_with_two_roles(manifest.load())
    assert not split, f"one Capture Setup, two roles: {split}"


def test_the_shipped_allocation_seals_something():
    """Sealing nothing passes every other check here and leaves the question
    the held-out set exists to answer unanswerable."""
    sealed = {e["capture_setup"] for e in manifest.load().values()
              if e["role"] == SEALED}
    assert sealed, "no Capture Setup is sealed; nothing can measure generalisation"
