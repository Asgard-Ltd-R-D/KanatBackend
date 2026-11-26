"""The Target finder's outdoor and colour check (#413): the colour gate as on
`main` (3f80479) against the segmentation model, on the held-out footage,
every frame also greyscale, hue-rotated 30/60/90/180 degrees, warm and cool
cast, and at 0.3 saturation.

`detection` is whichever checkout runs it, so the gate side runs from a
`main` worktree and the model side from this one, into the same OUT:

    python -m tools.target_finder_check gate  runs/413/finders   # on main
    python -m tools.target_finder_check model runs/413/finders
    python -m tools.target_finder_check report runs/413/finders

Truth is #403's reviewed truth, `runs/target_finders/results.json` and its
`review/rejected.txt`, scored on the accepted frames only. The camera-native
clips (`FirstNoOverlay`, `SecondNoOverlay`) are read from `LAB_DIR`.
Recall and false Targets are at IoU 0.5, as #413 asks; 0.85 is reported too.
Latency is only meaningful on an otherwise idle machine."""
import json
import os
import sys
import time
from pathlib import Path
import cv2, numpy as np

BASE = Path(__file__).resolve().parents[1]
RUNS, VIDEOS = BASE / "runs", BASE / "data" / "videos"
LAB = Path(os.environ.get("LAB_DIR", Path.home() / "Downloads" / "KANANT_STAFF_FOLDER"))
STEP_S, TRUTH_EVERY, IOU_PASS, IOU_MATCH, EDGE = 2.0, 5, 0.85, 0.5, 30

def video_path(rec):
    return LAB / f"{rec}.mp4" if rec.endswith("NoOverlay") else VIDEOS / f"{rec}.mkv"

def sampled(path):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS); step, i = round(STEP_S * fps), 0
    while True:
        ok, frame = cap.read()
        if not ok: break
        if i % step == 0: yield round(i / fps, 2), frame
        i += 1

def mask(p, shape):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(np.asarray(p)).reshape(-1, 1, 2).astype(np.int32)], 1)
    return m.astype(bool)

def iou(a, b): return (a & b).sum() / max(int((a | b).sum()), 1)

def off_edge(polys, shape):
    h, w = shape; keep = []
    for p in polys:
        ys, xs = np.nonzero(mask(p, shape))
        if xs.size and EDGE <= xs.mean() <= w - EDGE and EDGE <= ys.mean() <= h - EDGE: keep.append(p)
    return keep

def score(pred, truth, shape):
    pred, truth = off_edge(pred, shape), off_edge(truth, shape)
    P, T = [mask(p, shape) for p in pred], [mask(t, shape) for t in truth]
    pairs = sorted(((iou(p, t), i, j) for i, p in enumerate(P) for j, t in enumerate(T)), reverse=True)
    up, ut, good = set(), set(), []
    for v, i, j in pairs:
        if v >= IOU_MATCH and i not in up and j not in ut: up.add(i); ut.add(j); good.append(v)
    return {"hit5": len(good), "hit85": sum(v >= IOU_PASS for v in good), "truth": len(truth),
            "fp": len(pred) - len(good), "ious": good}

def truth_of(row):
    shape = tuple(row["shape"]); truth = list(row["disk_first"]["polys"])
    for g in row["gate_adaptive"]["polys"]:
        if all(iou(mask(g, shape), mask(t, shape)) < IOU_MATCH for t in truth): truth.append(g)
    return truth

def versions(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    def hue(d):
        h = hsv.copy(); h[..., 0] = (h[..., 0].astype(int) + d // 2) % 180
        return cv2.cvtColor(h, cv2.COLOR_HSV2BGR)
    def cast(b, r):
        return np.clip(frame * np.float32([b, 1, r]), 0, 255).astype(np.uint8)
    s = hsv.copy(); s[..., 1] = (s[..., 1] * 0.3).astype(np.uint8)
    return {"original": frame, "grey": cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR),
            "hue30": hue(30), "hue60": hue(60), "hue90": hue(90), "hue180": hue(180),
            "warm": cast(0.8, 1.2), "cool": cast(1.2, 0.8), "sat0.3": cv2.cvtColor(s, cv2.COLOR_HSV2BGR)}

def run(mode, out):
    from detection import board
    template_mask = (board.template_mask(cv2.imread(board.DEFAULT_TEMPLATE)) if hasattr(board, "template_mask")
                     else board.find_targets(cv2.imread(board.DEFAULT_TEMPLATE), min_area=1)[1])
    results = json.loads((RUNS / "target_finders/results.json").read_text())
    rejected = {l.split("#")[0].strip() for l in (RUNS / "target_finders/review/rejected.txt").read_text().splitlines()} - {""}
    rows_out = []
    for set_name, recs in results.items():
        for rec, rows in recs.items():
            truth_rows = {r["t"]: r for k, r in enumerate(rows) if k % TRUTH_EVERY == 0}
            for t, frame in sampled(video_path(rec)):
                row = truth_rows.get(t)
                for name, img in versions(frame).items():
                    rec_out = {"set": set_name, "rec": rec, "t": t, "version": name, "shape": frame.shape[:2]}
                    if mode == "model":
                        started = time.perf_counter()
                        contours, _ = board.find_targets(img)
                        rec_out["ms"] = (time.perf_counter() - started) * 1000
                        rec_out["polys"] = [c.reshape(-1, 2).tolist() for c in contours]
                    if row is not None:   # the baseline view on truth frames: what main's gate is scored by
                        contours, frame_mask, fit = board.board_targets(img, template_mask)
                        rec_out["built"] = fit is not None
                        rec_out["interior"] = fit is not None and board.interior_fit(img, fit[0])[0] is not None
                        view, _ = board.build_view(img, template_mask) if fit is not None else (None, None)
                        if mode == "gate":
                            rec_out["polys"] = [] if view is None else [
                                board.apply(view.H @ np.linalg.inv(view.tpl_to_board), p.reshape(-1, 2)).tolist()
                                for p in view.targets]
                        rec_out["truth"] = truth_of(row)
                        rec_out["judged"] = f"{rec}@{t}" not in rejected
                    if "polys" in rec_out: rows_out.append(rec_out)
            print(rec, flush=True)
    (Path(out) / f"{mode}.json").write_text(json.dumps(rows_out))

def report(out):
    lines = ["# Target finder: outdoor and colour check (#413)", ""]
    for mode in ("gate", "model"):
        rows = json.loads((Path(out) / f"{mode}.json").read_text())
        for set_name in ("indoor", "outdoor", "h264"):
            lines += [f"## {mode}, {set_name}", "",
                      "| version | recall @IoU 0.5 | recall @IoU 0.85 | FP | mean IoU | baseline built | interior_fit | frames with count != original | P50 / P95 ms |",
                      "|---|---|---|---|---|---|---|---|---|"]
            orig = {(r["rec"], r["t"]): len(off_edge(r["polys"], tuple(r["shape"])))
                    for r in rows if r["set"] == set_name and r["version"] == "original"}
            for v in ("original", "grey", "hue30", "hue60", "hue90", "hue180", "warm", "cool", "sat0.3"):
                sel = [r for r in rows if r["set"] == set_name and r["version"] == v]
                judged = [r for r in sel if r.get("judged")]
                s = [score(r["polys"], r["truth"], tuple(r["shape"])) for r in judged]
                built = [r for r in sel if "built" in r]
                n = sum(x["truth"] for x in s); ious = [i for x in s for i in x["ious"]]
                diff = sum(len(off_edge(r["polys"], tuple(r["shape"]))) != orig[(r["rec"], r["t"])] for r in sel)
                ms = [r["ms"] for r in sel if "ms" in r]
                lat = f"{np.percentile(ms, 50):.0f} / {np.percentile(ms, 95):.0f}" if ms else "-"
                lines.append(f"| {v} | {sum(x['hit5'] for x in s)}/{n} | {sum(x['hit85'] for x in s)}/{n} | "
                             f"{sum(x['fp'] for x in s)} | {np.mean(ious) if ious else float('nan'):.3f} | "
                             f"{sum(r['built'] for r in built)}/{len(built)} | {sum(r['interior'] for r in built)}/{len(built)} | "
                             f"{diff}/{len(sel)} | {lat} |")
            lines.append("")
    (Path(out) / "report.md").write_text("\n".join(lines))
    print("\n".join(lines))

if __name__ == "__main__":
    mode, out = sys.argv[1], sys.argv[2]
    report(out) if mode == "report" else run(mode, out)
