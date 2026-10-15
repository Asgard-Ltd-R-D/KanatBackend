"""SOW 2.1.6: the Board moved, synthetically, against an unmoved control (#162, #165).

Runs #162's fixed case set through the scoring tool, each moved case beside its
unmoved control at the same stride, and prints one table, per case against its
control, per truth number. Every run's full printed output is kept beside the
table in `--out`, one file a run, named by case, move and stride:

    caffeinate -i python -m tools.board_move        # everything: hours at stride 1
    python -m tools.board_move --case act-2 --move 80x40 --stride 17   # minutes

A case passes when it has no false positive its control lacks and loses no true
positive its control found. Distance-based attribution cannot recognise a
Baseline Mark displaced as far as #92's, so the rule does not ask it to:
everything else in the table is reported, not judged.
"""
import argparse
import contextlib
import os
import sys
from datetime import datetime, timezone
from typing import NamedTuple

import numpy as np

from detection import new_bullet_holes as nbh
from tools import evaluate, manifest, position_error


class Case(NamedTuple):
    file: str
    start: float
    end: float
    at: float = None   # the move's time, seconds into the Recording


# #162's case set, fixed by the spec.
CASES = {
    "act-2": Case("CamB_20260915_102250.mkv", 20.0, 46.0, 25.0),       # before the next Hit
    "first-hit": Case("CamB_20260915_102450.mkv", 0.0, 47.76, 20.0),   # before the first Hit
    "mid-102250": Case("CamB_20260915_102250.mkv", 0.0, 46.0, 29.8),   # between truth #2 and #4
    "mid-141546": Case("CamA_20260914_141546.mkv", 13.0, 25.0, 15.5),  # between the 15.24 and 15.88 s Hits
}
# Frame px and degrees, held to the end of the run: #92's 80, 40 jump at 1/5,
# 1/2 and 1x, and a 2 degree turn with no shift.
MOVES = {"16x8": (16, 8, 0), "40x20": (40, 20, 0), "80x40": (80, 40, 0), "turn2": (0, 0, 2)}
# No move: `_102250` cut at 20 s into two Ranges, each its own run.
TWO_ACTS = "two-acts"
ACTS = (Case("CamB_20260915_102250.mkv", 0.0, 20.0), Case("CamB_20260915_102250.mkv", 20.0, 46.0))
STRIDES = (nbh.LIVE_STRIDE, 1)   # the minutes first, the hours after

NOT_TESTED = """\
Not tested: wind sway or any continuous motion; a physical Board move (it needs new
truth, and the camera, #85); a camera move; overlapping Hits (SOW 2.3.6). Each move
is a whole-frame warp applied as the Recording is read, standing in for a Board move
only inside the Board region Registration reads. Truth is photo-derived and internal."""


def compare(control, case, tolerance=evaluate.MATCH_TOLERANCE_TPL):
    """A moved case against its unmoved control, both `evaluate.score_recording`
    results at one stride.

    Per truth #, `(found #, seconds first seen)` in each run, or None; where
    both found it, how far it moved, `(dX, dY)` mm, and how much later it was
    first seen, s, case minus control. Truth is placed through the unmoved
    baseline frame in both, so the change in Position Error is the change in
    Position. `extra` is the case's false positives no control false positive
    lies within `tolerance` of, one to one; `lost` the truths the control found
    and the case did not. Either fails the case, whatever attribution says.
    """
    def found(score):
        return {j: (i, score["times"][i - 1], dx, dy) for i, j, _, dx, dy, _ in score["rows"]}

    before, after = found(control), found(case)
    truths = []
    for j in range(1, control["truths"] + 1):
        b, a = before.get(j), after.get(j)
        t = {"truth": j, "control": b[:2] if b else None, "case": a[:2] if a else None,
             "moved": None, "delay": None}
        if b and a:
            t["moved"], t["delay"] = (a[2] - b[2], a[3] - b[3]), a[1] - b[1]
        truths.append(t)

    def points(score):
        return np.float32([p for _, p, _, _ in score["false_positives"]]).reshape(-1, 2)

    pairs, _ = evaluate.match(points(control), points(case), tolerance)
    paired = {n for n, _, _ in pairs}
    extra = [fp for n, fp in enumerate(case["false_positives"]) if n not in paired]
    lost = [t["truth"] for t in truths if t["control"] and not t["case"]]
    return {"truths": truths, "extra": extra, "lost": lost, "passed": not extra and not lost}


def two_acts(act_1, act_2):
    """#162's checks on `_102250` cut at 20 s into two Ranges, as `(what,
    passed)`: act 1 finds the Hit fired before the cut; act 2 numbers from 1,
    finds the three fired after it and names the first as on the Board at its
    `--start`."""
    def truths(score):
        return {j for _, j, *_ in score["rows"]}

    numbers = sorted([i for i, *_ in act_2["rows"]] + [i for i, *_ in act_2["false_positives"]])
    return [("act 1 reports truth #3 among its new Bullet Holes", 3 in truths(act_1)),
            ("act 2 numbers from 1",
             bool(numbers) and numbers == list(range(1, len(numbers) + 1))),
            ("act 2 reports truth #2, #4 and #1", {1, 2, 4} <= truths(act_2)),
            ("act 2 names truth #3 in the baseline at --start, on a P entry",
             3 in {j for j, _ in act_2["in_baseline"]})]


def refuse_sealed(files, entries):
    """Refuse the run if the manifest makes any of `files` Sealed, or knows
    one not at all: by role and file name, before anything is opened, so a
    refusal never comes hours in (ADR-0005). The gate still rules on each
    Recording's content as it is scored."""
    roles = {e["file"]: manifest.role_for(entries, sha)
             for sha, e in entries.items() if e["file"] in files}
    for file in sorted(files):
        if file not in roles:
            raise manifest.NotInManifest(f"{file} is in no manifest entry")
        if roles[file] == manifest.SEALED:
            raise manifest.Sealed(f"{file} is Sealed (ADR-0005): its one measurement is "
                                  f"never spent on a synthetic case")


class _Tee:
    """Every write to each of `streams`: the terminal and a run's log."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for s in self.streams:
            s.write(text)

    def flush(self):
        for s in self.streams:
            s.flush()


def score(case, stride, label, out, move=None):
    """One scoring run, shown as it goes and kept whole in `<out>/<label>.log`."""
    print(f"\n===== {label} =====")
    with open(os.path.join(out, f"{label}.log"), "w") as log, \
            contextlib.redirect_stdout(_Tee(sys.stdout, log)):
        r = evaluate.score_recording(
            os.path.join(position_error.VIDEO_DIR, case.file), case.start, case.end,
            position_error.truth_dir({"file": case.file}), stride=stride, move=move)
    # Chosen by file name, gated by content: the window and truth are this file's.
    if r["entry"]["file"] != case.file:
        raise SystemExit(f"[REFUSED] {case.file} holds the bytes of {r['entry']['file']} "
                         f"in the manifest; its window and truth folder would be wrong")
    return r


def _seen(found):
    return "missed" if found is None else f"#{found[0]} t={found[1]:.2f}s"


def _false_positive(score, i, cause, distance):
    near = "none" if distance == float("inf") else f"{distance:.0f} px"
    return f"#{i} t={score['times'][i - 1]:.2f}s {cause}, nearest Baseline Mark {near}"


def print_table(moved, acts, out):
    """`moved` is `(case, move, stride, control, case score)` a run, `acts`
    `(stride, act 1, act 2)`."""
    print(f"\n\n[BOARD MOVE] SOW 2.1.6 (#162) at commit {manifest.git_commit()}: each case "
          f"against its unmoved control at the same stride; every run's output in {out}")
    print(f"   python -m tools.board_move {' '.join(sys.argv[1:])}".rstrip())
    print("   Pass: no false positive the control lacks, no true positive the control "
          "found lost. Moved (mm, X right, Y up) and delay (first seen, s) are case minus "
          "control, reported, not judged")
    print(f"   {'case':<11} {'move':<6} {'stride':>6}  verdict  Lost Looks  re-anchors  "
          f"(control -> case)")
    passed = 0
    for name, move, stride, control, case in moved:
        c = compare(control, case)
        passed += c["passed"]
        print(f"   {name:<11} {move:<6} {stride:>6}  {'PASS' if c['passed'] else 'FAIL':<7}  "
              f"{control['lost']:>4} -> {case['lost']:<4} {control['reanchors']:>4} -> "
              f"{case['reanchors']}")
        for t in c["truths"]:
            line = f"      truth #{t['truth']}  {_seen(t['control'])} -> {_seen(t['case'])}"
            if t["moved"] is not None:
                line += (f"  moved dX {t['moved'][0]:+.1f} dY {t['moved'][1]:+.1f} mm  "
                         f"delay {t['delay']:+.2f} s")
            print(line + ("  LOST" if t["truth"] in c["lost"] else ""))
        for i, _, cause, distance in c["extra"]:
            print(f"      extra false positive {_false_positive(case, i, cause, distance)}")
    if moved:
        print(f"\n[SUMMARY] {passed} of {len(moved)} moved case(s) pass")

    for stride, act_1, act_2 in acts:
        checks = two_acts(act_1, act_2)
        print(f"\n[TWO ACTS] {ACTS[0].file} cut at {ACTS[1].start:g} s into two Ranges, "
              f"no move, stride {stride}: {'PASS' if all(p for _, p in checks) else 'FAIL'}")
        for what, ok in checks:
            print(f"   {'PASS' if ok else 'FAIL'}  {what}")
        for n, act in enumerate((act_1, act_2), 1):
            hits = ", ".join(f"#{i} truth #{j}" for i, j, *_ in act["rows"]) or "none"
            fps = "; ".join(_false_positive(act, i, cause, distance)
                            for i, _, cause, distance in act["false_positives"]) or "none"
            print(f"   act {n}: {hits}. False positive(s): {fps}")
    print("\n" + NOT_TESTED)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        "SOW 2.1.6: the Board moved, synthetically, against unmoved controls (#162)")
    p.add_argument("--case", action="append", choices=[*CASES, TWO_ACTS],
                   help="run only this case; repeat for more. Every case by default")
    p.add_argument("--move", action="append", choices=MOVES,
                   help="run only this move; repeat for more. Every move by default")
    p.add_argument("--stride", action="append", type=int, choices=STRIDES,
                   help="run only at this stride; repeat for both. Both by default")
    p.add_argument("--out", default=os.path.join(
        manifest.BASE_DIR, "runs", "board_move",
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")),
        help="where every run's printed output is kept")
    a = p.parse_args()
    names = a.case or [*CASES, TWO_ACTS]

    files = {CASES[n].file for n in names if n in CASES}
    files |= {c.file for c in ACTS} if TWO_ACTS in names else set()
    try:
        refuse_sealed(files, manifest.load())
    except manifest.ManifestError as why:
        raise SystemExit(f"[REFUSED] {why}")
    os.makedirs(a.out, exist_ok=True)

    moved, acts = [], []
    for stride in a.stride or STRIDES:
        for name in names:
            if name == TWO_ACTS:
                acts.append((stride, *(score(c, stride, f"{TWO_ACTS}_act{n}_s{stride}", a.out)
                                       for n, c in enumerate(ACTS, 1))))
                continue
            case = CASES[name]
            control = score(case, stride, f"{name}_control_s{stride}", a.out)
            for move in a.move or MOVES:
                moved.append((name, move, stride, control, score(
                    case, stride, f"{name}_{move}_s{stride}", a.out,
                    evaluate.Move(case.at, *MOVES[move]))))
    print_table(moved, acts, a.out)
