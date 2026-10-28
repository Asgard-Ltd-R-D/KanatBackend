"""What is on record about each recording: its Capture Setup, frame rate and window.

`config/recordings.json` is metadata, keyed by content hash, never by filename,
so a renamed file keeps its Capture Setup (which picks its print scale), frame
rate and analysis window. A file it does not list is not refused: it runs with
no Capture Setup, and so no print scale unless one is given (ADR-0010, which
supersedes ADR-0005's sealing).

The recordings themselves are not version-controlled; they run to hundreds of
megabytes. The manifest hash is the link between a file on disk and its entry.
"""
import hashlib
import json
import os
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ImageRecognitionService/
MANIFEST_PATH = os.path.join(BASE_DIR, "config", "recordings.json")


class ManifestError(Exception):
    """The manifest could not be read."""


def content_hash(path):
    """sha256 of the file's bytes. Recordings are large, so read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path=MANIFEST_PATH):
    """The manifest, keyed by sha256. Missing is not empty — it is an error.

    An empty dict would silently turn every listed recording into an unlisted
    one, running with no Capture Setup, when the source of truth is missing.
    """
    if not os.path.isfile(path):
        raise ManifestError(f"no manifest at {path}")
    with open(path) as f:
        return json.load(f)


def lookup(video, entries=None):
    """`video`'s entry, found by the hash of its bytes, or None: a file the
    manifest does not list runs, with no Capture Setup."""
    return (load() if entries is None else entries).get(content_hash(video))


# ADR-0010's label, kept by hand, as no tool can know what was in view: the
# Capture Setups nothing at HEAD was chosen with in view. Take one out as soon
# as anything is chosen with any of its recordings in view.
UNSEEN_SETUPS = {"cama-20260914-wide", "cama-20260914-wide-tight"}

FOOTAGE_MEANING = {
    "REGRESSION": "shows a change broke nothing here, not that it generalises",
    "UNSEEN": "evidence of generalisation; tuning on its Capture Setup makes it "
              "regression, so take that setup out of UNSEEN_SETUPS first",
    "UNLABELLED": "unlisted, so no Capture Setup to judge by; not evidence of "
                  "generalisation until it is listed",
}


def footage(entry):
    """ADR-0010's label for a recording's results, from its manifest entry:
    UNSEEN, REGRESSION, or UNLABELLED for an unlisted one."""
    if entry is None:
        return "UNLABELLED"
    return "UNSEEN" if entry["capture_setup"] in UNSEEN_SETUPS else "REGRESSION"


def pooled_footage(labels):
    """A pooled result is unseen only if all of it is."""
    labels = set(labels)
    if "REGRESSION" in labels:
        return "REGRESSION"
    return "UNSEEN" if labels == {"UNSEEN"} else "UNLABELLED"


def footage_line(label, what):
    return f"[FOOTAGE] {what}: {label} (ADR-0010), {FOOTAGE_MEANING[label]}"


def git_commit():
    """Short HEAD, marked when the tree is dirty. A report naming a clean
    commit that never existed is worse than none."""
    def run(*args):
        return subprocess.run(args, cwd=BASE_DIR, text=True,
                              capture_output=True, check=True).stdout.strip()
    try:
        return run("git", "rev-parse", "--short", "HEAD") + (
            "-dirty" if run("git", "status", "--porcelain") else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
