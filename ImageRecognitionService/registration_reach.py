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

`--registration` swaps the runtime chain for an experimental one (#50), so
alternatives are scored by the same yardstick before any runtime change:

- `runtime`: `board.track_view`, an 8-parameter homography fitted to the one
  Target's green mask, seeded frame to frame. What the pipeline does.
- `affine` (#50 A): the baseline homography's perspective is held; each frame
  is registered to the BASELINE frame's green mask by an affine only.
- `texture` (#50 B): as `affine`, but ECC runs on the greyscale frame over a
  Board region, so marks, sheet edges and seams far from the Target constrain
  the fit. `--motion homography` lets it refit the perspective too.

Every mode also splits each mark's error into drift (what holds for a second)
and jitter (the rest) (#50 C): they point at re-anchoring and at smoothing.

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
ECC_SCALE = 0.5   # anchored modes run ECC at this fraction of the frame; ~4x faster
DRIFT_FRAMES = 25  # drift is the rolling mean over this many frames (1 s at 25 fps)
REGION_SPANS = 1.5  # texture mode: the Board within this many Target spans of the ring


def locate(frame_gray, patch, predicted):
    """Sub-pixel raw position of `patch` near `predicted`, and its NCC, or
    (None, score) when the search window leaves the frame or the peak is on
    its edge."""
    x, y = int(round(predicted[0])), int(round(predicted[1]))
    r = PATCH + SEARCH
    h, w = frame_gray.shape
    if x - r < 0 or y - r < 0 or x + r >= w or y + r >= h:
        return None, 0.0
    window = frame_gray[y - r:y + r + 1, x - r:x + r + 1]
    ncc = cv2.matchTemplate(window, patch, cv2.TM_CCOEFF_NORMED)
    _, score, _, (px, py) = cv2.minMaxLoc(ncc)
    if px in (0, ncc.shape[1] - 1) or py in (0, ncc.shape[0] - 1):
        # The best score on the window's edge is not a maximum: a neighbour, or
        # the slope of a mark past SEARCH. CamA #2 flipped to one at (+8, -12).
        return None, score

    def refine(a, b, c):  # parabola through the peak and its neighbours
        d = a - 2 * b + c
        return 0.0 if d == 0 else 0.5 * (a - c) / d
    dx = refine(ncc[py, px - 1], ncc[py, px], ncc[py, px + 1])
    dy = refine(ncc[py - 1, px], ncc[py, px], ncc[py + 1, px])
    return np.array([x - SEARCH + px + dx, y - SEARCH + py + dy]), score


def _frames(video, start, end):
    """`(index, frame)` over the window, the frame at `start` first."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    try:
        for index in range(int((end - start) * fps)):
            ok, frame = cap.read()
            if not ok:
                break
            yield index, frame
    finally:
        cap.release()


def _registered(video, start, end, template_mask, view):
    """`(index, gray frame, view)` for every frame of the window, the baseline
    first at index 0 — the runtime's `track_view` chain, seeded frame to
    frame. A frame that fails to register comes with view None."""
    last = view
    for index, frame in _frames(video, start, end):
        try:
            current = view if index == 0 else board.track_view(frame, template_mask, last)[0]
        except cv2.error:
            current = None
        if current is not None:
            last = current
        yield index, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), current


def ecc_warp(ref, cur, motion, init, mask=None):
    """3x3 warp taking `ref` frame coordinates onto `cur`'s, by ECC at
    `ECC_SCALE`, seeded with `init` (same convention), over `mask`'s nonzero
    pixels of `ref` (all when None). Raises `cv2.error` when ECC does not
    converge."""
    D = np.diag([ECC_SCALE, ECC_SCALE, 1.0]).astype(np.float32)
    small = lambda im, how=cv2.INTER_AREA: cv2.resize(im, None, fx=ECC_SCALE, fy=ECC_SCALE,
                                                      interpolation=how)
    rows = 3 if motion == cv2.MOTION_HOMOGRAPHY else 2
    seed = (D @ init @ np.linalg.inv(D))[:rows].astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    _, w = cv2.findTransformECC(small(ref), small(cur), seed, motion, criteria,
                                None if mask is None else small(mask, cv2.INTER_NEAREST), 5)
    w = w if rows == 3 else np.vstack([w, [0, 0, 1]])
    return (np.linalg.inv(D) @ w @ D).astype(np.float32)


def _anchored(video, start, end, view, image, motion, mask=None):
    """As `_registered`, but every frame is registered to the BASELINE frame
    and the baseline homography is kept: H = W @ H0, W of `motion` found by
    ECC between `image(baseline)` and `image(frame)` over `mask`. The previous
    W seeds the next, but the reference never moves, so error cannot
    accumulate.

    ponytail: one fixed reference frame; once new Bullet Holes or lighting
    change the Board enough, ECC against it degrades. Re-anchor to a recent
    frame if the lost count ever climbs."""
    W, ref = np.eye(3, dtype=np.float32), None
    for index, frame in _frames(video, start, end):
        if ref is None:
            ref = image(frame)
        else:
            try:
                W = ecc_warp(ref, image(frame), motion, W, mask)
            except cv2.error:
                yield index, None, None
                continue
        yield index, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), board.BoardView(
            W @ view.H, view.tpl_to_board, view.canvas_size, [])


def _green(frame):
    """The blurred green mask the runtime registers on."""
    return board._blurred(board.find_targets(frame)[1])


def _gray(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255


def texture_region(view, frame_size, span, marks):
    """ECC mask, baseline frame coords: the square within `REGION_SPANS` Target
    spans of the ring (corners reach ~2.1 spans) — so gravel and sky, which move
    differently from the Board, do not vote — less a hole of PATCH + SEARCH
    around every mark being measured, so no mark helps register itself."""
    square = board.RING_CENTRE_TPL + REGION_SPANS * span * np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])
    region = np.zeros(frame_size[::-1], np.uint8)
    cv2.fillConvexPoly(region, board._apply(view.H, square).astype(np.int32), 255)
    for x, y in board._apply(view.H, marks):
        cv2.circle(region, (int(round(x)), int(round(y))), PATCH + SEARCH, 0, -1)
    return region


def split(displacement):
    """`(drift, jitter)` magnitudes of a mark's per-frame Board-space
    displacement (N x 2): drift is its rolling mean over `DRIFT_FRAMES`,
    jitter what is left."""
    d = np.asarray(displacement, np.float64)
    h = DRIFT_FRAMES // 2
    padded = np.pad(d, ((h, h), (0, 0)), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, DRIFT_FRAMES, axis=0)
    drift = windows.mean(axis=2)  # a median latches onto one side of a two-valued flicker
    return np.linalg.norm(drift, axis=1), np.linalg.norm(d - drift, axis=1)


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
    raw_ref, skipped, lost = [None] * len(marks), [0] * len(marks), 0
    for index, gray, current in frames:
        if current is None:
            lost += 1
            continue
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
                skipped[i] += 1  # off the frame, on the search edge, or under MIN_NCC
                continue
            here = board._apply(to_template, [found])[0]
            errors[i].append(here - t)
            scores[i].append(score)
            raw_moves[i].append(float(np.linalg.norm(found - raw_ref[i])))
    rows = []
    for i, t in enumerate(marks):
        if not errors[i]:
            rows.append(dict(mark=i + 1, found=False))  # at the frame edge, or never matched
            continue
        d = np.array(errors[i])
        e = np.linalg.norm(d, axis=1)
        drift, jitter = split(d)
        rows.append(dict(mark=i + 1, found=True, frames=len(e), skipped=skipped[i],
                         drift=float(np.percentile(drift, 95)),
                         jitter=float(np.percentile(jitter, 95)),
                         distance=float(np.linalg.norm(t - board.RING_CENTRE_TPL)),
                         median=float(np.median(e)), p95=float(np.percentile(e, 95)),
                         max=float(e.max()), raw_max=float(np.max(raw_moves[i])),
                         ncc=float(np.median(scores[i]))))
    return rows, lost


def _report(measured, span, label):
    rows, lost = measured
    print(f"[REACH] {label}: {lost} frame(s) failed to register and are not counted")
    print(f"[REACH] mark  distance(tpl px)  spans  frames  skipped  median  p95  max  "
          f"(template px; MATCH_TPL_PX {board.MATCH_TPL_PX:.0f})  raw-frame max  NCC  "
          f"p95 drift / jitter")
    for r in sorted(rows, key=lambda r: r.get("distance", -1)):
        if not r["found"]:
            print(f"   #{r['mark']:<3} at the frame edge, or never matched above MIN_NCC")
            continue
        print(f"   #{r['mark']:<3} {r['distance']:8.0f}  {r['distance'] / span:5.2f}  "
              f"{r['frames']:5d}  {r['skipped']:6d}  {r['median']:6.1f} {r['p95']:5.1f} {r['max']:5.1f}"
              f"{'  OVER' if r['p95'] > board.MATCH_TPL_PX else '      '}   "
              f"{r['raw_max']:5.1f}  {r['ncc']:.2f}  {r['drift']:5.1f} / {r['jitter']:4.1f}")


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
    p.add_argument("--registration", choices=("runtime", "affine", "texture"), default="runtime",
                   help="how each frame is registered; see the module docstring (#50)")
    p.add_argument("--motion", choices=("affine", "homography"), default="affine",
                   help="texture mode only: the correction's degrees of freedom")
    a = p.parse_args()
    # No --final-run: this is an investigation, never the sealed measurement.
    manifest.gate(a.video, False, None, "registration_reach.py")

    _, template_mask = board.find_targets(cv2.imread(board.DEFAULT_TEMPLATE), min_area=1)
    span = board.contour_span(board.template_contour(template_mask))
    base, view = evaluate.baseline_view(a.video, a.start, template_mask)
    if a.appeared is None:
        marks, _ = evaluate.load_truth(
            None, os.path.join(a.truth_labels, evaluate.RAW_NAMES["before"]), base, view)
        from_index, label = [0] * len(marks), "from the baseline"
    else:
        marks, _ = evaluate.load_truth(None, a.truth_labels, base, view)
        times = [float(t) for t in a.appeared.split(",")]
        if len(times) != len(marks):
            raise SystemExit(f"--appeared has {len(times)} times for {len(marks)} new Bullet Holes")
        fps = cv2.VideoCapture(a.video).get(cv2.CAP_PROP_FPS)
        from_index = [int(round((t - a.start) * fps)) for t in times]
        label = "wander after appearance (NOT baseline marks)"

    if a.registration == "runtime":
        frames = _registered(a.video, a.start, a.end, template_mask, view)
    elif a.registration == "affine":
        frames = _anchored(a.video, a.start, a.end, view, _green, cv2.MOTION_AFFINE)
    else:
        motion = cv2.MOTION_HOMOGRAPHY if a.motion == "homography" else cv2.MOTION_AFFINE
        frames = _anchored(a.video, a.start, a.end, view, _gray, motion,
                           texture_region(view, base.shape[1::-1], span, marks))
    print(f"[REACH] registration: {a.registration}"
          + (f", {a.motion}" if a.registration == "texture" else ""))
    _report(measure(frames, marks, from_index), span, label)
