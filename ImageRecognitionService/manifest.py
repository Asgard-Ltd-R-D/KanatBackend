"""Which recordings may be looked at, and a record of every look at the rest.

ADR-0005 splits the five customer recordings by Capture Setup: two go to
threshold work, the rest are **sealed**, and sealed means no pixels used for
anything — not frames, not labels, not unlabelled background crops. A model
trained on a sealed recording's gravel answers a weaker question than the one
the sealed set exists to ask, and the contamination cannot be un-seen in a
checkpoint.

That rule does not get broken deliberately. It gets broken months later, during
a long sweep, by someone who was not party to the decision — so it is enforced
here rather than written down:

- **Role is looked up by content hash**, never by filename. Renaming a file
  cannot move it across the split boundary.
- **A hash absent from the manifest is an error.** There is no default role; an
  unrecorded recording is one nobody has allocated yet.
- **An unrecognised role is an error too.** A guard that permits everything it
  does not recognise fails open, and `"Sealed"` is one shift key away.
- **Sealed footage is refused** unless `--final-run` is passed explicitly.
- **Every permitted final run appends** its date, model and commit to the log,
  so "we only looked once" is a record rather than a claim — which is what an
  acceptance conversation about SOW 2.3.6 will want.

The guard sits on the recording, because that is the only place provenance
exists. A frame already extracted to disk cannot be traced back to the footage
it came from — `sweep_profile.py` takes one and has nothing to check — so every
tool that *opens a recording* gates first, and that is what keeps sealed pixels
from reaching the ones that don't.

The recordings themselves are not version-controlled; they run to hundreds of
megabytes. The manifest hash is the link between a file on disk and its role.
"""
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BASE_DIR, "recordings.json")
RUN_LOG_PATH = os.path.join(BASE_DIR, "sealed_runs.log")

SEALED = "sealed"                  # held out; no pixels, see ADR-0005
THRESHOLD_WORK = "threshold-work"  # may falsify a constant, may not retune one
SPENT = "spent"                    # already analysed; the negative-mining source
ROLES = (SEALED, THRESHOLD_WORK, SPENT)


class ManifestError(Exception):
    """The manifest could not answer. Never assume a role when it cannot."""


class NotInManifest(ManifestError):
    """The file is not allocated to either side of the split."""


class Sealed(ManifestError):
    """The file is held out, and this run did not say it was the final one."""


def content_hash(path):
    """sha256 of the file's bytes. Recordings are large, so read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path=MANIFEST_PATH):
    """The manifest, keyed by sha256. Missing is not empty — it is an error.

    An empty dict would silently turn every lookup into "unknown", which reads
    as a tooling failure when it is really a missing source of truth.
    """
    if not os.path.isfile(path):
        raise ManifestError(f"no manifest at {path}; nothing has a role")
    with open(path) as f:
        return json.load(f)


def role_for(entries, sha):
    """The recording's role. Absent is an error, never a default."""
    if sha not in entries:
        raise NotInManifest(
            f"sha256 {sha} is in no manifest entry. Add it with its Capture "
            "Setup, role, frame rate and analysis window before using it — an "
            "unallocated recording has no role, and guessing one is how the "
            "held-out set gets spent.")
    role = entries[sha]["role"]
    if role not in ROLES:
        raise ManifestError(
            f"sha256 {sha} carries role {role!r}, which is not one of "
            f"{', '.join(ROLES)}. A typo must not read as permission.")
    return role


def check_allowed(entries, sha, final_run=False):
    """The manifest entry, if this run is allowed to look at the recording."""
    if role_for(entries, sha) == SEALED and not final_run:
        raise Sealed(
            f"sha256 {sha} is sealed held-out footage (ADR-0005): no pixels of "
            "it may be used for tuning, mining or comparison. Pass --final-run "
            "if this is the once-only measurement — it is appended to "
            f"{os.path.basename(RUN_LOG_PATH)} with the date, model and commit.")
    return entries[sha]


def git_commit():
    """Short HEAD, marked when the tree is dirty. A log entry naming a clean
    commit that never existed is worse than no entry."""
    def run(*args):
        return subprocess.run(args, cwd=BASE_DIR, text=True,
                              capture_output=True, check=True).stdout.strip()
    try:
        return run("git", "rev-parse", "--short", "HEAD") + (
            "-dirty" if run("git", "status", "--porcelain") else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def log_final_run(sha, model, commit, tool, log_path=RUN_LOG_PATH):
    """Append one line. Append-only: two final runs leave two entries."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log_path, "a") as f:
        f.write(f"{stamp}  {sha}  model={model}  commit={commit}  tool={tool}\n")


def authorise(video, final_run=False, model=None, tool=None,
              entries=None, log_path=RUN_LOG_PATH):
    """Gate one tool run on one recording, and log it if it spent sealed footage.

    The single seam every tool that opens a recording goes through — scoring,
    detection, negative mining. Raises a `ManifestError`; returns the entry,
    which also carries the frame rate and analysis window.

    The log is written before the first frame is read, so a run that crashes
    half way through still records as a look. It was: the pixels were opened.
    Recording a look that achieved nothing is the safe error here.
    """
    sha = content_hash(video)
    entry = check_allowed(load() if entries is None else entries, sha, final_run)
    if entry["role"] == SEALED:
        log_final_run(sha, model, git_commit(), tool, log_path)
    return entry


def add_flag(parser):
    """The `--final-run` flag, identical in every tool that opens a recording."""
    parser.add_argument("--final-run", action="store_true",
                        help="this is the once-only measurement on sealed "
                             "held-out footage (ADR-0005). Without it a sealed "
                             "recording is refused; with it, the run is "
                             "appended to sealed_runs.log with the date, model "
                             "and commit.")


def gate(video, final_run, model, tool):
    """`authorise` for a command line: refuse with a message, not a traceback."""
    try:
        return authorise(video, final_run, model, tool)
    except ManifestError as why:
        raise SystemExit(f"[REFUSED] {why}")
