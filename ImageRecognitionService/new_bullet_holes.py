"""Report the Bullet Holes that appear on a Board after a baseline frame.

The runtime pipeline from bullet_hole_detection_pipeline_updated.md:

    frame
      -> locate Board            board.find_targets, one hue threshold
      -> homography              board.register, ECC refinement
      -> rectified Board         board.BoardView.rectify, at TARGET_NET_SCALE
      -> YOLO on the rectified Board
      -> Target / Miss           board.BoardView.assign
      -> baseline + persistence  track_new_bullet_holes, here
      -> millimetres, score      NOT IMPLEMENTED, see board.to_millimetres

Two things the plain detector cannot do on its own:

- **Baseline (SOW 2.1.6).** A Board usually arrives already shot. Bullet Holes
  present in the baseline frame are recorded once and never reported again.
- **Persistence.** A real Bullet Hole appears and then stays put. A false
  positive on gravel or a shadow flickers. Measured on CamA_20260914_141546,
  requiring a detection to survive its confirmation window cut 70 candidates to
  7 — with no retraining, and where no confidence threshold could separate them.

Change detection runs alongside as corroborating evidence only, never as the
gate: it covers at best 4 of 5 known new Bullet Holes at any threshold.

Counts are Bullet Holes, never Hits — see
docs/adr/0001-report-bullet-holes-not-hits.md. Two bullets through one mark are
one Bullet Hole, and no amount of temporal evidence separates them.
"""
import argparse
import os

import cv2
import numpy as np

import board

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Single-class yolo26n, trained on Bullet Holes only. Replaces
# kanat_model10_v.2.0 (3-class, board/bullet_hole/target), which scored below its
# own Capture Profile floor on real range footage and so reported nothing.
DEFAULT_MODEL = os.path.join(BASE_DIR, "trained_models", "kanat_yolo26n_v1", "weights", "best.pt")

# --- Provisional working values --------------------------------------------
# Not validated. Hand-set against a single clip, to be tuned against the
# held-out customer test set. See board.py for the same warning about the
# geometry constants.
# Measured against operator ground truth on CamA_20260914_141546 (6 Hits, all in
# one group): at 0.70 only 1 of the group survived; at 0.50 all 4 the model found
# survived. The four that 0.70 discarded had persistences of 0.50-0.62 — real
# Bullet Holes, rejected by a bar set from nothing but intuition.
PERSIST = 0.50        # PROVISIONAL
PERSIST_FRAMES = 50   # PROVISIONAL length, but FIXED by design: measured to the end
                      # of the clip instead, the same Bullet Hole confirms over
                      # 13-17s and fails over 13-25s purely because registration
                      # drifts further over the longer run.
DEFAULT_CONFIDENCE = 0.40  # PROVISIONAL

# Require change detection to corroborate a confirmed Bullet Hole.
#
# This is a narrower role than the gate rejected in ADR-0003: it filters
# CONFIRMED Bullet Holes rather than deciding what the model looks at, so a
# missed candidate is still detected and can still be recovered by lowering the
# bar. On the ground-truth clip it removed 5 of 7 false positives and cost
# nothing real — every one of the four true Bullet Holes was corroborated.
#
# It is not free. The same footage shows change detection blind to 1 in 5 real
# Bullet Holes, so this trades recall for precision. Turn it off with
# --no-change-filter when recall matters more.
REQUIRE_CHANGE_EVIDENCE = True  # PROVISIONAL


def track_new_bullet_holes(per_frame, n_frames, match_px, persist=PERSIST,
                           window=PERSIST_FRAMES):
    """Fold per-frame detections into confirmed new Bullet Holes.

    `per_frame` is [(frame_idx, Nx2 array of Board-space centres), ...], already
    stripped of anything matching the baseline. **Only frames that registered
    successfully appear in it**, and a registered frame with no detections must
    appear with an empty array rather than be omitted: the denominator below
    counts the frames that actually got a look, so a registration failure neither
    counts for nor against a Bullet Hole.

    A candidate whose window has not yet elapsed is not reported. Shortening the
    denominator instead would confirm a Bullet Hole seen in 7 of the 10 frames
    that happened to remain — exactly the clip-length dependence the fixed window
    exists to remove.

    Kept free of cv2 and the model so the logic is testable on plain arrays.
    """
    looked_at = sorted(idx for idx, _ in per_frame)

    candidates = []  # [pos, seen_frame_idxs, first_idx]
    for idx, pts in per_frame:
        for p in np.asarray(pts, np.float32).reshape(-1, 2):
            match = next((c for c in candidates if np.linalg.norm(c[0] - p) < match_px), None)
            if match is None:
                candidates.append([p.copy(), [idx], idx])
            else:
                n = len(match[1])
                match[0] = (match[0] * n + p) / (n + 1)
                match[1].append(idx)

    confirmed = []
    for pos, seen, first in candidates:
        if first + window > n_frames:
            continue  # window has not elapsed; unconfirmable, not rejected
        span = sum(1 for i in looked_at if first <= i < first + window)
        if span <= 0:
            continue
        ratio = sum(1 for i in seen if i < first + window) / span
        if ratio >= persist:
            confirmed.append({"pos": pos, "first_frame": first,
                              "persistence": min(ratio, 1.0)})
    return sorted(confirmed, key=lambda c: c["first_frame"])


def _detect(model, image, imgsz, conf):
    r = model.predict(image, imgsz=imgsz, conf=conf, verbose=False)[0]
    return np.array([[(float(b.xyxy[0][0]) + float(b.xyxy[0][2])) / 2,
                      (float(b.xyxy[0][1]) + float(b.xyxy[0][3])) / 2]
                     for b in r.boxes], np.float32).reshape(-1, 2)


def _round32(x):
    return max(32, int(round(x / 32)) * 32)


def _corroborated(point, changed_mask, radius):
    """Did change detection also see something here? Evidence, not a gate."""
    h, w = changed_mask.shape
    x, y = int(point[0]), int(point[1])
    r = int(max(1, radius))
    x0, y0, x1, y1 = max(0, x - r), max(0, y - r), min(w, x + r + 1), min(h, y + r + 1)
    return bool(x1 > x0 and y1 > y0 and changed_mask[y0:y1, x0:x1].any())


def process(video, start, end, model_path, conf=DEFAULT_CONFIDENCE,
            out_video=None, ring_diameter_mm=None, template_path=board.DEFAULT_TEMPLATE,
            require_change_evidence=REQUIRE_CHANGE_EVIDENCE):
    from ultralytics import YOLO  # imported lazily: pulls in torch
    model = YOLO(model_path)

    template = cv2.imread(template_path)
    if template is None:
        raise SystemExit(f"cannot read Target artwork at {template_path}")
    _, template_mask = board.find_targets(template, min_area=1)

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    ok, base = cap.read()
    if not ok:
        raise SystemExit(f"cannot read {video} at {start}s")

    # Board space is fixed here, once, and every later frame reuses it.
    view, correlation = board.build_view(base, template_mask)
    if view is None:
        raise SystemExit("no Target found in the baseline frame; cannot locate the Board")
    canvas_w, canvas_h = view.canvas_size
    # ultralytics fits the LONGEST side to imgsz, so that is what must match.
    imgsz = _round32(max(canvas_w, canvas_h))
    frame_span = board.contour_span(board.find_targets(base)[0][0])
    tpl_span = board.contour_span(board.template_contour(template_mask))
    scale = board.net_scale(view.board_scale, tpl_span, frame_span, imgsz,
                            max(canvas_w, canvas_h))

    print(f"[BOARD] {len(view.targets)} Target(s), registration correlation {correlation:.4f}")
    print(f"[BOARD] rectified {canvas_w}x{canvas_h}, imgsz {imgsz}, net scale {scale:.2f}")
    if not 0.5 <= scale <= 1.2:
        print(f"[WARN] net scale {scale:.2f} is outside the measured working band "
              f"(0.5-1.2, flat within it); detection is zero by ~1.8")

    baseline_canvas = view.rectify(base)
    baseline = _detect(model, baseline_canvas, imgsz, conf)
    match_px = view.match_radius
    print(f"[INFO] baseline: {len(baseline)} pre-existing Bullet Holes at {start}s")

    n_frames = int((end - start) * fps)
    per_frame, corroboration, lost = [], [], 0
    last = view
    for idx in range(1, n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        try:
            current, _ = board.track_view(frame, template_mask, last)
        except cv2.error:
            current = None
        if current is None:
            lost += 1
            continue  # no evidence from this frame, either way
        last = current

        canvas = current.rectify(frame)
        pts = _detect(model, canvas, imgsz, conf)
        if len(pts) and len(baseline):
            pts = pts[np.min(np.linalg.norm(baseline[None] - pts[:, None], axis=2), axis=1) >= match_px]
        if len(pts):
            changed = board.changed_regions(baseline_canvas, canvas)
            corroboration += [p for p in pts if _corroborated(p, changed, match_px / 2)]
        per_frame.append((idx, pts))  # empty is meaningful: looked, saw nothing

    cap.release()
    if lost:
        print(f"[WARN] Board lost on {lost} frame(s); excluded from persistence")

    new = track_new_bullet_holes(per_frame, n_frames, match_px)
    for hole in new:
        hole["target"] = last.assign(hole["pos"])
        hole["corroborated"] = any(
            np.linalg.norm(np.asarray(c) - hole["pos"]) < match_px for c in corroboration)

    if require_change_evidence:
        before = len(new)
        new = [h for h in new if h["corroborated"]]
        print(f"[FILTER] change evidence required: {before} -> {len(new)} Bullet Holes")

    _report(new, start, fps, last, ring_diameter_mm)
    if out_video:
        _render(video, start, n_frames, fps, template_mask, view, baseline, new, out_video)
    return new


def _report(new, start, fps, view, ring_diameter_mm):
    misses = sum(1 for h in new if h["target"] is None)
    print(f"[INFO] {len(new)} new Bullet Holes ({len(new) - misses} on a Target, {misses} Miss)")

    # A Miss has no Target and so no Shot Distance — by definition, not by
    # omission. Measuring it against some Target's centre would be a number with
    # no meaning. See CONTEXT.md, Miss.
    for hole in new:
        hole["mm"] = None
        if hole["target"] is None:
            continue
        try:
            hole["mm"] = board.to_millimetres([hole["pos"]], view, ring_diameter_mm,
                                              hole["target"])[0]
        except board.NotCalibrated as why:
            if hole is new[0]:
                print(f"[BLOCKED] millimetres unavailable: {why}")

    # Always exercised, so its blocked state is visible even once --ring-mm is
    # supplied. Silently skipping it made a half-done pipeline look finished.
    try:
        board.score([h["pos"] for h in new if h["target"] is not None], view, ring_diameter_mm)
    except board.NotCalibrated as why:
        print(f"[BLOCKED] score unavailable: {why}")

    for i, hole in enumerate(new, 1):
        where = "MISS" if hole["target"] is None else f"Target {hole['target'] + 1}"
        evidence = "changed" if hole["corroborated"] else "model only"
        line = (f"  #{i}  t={start + hole['first_frame'] / fps:5.2f}s  {where:<9} "
                f"persistence {hole['persistence']:.0%}  [{evidence}]")
        if hole["mm"] is not None:
            line += f"  X {hole['mm'][0]:+7.1f} mm  Y {hole['mm'][1]:+7.1f} mm"
        elif hole["target"] is not None and ring_diameter_mm is not None:
            line += "  (mm unavailable)"
        print(line)


def _render(video, start, n_frames, fps, template_mask, reference, baseline, new, out_video):
    """Redraw the clip as the rectified Board. Detection is not repeated."""
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    ok, base = cap.read()
    w, h = reference.canvas_size
    vw = cv2.VideoWriter(out_video, cv2.VideoWriter_fourcc(*"avc1"), fps, (w, h))
    view, idx, frame = reference, 0, base
    while idx < n_frames:
        if idx:
            ok, frame = cap.read()
            if not ok:
                break
            try:
                tracked, _ = board.track_view(frame, template_mask, view)
                if tracked is not None:
                    view = tracked
            except cv2.error:
                pass
        vis = view.rectify(frame)
        for t in view.targets:
            cv2.polylines(vis, [np.int32(t)], True, (0, 200, 0), 2)
        for p in baseline:
            cv2.circle(vis, tuple(np.int32(p)), 9, (150, 150, 150), 2)
        shown = 0
        for hole in new:
            if idx < hole["first_frame"]:
                continue
            shown += 1
            q = np.int32(hole["pos"])
            colour = (0, 165, 255) if hole["target"] is None else (0, 0, 255)
            cv2.circle(vis, tuple(q), 16, colour, 3)
            cv2.putText(vis, f"#{shown}" + ("M" if hole["target"] is None else ""),
                        (q[0] + 19, q[1] + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(vis, f"t {start + idx / fps:5.2f}s", (16, 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(vis, f"pre-existing {len(baseline)}", (16, 66),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 2)
        cv2.putText(vis, f"NEW {shown}", (16, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        vw.write(vis)
        idx += 1
    cap.release()
    vw.release()
    print(f"[INFO] -> {out_video}")


if __name__ == "__main__":
    p = argparse.ArgumentParser("Report Bullet Holes that are new since a baseline frame")
    p.add_argument("video")
    p.add_argument("--start", type=float, required=True, help="baseline timestamp, seconds")
    p.add_argument("--end", type=float, required=True,
                   help="end of the window, seconds. Allow at least "
                        f"{PERSIST_FRAMES} frames after the last expected Hit: a "
                        "Bullet Hole whose confirmation window runs past the end "
                        "is not reported.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--template", default=board.DEFAULT_TEMPLATE,
                   help="printed Target artwork used to register the Board")
    p.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    p.add_argument("--ring-mm", type=float, default=None,
                   help="measured diameter of the printed white 10-ring, in mm. "
                        "Without it, positions stay in Board pixels: every "
                        "millimetre figure scales linearly with this, so it is "
                        "not guessed.")
    p.add_argument("--no-change-filter", action="store_true",
                   help="keep confirmed Bullet Holes that change detection did "
                        "not corroborate. Raises recall, lowers precision.")
    p.add_argument("--out", help="write an annotated video of the rectified Board here")
    a = p.parse_args()
    process(a.video, a.start, a.end, a.model, a.confidence, a.out, a.ring_mm,
            a.template, not a.no_change_filter)
