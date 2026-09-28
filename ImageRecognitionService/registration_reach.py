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

`--registration` picks how each frame is registered (#50), so alternatives are
scored by the same yardstick:

- `runtime`: `board.track_view` as the pipeline runs it: ECC on the greyscale
  Board round the Target, each frame against the baseline frame (#50 B).
  `--cut-marks` cuts the measured marks out of its region, so none of them
  helps register itself; without it the probe sees what the runtime sees.
- `silhouette`: the chain before #50, an 8-parameter homography fitted to the
  one Target's green mask, seeded frame to frame.
- `affine` (#50 A): the baseline homography's perspective is held; each frame
  is registered to the BASELINE frame's green mask by an affine only.

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
DRIFT_FRAMES = 25  # drift is the rolling mean over this many frames (1 s at 25 fps)


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


def _registered(video, start, end, view, track):
    """`(index, gray frame, view)` for every frame of the window, the baseline
    first at index 0, each later one `track(frame, last registered view)`. A
    frame that fails to register comes with view None."""
    last = view
    for index, frame in _frames(video, start, end):
        try:
            current = view if index == 0 else track(frame, last)
        except cv2.error:
            current = None
        if current is not None:
            last = current
        yield index, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), current


def _silhouette(template_mask):
    """The pre-#50 `track_view`: the one Target's green mask, frame to frame."""
    def track(frame, last):
        contours, mask = board.find_targets(frame)
        if not contours:
            return None
        H, _ = board.register(template_mask, mask, contours[0], last.H)
        return board.BoardView(H, last.tpl_to_board, last.canvas_size, [])
    return track


def _green_affine(base):
    """#50 A: an affine on the green mask, against the baseline frame's."""
    ref = _green(base)

    def track(frame, last):
        a = last.anchor
        W, _ = board.ecc_warp(ref, _green(frame), cv2.MOTION_AFFINE,
                              last.H @ np.linalg.inv(a.H))
        return board.BoardView(W @ a.H, last.tpl_to_board, last.canvas_size, [], a)
    return track


def _green(frame):
    """The blurred green mask the silhouette registration fits."""
    return board._blurred(board.find_targets(frame)[1])


def cut_marks(anchor, marks):
    """`anchor` with a hole of PATCH + SEARCH frame px cut round every mark,
    so no mark being measured helps register itself."""
    region = anchor.region.copy()
    for x, y in board._apply(anchor.H, marks):
        cv2.circle(region, (int(round(x)), int(round(y))), PATCH + SEARCH, 0, -1)
    return anchor._replace(region=region)


def split(displacement, frame=None):
    """`(drift, jitter)` magnitudes of a mark's per-frame Board-space
    displacement (N x 2): drift is its rolling mean over `DRIFT_FRAMES`,
    jitter what is left. `frame` is each sample's frame index; frames with no
    sample (skipped, or failed to register) stay gaps, so the window is always
    `DRIFT_FRAMES` of video time and not that many samples."""
    d = np.asarray(displacement, np.float64)
    frame = np.arange(len(d)) if frame is None else np.asarray(frame) - frame[0]
    full = np.full((frame[-1] + 1, 2), np.nan)
    full[frame] = d
    h = DRIFT_FRAMES // 2
    padded = np.pad(full, ((h, h), (0, 0)), mode="edge")  # both ends are samples
    windows = np.lib.stride_tricks.sliding_window_view(padded, DRIFT_FRAMES, axis=0)[frame]
    drift = np.nanmean(windows, axis=2)  # a median latches onto one side of a two-valued flicker
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
    errors, raw_moves, scores, at = ([[] for _ in marks] for _ in range(4))
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
            at[i].append(index)
            scores[i].append(score)
            raw_moves[i].append(float(np.linalg.norm(found - raw_ref[i])))
    rows = []
    for i, t in enumerate(marks):
        if not errors[i]:
            rows.append(dict(mark=i + 1, found=False))  # at the frame edge, or never matched
            continue
        d = np.array(errors[i])
        e = np.linalg.norm(d, axis=1)
        drift, jitter = split(d, at[i])
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
    p.add_argument("--registration", choices=("runtime", "silhouette", "affine"),
                   default="runtime", help="how each frame is registered; see the "
                                           "module docstring (#50)")
    p.add_argument("--cut-marks", action="store_true",
                   help="runtime mode: cut the measured marks out of the ECC region")
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

    if a.cut_marks:
        view.anchor = cut_marks(view.anchor, marks)
    if a.registration == "runtime":
        track = lambda frame, last: board.track_view(frame, last)[0]
    elif a.registration == "silhouette":
        track = _silhouette(template_mask)
    else:
        track = _green_affine(base)
    print(f"[REACH] registration: {a.registration}{', marks cut' if a.cut_marks else ''}")
    frames = _registered(a.video, a.start, a.end, view, track)
    _report(measure(frames, marks, from_index), span, label)
