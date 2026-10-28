"""SOW 2.3.2 stage 1: Position Error over every recording with truth.

Scores each manifest recording that has a truth folder, with the window and
Capture Setup its manifest entry gives, then reports the matched
pairs' Position Error over all of them (#123, #126). The headline is at
`LIVE_STRIDE` (ADR-0007), stride 1 beside it:

    python -m tools.position_error --stride 17
    python -m tools.position_error --stride 1

The recordings are read from data/videos under their manifest file names, and
each truth folder's photograph from wherever its board.source.txt names it.

Internal, and says so under every summary: the truth is photo-derived and
carried into each recording's own frame of reference, so what it shares with
the run cancels out of the figure.
"""
import argparse
import os

import numpy as np

from detection import new_bullet_holes as nbh
from tools import evaluate, manifest

TRUTH_DIR = os.path.join(manifest.BASE_DIR, "data", "truth")
VIDEO_DIR = os.path.join(manifest.BASE_DIR, "data", "videos")

# SOW 2.3.2's bound, per axis. Reported against, never ruled on: the
# acceptance statistic is the customer's to confirm.
LIMIT_MM = 5.0

NOT_COVERED = """\
INTERNAL MEASUREMENT — not an independent validation of SOW 2.3.2. Truth: labels
on photographs of the Board, carried into this footage's own frame of
reference. Not covered (errors here cancel out or never enter): the Target
centre; the print scale (mm per template px); the baseline frame's mapping to
the artwork; compression (these recordings are MPEG-4 Part 2, live is H.264,
and a re-encode moved positions by up to 3 mm); field conditions (angle,
wind). Included: the truth's own placement error (the placement check). Errors
above the matching tolerance (40 template px, ≈ 7.1 mm radial) appear only as
an unmatched detection plus a missed Bullet Hole. No compliance verdict: the
acceptance statistic is the customer's to confirm."""

# ADR-0010's label, stated by hand: no tool can know what was in view when the
# commit was chosen. Change it when a recording of an unseen Capture Setup gains
# truth.
FOOTAGE = """\
   Footage: REGRESSION, every recording (ADR-0010). Each one's Capture Setup was
   in view when this commit's model and constants were chosen, so this shows a
   change broke nothing here, not that it generalises."""


def truth_dir(entry, root=TRUTH_DIR):
    """`CamB_20260915_102250.mkv` -> `<root>/camb-20260915-102250`."""
    stem = os.path.splitext(entry["file"])[0]
    return os.path.join(root, stem.lower().replace("_", "-"))


def select(entries, root=TRUTH_DIR):
    """The manifest entries that have a truth folder, by file name: every one
    is scored (ADR-0010)."""
    return sorted((e for e in entries.values() if os.path.isdir(truth_dir(e, root))),
                  key=lambda e: e["file"])


def summarise(errors, on_target):
    """The stage-1 statistics over matched pairs' Position Errors.

    `errors` is `evaluate.position_errors` rows, `(dX, dY, radial)` mm, from
    any number of recordings; `on_target` says per row whether the run put that
    Bullet Hole on a Target. `under` counts the rows with |dX| and |dY| both
    strictly under 5 mm: exactly 5 is not under. P95 interpolates between the
    order statistics (numpy's default), so at this N it sits near the maximum.
    """
    e = np.asarray(errors, np.float64).reshape(-1, 3)
    out = {"n": len(e), "on_target": int(np.sum(on_target))}
    if not len(e):
        return out
    absolute = np.abs(e[:, :2])

    def mean_p95_max(v):
        return {"mean": v.mean(), "p95": np.percentile(v, 95), "max": v.max()}

    return {**out, "bias": e[:, :2].mean(axis=0),
            "dx": mean_p95_max(absolute[:, 0]),
            "dy": mean_p95_max(absolute[:, 1]),
            "radial": mean_p95_max(e[:, 2]),
            "under": int(np.all(absolute < LIMIT_MM, axis=1).sum())}


def print_summary(label, s):
    print(f"\n[SUMMARY] {label}: N {s['n']} matched, {s['on_target']} on a Target")
    if not s["n"]:
        return
    print(f"   bias      mean dX {s['bias'][0]:+.1f}  mean dY {s['bias'][1]:+.1f} mm")
    for name, key in (("|dX|", "dx"), ("|dY|", "dy"), ("radial", "radial")):
        v = s[key]
        print(f"   {name:<9} mean {v['mean']:.1f}  P95 {v['p95']:.1f}  "
              f"max {v['max']:.1f} mm")
    print(f"   |dX| and |dY| both under {LIMIT_MM:g} mm: {s['under']} of "
          f"{s['n']} ({s['under'] / s['n']:.0%})")


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        "SOW 2.3.2 stage-1 Position Error over every truth recording")
    nbh.add_stride_flag(p)
    a = p.parse_args()

    entries = manifest.load()
    chosen = select(entries)
    # A truth folder no manifest entry maps to would drop out of N unsaid.
    orphans = sorted(set(next(os.walk(TRUTH_DIR))[1])
                     - {os.path.basename(truth_dir(e)) for e in entries.values()})
    scored = []
    for entry in chosen:
        print(f"\n===== {entry['file']} =====")
        start, end = entry["window"]
        r = evaluate.score_recording(os.path.join(VIDEO_DIR, entry["file"]),
                                     start, end, truth_dir(entry),
                                     stride=a.stride)
        # Chosen by file name, looked up by content: they must be one
        # recording, or the window and truth belong to another one than the scale.
        if r["entry"] != entry:
            raise SystemExit(f"[REFUSED] {entry['file']} does not hold the bytes "
                             f"the manifest lists under that name; its window "
                             f"and truth folder would be wrong")
        scored.append((os.path.splitext(entry["file"])[0], r))

    stride = a.stride or 1
    print(f"\n\n[POSITION ERROR REPORT] SOW 2.3.2 stage 1, stride {stride}"
          + (" (LIVE_STRIDE, the headline)" if stride == nbh.LIVE_STRIDE else "")
          + f", {len(scored)} recording(s)")
    print(FOOTAGE)
    if orphans:
        print(f"[WARN] truth folder(s) no manifest entry maps to, not scored: "
              f"{', '.join(orphans)}")
    print("   mm along the Target's printed axes (X right, Y up), system minus "
          "truth, at the end-of-Range position")
    print(f"   {'recording':<22} {'found':>5} {'truth':>5}  {'where':<9} "
          f"{'dX':>6} {'dY':>6} {'radial':>6}")
    for name, r in scored:
        for i, j, where, dx, dy, radial in r["rows"]:
            print(f"   {name:<22} {'#' + str(i):>5} {'#' + str(j):>5}  {where:<9} "
                  f"{dx:+6.1f} {dy:+6.1f} {radial:6.1f}")

    print(f"\n[UNMATCHED] in no statistic: "
          f"{sum(r['unmatched'] for _, r in scored)} detection(s) matched to no "
          f"truth, {sum(r['missed'] for _, r in scored)} truth Bullet Hole(s) "
          f"not found")
    for name, r in scored:
        print(f"   {name:<22} {r['unmatched']} unmatched, {r['missed']} missed")

    print("\n[PLACEMENT] per recording: the truth's own placement error, "
          "inside every figure here")
    for name, r in scored:
        for line in r["placement"].splitlines():
            print(f"   {name:<22} {line}")

    cameras = [name.split("_")[0] for name, _ in scored]
    for label in ["pooled"] + sorted(set(cameras)):
        rows = [row for camera, (_, r) in zip(cameras, scored)
                if label in ("pooled", camera) for row in r["rows"]]
        print_summary(label, summarise([row[3:] for row in rows],
                                       [row[2] != "MISS" for row in rows]))
        print("\n" + NOT_COVERED)
