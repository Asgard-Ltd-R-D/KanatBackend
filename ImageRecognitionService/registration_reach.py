"""How registration error grows with distance from the registered Target (#46).

Board space is one homography fitted to one Target and extrapolated to the
rest of the Board. A pre-existing Bullet Hole does not move on the Board, so
any wander of its Board-space position over a recording is registration error
at that distance — plus sheet curl and non-planarity, which are equally what
the pipeline has to live with.

No detector is involved, so detector flicker cannot pose as registration error.
Each reference mark is located in every RAW frame by normalised
cross-correlation against its own patch from the baseline frame, searched
around where that frame's homography predicts it. The raw position is then
carried into template space through the same frame's homography, exactly as
the runtime carries a detection (`board.track_view`, seeded frame to frame).
Error is the distance from the mark's baseline-frame position, in template px
— what baseline suppression compares against `MATCH_TPL_PX`.

Reference marks are every mark labelled on the before photograph
(`board.before.export.txt`) — on the Board before the recording, so stationary
through it — placed through the baseline frame as `evaluate.py` places truth.

Measurement only: changes nothing in the pipeline.
"""
import argparse
import os

import cv2
import numpy as np

import board
import evaluate
import manifest

PATCH = 10        # half-size of a mark's patch, frame px: a hole plus its rim
SEARCH = 12       # how far from the predicted position to look, frame px
MIN_NCC = 0.6     # below this the mark was not found in that frame; skipped


def locate(frame_gray, patch, predicted):
    """Sub-pixel raw position of `patch` near `predicted`, and its NCC, or
    (None, score) when the search window leaves the frame."""
    x, y = int(round(predicted[0])), int(round(predicted[1]))
    r = PATCH + SEARCH
    h, w = frame_gray.shape
    if x - r < 0 or y - r < 0 or x + r >= w or y + r >= h:
        return None, 0.0
    window = frame_gray[y - r:y + r + 1, x - r:x + r + 1]
    ncc = cv2.matchTemplate(window, patch, cv2.TM_CCOEFF_NORMED)
    _, score, _, (px, py) = cv2.minMaxLoc(ncc)

    def refine(a, b, c):  # parabola through the peak and its neighbours
        d = a - 2 * b + c
        return 0.0 if d == 0 else 0.5 * (a - c) / d
    dx = refine(ncc[py, px - 1], ncc[py, px], ncc[py, px + 1]) if 0 < px < ncc.shape[1] - 1 else 0.0
    dy = refine(ncc[py - 1, px], ncc[py, px], ncc[py + 1, px]) if 0 < py < ncc.shape[0] - 1 else 0.0
    return np.array([x - SEARCH + px + dx, y - SEARCH + py + dy]), score


def _registered(video, start, end, template_mask, view):
    """`(index, gray frame, view)` for every registered frame of the window,
    the baseline first at index 0 — the runtime's `track_view` chain, seeded
    frame to frame. Frames that fail to register are counted in `lost`."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    last, lost = view, [0]
    try:
        for index in range(int((end - start) * fps)):
            ok, frame = cap.read()
            if not ok:
                break
            try:
                current = view if index == 0 else board.track_view(frame, template_mask, last)[0]
            except cv2.error:
                current = None
            if current is None:
                lost[0] += 1
                continue
            last = current
            yield index, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), current
    finally:
        cap.release()
        _registered.lost = lost[0]


def _cut(gray, point):
    x, y = int(round(point[0])), int(round(point[1]))
    patch = gray[y - PATCH:y + PATCH + 1, x - PATCH:x + PATCH + 1]
    return patch if patch.shape == (2 * PATCH + 1,) * 2 else None  # cut off by the frame edge


def measure(frames, marks, from_index):
    """Per mark: its Board-space wander, in template px, from the frame it is
    referenced at (`from_index[i]`) to the end of the window.

    The mark's patch is cut at that frame where the homography puts it, so the
    reference is the Board point itself and its labelled placement error is
    not counted as wander."""
    patches = [None] * len(marks)
    errors, raw_moves, scores = ([[] for _ in marks] for _ in range(3))
    raw_ref = [None] * len(marks)
    for index, gray, current in frames:
        predicted = board._apply(current.H, marks)
        to_template = np.linalg.inv(current.H)
        for i, t in enumerate(marks):
            if index < from_index[i]:
                continue
            if patches[i] is None:
                if index == from_index[i]:
                    patches[i] = _cut(gray, predicted[i])
                    raw_ref[i] = predicted[i]
                continue
            found, score = locate(gray, patches[i], predicted[i])
            if found is None or score < MIN_NCC:
                continue
            here = board._apply(to_template, [found])[0]
            errors[i].append(float(np.linalg.norm(here - t)))
            scores[i].append(score)
            raw_moves[i].append(float(np.linalg.norm(found - raw_ref[i])))
    rows = []
    for i, t in enumerate(marks):
        if not errors[i]:
            rows.append(dict(mark=i + 1, found=False))  # at the frame edge, or never matched
            continue
        e = np.array(errors[i])
        rows.append(dict(mark=i + 1, found=True, frames=len(e),
                         distance=float(np.linalg.norm(t - board.RING_CENTRE_TPL)),
                         median=float(np.median(e)), p95=float(np.percentile(e, 95)),
                         max=float(e.max()), raw_max=float(np.max(raw_moves[i])),
                         ncc=float(np.median(scores[i]))))
    return rows


def _report(rows, span, label):
    print(f"[REACH] {label}: {_registered.lost} frame(s) failed to register and are not counted")
    print(f"[REACH] mark  distance(tpl px)  spans  frames  median  p95  max  "
          f"(template px; MATCH_TPL_PX {board.MATCH_TPL_PX:.0f})  raw-frame max  NCC")
    for r in sorted(rows, key=lambda r: r.get("distance", -1)):
        if not r["found"]:
            print(f"   #{r['mark']:<3} at the frame edge, or never matched above MIN_NCC")
            continue
        print(f"   #{r['mark']:<3} {r['distance']:8.0f}  {r['distance'] / span:5.2f}  "
              f"{r['frames']:5d}  {r['median']:6.1f} {r['p95']:5.1f} {r['max']:5.1f}"
              f"{'  OVER' if r['p95'] > board.MATCH_TPL_PX else '      '}   "
              f"{r['raw_max']:5.1f}  {r['ncc']:.2f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser("Registration error against distance from the Target")
    p.add_argument("video")
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--truth-labels", required=True,
                   help="a truth directory holding board.before.export.txt")
    p.add_argument("--appeared",
                   help="comma-separated seconds, one per NEW Bullet Hole in the "
                        "truth: measure those instead, each from when it appeared "
                        "- wander after appearance, not from the baseline. Take "
                        "them from a run's first detections; finding them from "
                        "pixels matched CamA's printed rings before the hole existed")
    a = p.parse_args()
    # No --final-run: this is an investigation, never the sealed measurement.
    manifest.gate(a.video, False, None, "registration_reach.py")

    _, template_mask = board.find_targets(cv2.imread(board.DEFAULT_TEMPLATE), min_area=1)
    span = board.contour_span(board.template_contour(template_mask))
    base, view = evaluate.baseline_view(a.video, a.start, template_mask)
    frames = lambda: _registered(a.video, a.start, a.end, template_mask, view)
    if a.appeared is None:
        marks, _ = evaluate.load_truth(
            None, os.path.join(a.truth_labels, evaluate.RAW_NAMES["before"]), base, view)
        _report(measure(frames(), marks, [0] * len(marks)), span, "from the baseline")
    else:
        marks, _ = evaluate.load_truth(None, a.truth_labels, base, view)
        times = [float(t) for t in a.appeared.split(",")]
        if len(times) != len(marks):
            raise SystemExit(f"--appeared has {len(times)} times for {len(marks)} new Bullet Holes")
        fps = cv2.VideoCapture(a.video).get(cv2.CAP_PROP_FPS)
        _report(measure(frames(), marks, [int(round((t - a.start) * fps)) for t in times]),
                span, "wander after appearance (NOT baseline marks)")
