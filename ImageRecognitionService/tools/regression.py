"""#268's regression bench: every truth recording scored per Bullet Hole, and
two results compared by #268's regression rule (#272).

`run` scores every recording `config/recordings.json` lists with a truth
folder, over its manifest window, at one stride and device, and at each
canvas shift of the control (`board.shifted`, #46), and writes one JSON
result. `compare` reads two and rules on them:

    caffeinate -i python -m tools.regression run --out main.json   # hours: 4 shifts x 6 at stride 1
    python -m tools.regression run --out quick.json --shifts 0 --only CamB_20260915_102250
    python -m tools.regression compare main.json branch.json

The rule, per Bullet Hole of the new result against the reference, at 0 px:
no truth Bullet Hole the reference finds is lost; no false positive is
added; each matched Bullet Hole's Position Error moves at most `MOVE_MM` and stays under
`position_error.LIMIT_MM` on both axes. A failure the reference itself shows
under its shifted runs (the hole lost, the false positive there, the error
moved or over the limit) flips under the control: it is grid noise,
reported, and does not fail. A position failure flips only where a shifted
run found the hole and shows it: a shifted miss has no position to show.
Recordings run at another window, stride or device are not ruled on. Only the reference's shifted runs are read, but
`run` makes them by default all the same: today's result is the next
change's reference.

Hit-to-report is from each truth Bullet Hole's arrival frame, `board.arrival.txt`
beside its truth (#273): one line per truth line, the frame of the Recording
it was first visible in, `-` where none is labelled. Blank where none is,
never estimated from the detector. Its report time is the Look that judged
it, before the Change Evidence check.

Every result is regression (ADR-0010): this is the footage changes are
judged on, so passing here is not evidence of generalisation.
"""
import argparse
import csv
import json
import os
import platform
import sys
import tempfile

import numpy as np

from detection import new_bullet_holes as nbh
from tools import evaluate, manifest, position_error

SHIFTS = (0, 8, 16, 32)   # Board px, #46's control
MOVE_MM = 1.0             # #268: a matched hole's Position Error may move this much
ARRIVAL_NAME = "board.arrival.txt"
TIMED = {"look": "look_ms", "inference": "inference_ms", "registration": "registration_ms"}
# What fails the rule; anything else compare finds is reported only.
FAILS = ("lost", "added", "moved", "over limit", "not run", "not comparable")


def arrival_frames(truth_dir):
    """Per truth line, the frame its Bullet Hole arrived in, or None: none
    labelled, or no `board.arrival.txt` at all."""
    path = os.path.join(truth_dir, ARRIVAL_NAME)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        first = [(l.split() or ["-"])[0] for l in f.read().splitlines()]
    return [None if f == "-" else int(f) for f in first]


def timing_summary(path):
    """n, P50, P95, P99 and max per `TIMED` stage of a `--timing` CSV."""
    with open(path) as f:
        rows = list(csv.DictReader(l for l in f if not l.startswith("#")))
    out = {}
    for name, column in TIMED.items():
        ms = [float(r[column]) for r in rows if r[column]]
        out[name] = ({"n": len(ms), **dict(zip(("p50", "p95", "p99"),
                                                map(float, np.percentile(ms, (50, 95, 99))))),
                      "max": max(ms)} if ms else {"n": 0})
    return out


def score(entry, stride, device, shift, timing=None, truth_filter=None):
    """One run of `entry` at canvas shift `shift`, per Bullet Hole.

    `truth_filter(entry, truth)` takes the truth in template px and says which
    to score; the rest, and the detections they claim, are out of scope:
    neither found, missed nor false (#268's Target Sheets)."""
    folder = position_error.truth_dir(entry)
    start, end = entry["window"]
    r = evaluate.score_recording(os.path.join(position_error.VIDEO_DIR, entry["file"]),
                                 start, end, folder, stride=stride, device=device,
                                 timing=timing, canvas_shift=shift)
    if r["entry"] != entry:
        raise SystemExit(f"[REFUSED] {entry['file']} does not hold the bytes the manifest "
                         f"lists under that name")
    keep = (np.ones(len(r["truth"]), bool) if truth_filter is None
            else np.asarray(truth_filter(entry, r["truth"]), bool))
    arrivals = arrival_frames(folder)
    owner = {j: i for i, j, _ in r["pairs"]}
    errors = {j - 1: (dx, dy, radial) for _, j, _, dx, dy, radial in r["rows"]}
    truth = []
    for j in range(len(r["truth"])):
        i = owner.get(j)
        t = {"truth": j + 1, "outcome": "out of scope" if not keep[j] else
             "FN" if i is None else "TP", "found": None if i is None else i + 1,
             "dx": None, "dy": None, "radial": None, "first_seen": None,
             "reported": None, "hit_to_report": None,
             "arrival": arrivals[j] if j < len(arrivals) else None}
        if i is not None:
            t.update(zip(("dx", "dy", "radial"), map(float, errors[j])))
            t.update(first_seen=r["times"][i], reported=r["reported"][i])
            if t["arrival"] is not None:
                t["hit_to_report"] = t["reported"] - t["arrival"] / r["fps"]
        truth.append(t)
    claimed = set(owner.values())
    false_positives = [{"found": i + 1, "x": float(x), "y": float(y),
                        "first_seen": r["times"][i], "reported": r["reported"][i]}
                       for i, (x, y) in enumerate(r["found"]) if i not in claimed]
    # Before the change filter: what persisted, less what truth claims.
    pairs, _ = evaluate.match(r["truth"], r["persisted"], evaluate.MATCH_TOLERANCE_TPL)
    return {"truth": truth, "false_positives": false_positives,
            "fp_before_change_filter": len(r["persisted"]) - len(pairs),
            "unit": r["unit"], "device": r["device"]}


def run(entries, stride, device, shifts, out, truth_filter=None):
    """Score `entries` at every shift and write the result to `out`, after
    each recording, so hours of runs survive a crash in the last."""
    result = {"footage": "REGRESSION", "commit": manifest.git_commit(),
              "host": platform.node(), "platform": platform.platform(),
              "device": device, "stride": stride, "shifts": list(shifts),
              "recordings": {}}
    for entry in entries:
        name = os.path.splitext(entry["file"])[0]
        recording = {"window": entry["window"], "footage": manifest.footage(entry),
                     "shifts": {}}
        for d in shifts:
            print(f"\n===== {name}, canvas shift {d} px =====")
            with tempfile.TemporaryDirectory() as tmp:
                timing = os.path.join(tmp, "timing.csv") if d == 0 else None
                recording["shifts"][str(d)] = score(entry, stride, device, d, timing,
                                                    truth_filter)
                if timing:
                    recording["timing"] = timing_summary(timing)
        result["recordings"][name] = recording
        with open(out, "w") as f:
            json.dump(result, f, indent=1)
    print_result(result)
    return result


def _truth(shift_result, j):
    return next(t for t in shift_result["truth"] if t["truth"] == j)


def _over(t):
    return max(abs(t["dx"]), abs(t["dy"])) >= position_error.LIMIT_MM


def _moved(a, b):
    return float(np.hypot(b["dx"] - a["dx"], b["dy"] - a["dy"]))


def _points(fps):
    return np.array([(f["x"], f["y"]) for f in fps], np.float64).reshape(-1, 2)


def compare(ref, new):
    """The new result against the reference, by #268's rule: `(findings,
    passed)`. A finding is a dict: `recording`, `kind`, `hole`, `detail`,
    `noise` (it flips under the reference's shifted runs) and `fails`."""
    findings = []

    def note(recording, kind, hole, detail, noise=False):
        findings.append({"recording": recording, "kind": kind, "hole": hole,
                         "detail": detail, "noise": noise,
                         "fails": kind in FAILS and not noise})

    for name, r in ref["recordings"].items():
        n = new["recordings"].get(name)
        if n is None or "0" not in n["shifts"]:
            note(name, "not run", "-", "in the reference, not in the new result at 0 px")
            continue
        r0, n0 = r["shifts"]["0"], n["shifts"]["0"]
        control = [s for k, s in r["shifts"].items() if k != "0"]
        unit = n0["unit"]
        # The rule's bounds are mm, on one truth: anything else is not ruled on.
        if (r0["unit"], unit) != ("mm", "mm") or len(r0["truth"]) != len(n0["truth"]):
            note(name, "not comparable", "-",
                 f"{len(r0['truth'])} truth in {r0['unit']} against "
                 f"{len(n0['truth'])} in {unit}")
            continue
        # Another window, stride or device is another experiment, not a change.
        was_run, now_run = (f"stride {x['stride']}, {y['window'][0]:g}-{y['window'][1]:g} s, "
                            f"device {y['shifts']['0']['device']}"
                            for x, y in ((ref, r), (new, n)))
        if was_run != now_run:
            note(name, "not comparable", "-", f"{now_run} against {was_run}")
            continue
        for t in n0["truth"]:
            j, was = t["truth"], _truth(r0, t["truth"])
            hole = f"truth #{j}"
            if "out of scope" in (t["outcome"], was["outcome"]):
                if t["outcome"] != was["outcome"]:
                    note(name, "scope", hole, f"{was['outcome']} -> {t['outcome']}")
                continue
            if was["outcome"] == "FN":
                if t["outcome"] == "TP":
                    note(name, "gained", hole, "missed by the reference, found")
                continue
            under = [_truth(s, j) for s in control]
            if t["outcome"] != "TP":
                note(name, "lost", hole, "found by the reference, missed",
                     any(u["outcome"] != "TP" for u in under))
                continue
            moved = _moved(was, t)
            if moved > MOVE_MM:
                note(name, "moved", hole,
                     f"dX {was['dx']:+.1f} -> {t['dx']:+.1f}, dY {was['dy']:+.1f} -> "
                     f"{t['dy']:+.1f}: moved {moved:.2f} {unit}, over {MOVE_MM:g}",
                     any(u["outcome"] == "TP" and _moved(was, u) > MOVE_MM for u in under))
            if _over(t):
                note(name, "over limit", hole,
                     f"dX {t['dx']:+.1f}, dY {t['dy']:+.1f} {unit}: at or over "
                     f"{position_error.LIMIT_MM:g}",
                     any(u["outcome"] == "TP" and _over(u) for u in under))
        tol = evaluate.MATCH_TOLERANCE_TPL
        before, after = _points(r0["false_positives"]), _points(n0["false_positives"])
        pairs, removed = evaluate.match(before, after, tol)
        paired = {i for i, _, _ in pairs}
        for i, (x, y) in enumerate(after):
            if i in paired:
                continue
            noise = any(len(c) and np.linalg.norm(c - (x, y), axis=1).min() <= tol
                        for c in map(_points, (s["false_positives"] for s in control)))
            note(name, "added", f"FP found #{n0['false_positives'][i]['found']}",
                 f"at template ({x:.0f}, {y:.0f}), no reference FP within {tol:.0f} px",
                 noise)
        for j in removed:
            note(name, "removed", f"reference FP found #{r0['false_positives'][j]['found']}",
                 "no longer reported")
    return findings, not any(f["fails"] for f in findings)


def _load(path):
    with open(path) as f:
        return json.load(f)


def _footage(result):
    return manifest.footage_line(
        manifest.pooled_footage(r["footage"] for r in result["recordings"].values()),
        "regression bench")


def _cell(v, fmt):
    return "" if v is None else format(v, fmt)


def print_result(result):
    print(f"\n\n[REGRESSION] bench at {result['commit']}, stride {result['stride']}, "
          f"device {result['device'] or 'default'}, shifts {result['shifts']} px, on "
          f"{result['host']} ({result['platform']})")
    print(_footage(result))
    for name, r in result["recordings"].items():
        print(f"\n[REGRESSION] {name} {r['window'][0]:g}-{r['window'][1]:g} s")
        for d, s in r["shifts"].items():
            count = lambda o: sum(t["outcome"] == o for t in s["truth"])
            print(f"   {d:>2} px  TP {count('TP')}  FP {len(s['false_positives'])}  "
                  f"FN {count('FN')}  out of scope {count('out of scope')}  "
                  f"FP before the change filter {s['fp_before_change_filter']}  "
                  f"(device {s['device']})")
        print(f"   {'truth':>6} {'outcome':<12} {'dX':>6} {'dY':>6} {'radial':>6} "
              f"{'seen s':>7} {'reported s':>10} {'arrival':>7} {'hit-to-report s':>15}")
        for t in r["shifts"]["0"]["truth"]:
            print(f"   {'#' + str(t['truth']):>6} {t['outcome']:<12} "
                  f"{_cell(t['dx'], '+6.1f'):>6} {_cell(t['dy'], '+6.1f'):>6} "
                  f"{_cell(t['radial'], '6.1f'):>6} {_cell(t['first_seen'], '7.2f'):>7} "
                  f"{_cell(t['reported'], '10.2f'):>10} {_cell(t['arrival'], 'd'):>7} "
                  f"{_cell(t['hit_to_report'], '15.2f'):>15}")
        for stage, p in r.get("timing", {}).items():
            line = (f"n {p['n']}  P50 {p['p50']:.1f}  P95 {p['p95']:.1f}  "
                    f"P99 {p['p99']:.1f}  max {p['max']:.1f} ms" if p["n"] else "n 0")
            print(f"   {stage:<13} {line}")


def print_compare(ref, new, findings, passed):
    print(f"[REGRESSION] {new['commit']} against the reference {ref['commit']}, "
          f"stride {new['stride']} against {ref['stride']}, on {new['host']}")
    print(_footage(new))
    if len(ref["shifts"]) < 2:
        print("[WARN] the reference has no shifted runs: nothing can be marked noise")
    for f in findings:
        flag = "NOISE" if f["noise"] else "FAIL" if f["fails"] else "info"
        print(f"   {flag:<5} {f['recording']:<22} {f['kind']:<10} {f['hole']:<16} {f['detail']}")
    for name, r in ref["recordings"].items():
        n = new["recordings"].get(name)
        if n is None or "0" not in n["shifts"]:
            continue
        look = lambda x: x.get("timing", {}).get("look", {})
        p50 = lambda p: f"{p['p50']:.0f}" if p.get("n") else "-"
        print(f"   {name:<22} FP before the change filter "
              f"{r['shifts']['0']['fp_before_change_filter']} -> "
              f"{n['shifts']['0']['fp_before_change_filter']}, Look Time P50 "
              f"{p50(look(r))} -> {p50(look(n))} ms")
    print(f"[REGRESSION] {'PASS' if passed else 'FAIL'}: "
          f"{sum(f['fails'] for f in findings)} failing, "
          f"{sum(f['noise'] for f in findings)} noise")


if __name__ == "__main__":
    p = argparse.ArgumentParser("#268's regression bench")
    sub = p.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("run", help="score every truth recording, write a JSON result")
    r.add_argument("--out", required=True)
    nbh.add_stride_flag(r)
    r.add_argument("--device", help="the detector's device: cpu, mps, or a CUDA index")
    r.add_argument("--shifts", default=",".join(map(str, SHIFTS)),
                   type=lambda s: [int(v) for v in s.split(",")],
                   help="canvas shifts, Board px; 0 must be among them")
    r.add_argument("--only", nargs="+", metavar="NAME",
                   help="these recordings, by file name without extension")
    c = sub.add_parser("compare", help="rule on a new result against a reference")
    c.add_argument("reference")
    c.add_argument("new")
    a = p.parse_args()

    if a.mode == "run":
        if 0 not in a.shifts:
            p.error("--shifts must include 0: it is what compare rules on")
        entries = position_error.select(manifest.load())
        if a.only:
            entries = [e for e in entries if os.path.splitext(e["file"])[0] in a.only]
            if len(entries) != len(a.only):
                p.error(f"--only names a recording with no truth folder: {a.only}")
        run(entries, a.stride or 1, a.device, a.shifts, a.out)
    else:
        ref, new = map(_load, (a.reference, a.new))
        findings, passed = compare(ref, new)
        print_compare(ref, new, findings, passed)
        sys.exit(0 if passed else 1)
