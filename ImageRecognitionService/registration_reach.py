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


def measure(video, start, end, truth_dir, template_path=board.DEFAULT_TEMPLATE):
    """Per reference mark: distance from the ring centre, and its Board-space
    wander over the window, both in template px."""
    _, template_mask = board.find_targets(cv2.imread(template_path), min_area=1)
    base, view = evaluate.baseline_view(video, start, template_mask)
    before = os.path.join(truth_dir, evaluate.RAW_NAMES["before"])
    pre, _ = evaluate.load_truth(None, before, base, view)

    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    raw0 = board._apply(view.H, pre)
    patches = [gray[int(round(y)) - PATCH:int(round(y)) + PATCH + 1,
                    int(round(x)) - PATCH:int(round(x)) + PATCH + 1] for x, y in raw0]
    # A patch cut off by the frame edge cannot be searched for.
    tpl0 = [t if patch.shape == (2 * PATCH + 1,) * 2 else None
            for t, patch in zip(pre, patches)]

    errors = [[] for _ in pre]
    raw_moves = [[] for _ in pre]
    scores = [[] for _ in pre]
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps) + 1)
    last, frames, lost = view, int((end - start) * fps), 0
    for _ in range(frames - 1):
        ok, frame = cap.read()
        if not ok:
            break
        try:
            current, _ = board.track_view(frame, template_mask, last)
        except cv2.error:
            current = None
        if current is None:
            lost += 1
            continue
        last = current
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        predicted = board._apply(current.H, [t if t is not None else [0, 0] for t in tpl0])
        for i, (t, patch) in enumerate(zip(tpl0, patches)):
            if t is None:
                continue
            found, score = locate(g, patch, predicted[i])
            if found is None or score < MIN_NCC:
                continue
            here = board._apply(np.linalg.inv(current.H), [found])[0]
            errors[i].append(float(np.linalg.norm(here - t)))
            scores[i].append(score)
            raw_moves[i].append(float(np.linalg.norm(found - board._apply(view.H, [t])[0])))
    cap.release()

    centre = board.RING_CENTRE_TPL
    span = board.contour_span(board.template_contour(template_mask))
    rows = []
    for i, t in enumerate(tpl0):
        if t is None or not errors[i]:
            rows.append(dict(mark=i + 1, found=False))  # at the frame edge, or never matched
            continue
        e = np.array(errors[i])
        rows.append(dict(mark=i + 1, found=True, frames=len(e),
                         distance=float(np.linalg.norm(t - centre)), span=span,
                         median=float(np.median(e)), p95=float(np.percentile(e, 95)),
                         max=float(e.max()),
                         raw_max=float(np.max(raw_moves[i])),
                         ncc=float(np.median(scores[i]))))
    return rows, lost


if __name__ == "__main__":
    p = argparse.ArgumentParser("Registration error against distance from the Target")
    p.add_argument("video")
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--truth-labels", required=True, help="a truth directory holding board.before.export.txt")
    a = p.parse_args()
    # No --final-run: this is an investigation, never the sealed measurement.
    manifest.gate(a.video, False, None, "registration_reach.py")

    rows, lost = measure(a.video, a.start, a.end, a.truth_labels)
    print(f"[REACH] {lost} frame(s) failed to register and are not counted")
    print(f"[REACH] mark  distance(tpl px)  spans  frames  median  p95  max  "
          f"(template px; MATCH_TPL_PX {board.MATCH_TPL_PX:.0f})  raw-frame max  NCC")
    for r in sorted(rows, key=lambda r: r.get("distance", -1)):
        if not r["found"]:
            print(f"   #{r['mark']:<3} at the frame edge, or never matched above MIN_NCC")
            continue
        print(f"   #{r['mark']:<3} {r['distance']:8.0f}  {r['distance'] / r['span']:5.2f}  "
              f"{r['frames']:5d}  {r['median']:6.1f} {r['p95']:5.1f} {r['max']:5.1f}"
              f"{'  OVER' if r['p95'] > board.MATCH_TPL_PX else '      '}   {r['raw_max']:5.1f}  {r['ncc']:.2f}")
