"""Report only the Bullet Holes that appear after a baseline frame.

Two things the plain detector cannot do on its own:

- **Baseline (SOW 2.1.6).** A Board usually arrives already shot. Bullet Holes
  present in the baseline frame are recorded once and never reported again.
- **Persistence.** A real Bullet Hole appears and then stays put. A false
  positive on gravel or a shadow flickers. Requiring a detection to survive
  PERSIST of its confirmation window removes the bulk of the false positives
  without retraining anything — measured on CamA_20260914_141546: 70 candidates
  collapse to 7.

The camera is not static (~16px drift over 12s on that clip), so every frame is
registered back to the baseline frame before positions are compared.

Counts here are Bullet Holes, never Hits — see
docs/adr/0001-report-bullet-holes-not-hits.md. Two bullets through one mark are
one Bullet Hole, and no amount of temporal evidence separates them.
"""
import argparse
import os

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Single-class yolo26n, trained on Bullet Holes only. Replaces
# kanat_model10_v.2.0 (3-class, board/bullet_hole/target), which scored below its
# own Capture Profile floor on real range footage and so reported nothing.
DEFAULT_MODEL = os.path.join(BASE_DIR, "trained_models", "kanat_yolo26n_v1", "weights", "best.pt")

MATCH_PX = 22    # two detections are the same Bullet Hole within this, in baseline-frame px
PERSIST  = 0.70  # fraction of the confirmation window it must still be seen in
PERSIST_FRAMES = 50  # length of that window. Fixed, so the verdict does not depend
                     # on how long a clip happens to run: measured to the end of the
                     # clip instead, the same Bullet Hole confirms over 13-17s and
                     # fails over 13-25s purely because registration drifts further.

# ponytail: registration is one full-frame homography per frame, correcting camera
# drift only. It does not rectify the Board or separate Targets — that is the
# rectify-first design in bullet_hole_detection_pipeline_updated.md, still to come.


def track_new_bullet_holes(per_frame, n_frames, match_px=MATCH_PX, persist=PERSIST,
                           window=PERSIST_FRAMES):
    """Fold per-frame detections into confirmed new Bullet Holes.

    `per_frame` is [(frame_idx, Nx2 array of centres in baseline coords), ...],
    already stripped of anything matching the baseline. **Only frames that
    registered successfully appear in it**, and a registered frame with no
    detections must appear with an empty array rather than be omitted: the
    denominator below counts the frames that actually got a look, so a
    registration failure neither counts for nor against a Bullet Hole.

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


def _detect(model, frame, imgsz, conf):
    r = model.predict(frame, imgsz=imgsz, conf=conf, verbose=False)[0]
    return np.array([[(float(b.xyxy[0][0]) + float(b.xyxy[0][2])) / 2,
                      (float(b.xyxy[0][1]) + float(b.xyxy[0][3])) / 2]
                     for b in r.boxes], np.float32).reshape(-1, 2)


def _gray(frame):
    return cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255, (5, 5), 0)


def process(video, start, end, model_path, imgsz, conf, out_video=None):
    from ultralytics import YOLO  # imported lazily: pulls in torch
    model = YOLO(model_path)

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    ok, base = cap.read()
    if not ok:
        raise SystemExit(f"cannot read {video} at {start}s")
    baseline = _detect(model, base, imgsz, conf)
    gb = _gray(base)
    n_frames = int((end - start) * fps)
    print(f"[INFO] baseline: {len(baseline)} pre-existing Bullet Holes at {start}s")

    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6)
    W = np.eye(3, dtype=np.float32)
    per_frame = []
    lost = 0
    for idx in range(1, n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        try:
            _, W = cv2.findTransformECC(gb, _gray(frame), W, cv2.MOTION_HOMOGRAPHY, crit, None, 5)
        except cv2.error:
            lost += 1
            continue  # registration lost; this frame is no evidence either way
        pts = _detect(model, frame, imgsz, conf)
        if len(pts):
            pts = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), np.linalg.inv(W)).reshape(-1, 2)
            if len(baseline):
                pts = pts[np.min(np.linalg.norm(baseline[None] - pts[:, None], axis=2), axis=1) >= MATCH_PX]
        per_frame.append((idx, pts))  # empty is meaningful: looked, saw nothing

    if lost:
        print(f"[WARN] registration lost on {lost} frame(s); excluded from persistence")

    new = track_new_bullet_holes(per_frame, n_frames)
    print(f"[INFO] {len(new)} new Bullet Holes")
    for i, c in enumerate(new, 1):
        print(f"  #{i}  t={start + c['first_frame'] / fps:5.2f}s  "
              f"pos=({c['pos'][0]:6.0f},{c['pos'][1]:6.0f})  persistence {c['persistence']:.0%}")

    if out_video:
        _render(video, start, n_frames, fps, baseline, new, out_video)
    return new


def _render(video, start, n_frames, fps, baseline, new, out_video):
    """Second pass: redraw the clip with the baseline and the confirmed Bullet Holes.

    Positions are in baseline-frame coordinates and the camera drifts, so each
    frame is registered again here. Detection is not repeated.
    """
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    ok, base = cap.read()
    gb = _gray(base)
    vw = cv2.VideoWriter(out_video, cv2.VideoWriter_fourcc(*"avc1"), fps,
                         (int(cap.get(3)), int(cap.get(4))))
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6)
    W = np.eye(3, dtype=np.float32)
    frame, idx = base, 0
    while idx < n_frames:
        if idx:
            ok, frame = cap.read()
            if not ok:
                break
            try:
                _, W = cv2.findTransformECC(gb, _gray(frame), W, cv2.MOTION_HOMOGRAPHY, crit, None, 5)
            except cv2.error:
                pass
        vis = frame.copy()

        def to_frame(p):
            return np.int32(cv2.perspectiveTransform(np.float32([[p]]), W)[0][0])

        for p in baseline:
            cv2.circle(vis, tuple(to_frame(p)), 9, (150, 150, 150), 2)
        shown = 0
        for c in new:
            if idx < c["first_frame"]:
                continue
            shown += 1
            q = to_frame(c["pos"])
            cv2.circle(vis, tuple(q), 16, (0, 0, 255), 3)
            cv2.putText(vis, f"#{shown}", (q[0] + 19, q[1] + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(vis, f"t {start + idx / fps:5.2f}s", (20, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.putText(vis, f"pre-existing {len(baseline)}", (20, 84),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (150, 150, 150), 2)
        cv2.putText(vis, f"NEW {shown}", (20, 126),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
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
    p.add_argument("--inference-size", type=int, default=1280)
    p.add_argument("--confidence", type=float, default=0.4)
    p.add_argument("--out", help="write an annotated video here")
    a = p.parse_args()
    process(a.video, a.start, a.end, a.model, a.inference_size, a.confidence, a.out)
