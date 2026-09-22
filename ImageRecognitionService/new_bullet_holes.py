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
import itertools
import os
from typing import NamedTuple

import cv2
import numpy as np

import board
import manifest

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

# How many frames the baseline is built from.
#
# The baseline answers "was this mark already on the Board?", and whatever it
# fails to see is reported as a new Bullet Hole. Built from one frame it
# inherits every miss of that frame. Measured on CamB_20260915_102250: a mark
# 127 Board px clear of anything else was missed by the t=0 frame, detected at
# 0.40 from t=0.04s onward, and reported as new 40 ms after the baseline. No
# bullet arrives in one frame.
#
# 5 frames at 25 fps is ~200 ms. The bound the other way is real and is why this
# stays small: a Hit landing *inside* the baseline window is absorbed into the
# baseline and never reported. The baseline interval must therefore precede the
# shooting interval, which --start already puts under the operator's control.
#
# The alternative rejected here was lowering the baseline's confidence floor.
# 0.20 recovers the same mark on this clip, but by 0.10 the baseline starts
# suppressing on the printed rings — blinding the pipeline to Bullet Holes on
# the one Target CamB finally put bullets on. That is a constant fitted to one
# clip with a narrow safe band; this is a duration.
BASELINE_FRAMES = 5   # PROVISIONAL: exercise on the held-out recordings

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

# Two detections are the same Bullet Hole if their centres lie within
# DUP_CENTER_FACTOR x the mean box diagonal, or their boxes overlap by more than
# OVERLAP_THRESHOLD of the smaller box's area.
#
# Ported unchanged from tagging_bullets.is_duplicate_bullet, where 0.5 is
# measured rather than chosen: across the sample images the closest genuinely
# distinct Bullet Holes sit 0.93x diagonal apart while duplicate boxes of one
# Bullet Hole sit below 0.3x, so the gate falls in the empty gap between them.
#
# This pipeline shipped without it and regressed. MATCH_TPL_PX is a constant in
# TEMPLATE px, which is scale-invariant and correct as a floor, but says nothing
# about how large the mark is: on CamB_20260915_102250 it came to 2.96 Board px
# against a torn mark 13 Board px across, and one Bullet Hole was reported twice.
# Box diagonals scale with the mark itself, which is the property needed here.
DUP_CENTER_FACTOR = 0.5   # measured in tagging_bullets.py; not re-tuned here
OVERLAP_THRESHOLD = 0.5


# --- Non-co-occurrence merge: CANDIDATE MITIGATION, OFF BY DEFAULT ----------
#
# Measured on CamB_20260915_102250: one physical mark was reported as two Bullet
# Holes 27 Board px apart. Across 363 frames the two positions NEVER appeared
# together — 306 frames at one, 49 at the other, 0 at both. Two genuine Bullet
# Holes co-occur constantly once both exist; one mark displaced by registration
# cannot.
#
# The cause is geometric and is NOT fixed here: CamB has a single Target, so the
# homography is constrained only near it and the far field is extrapolation. A
# probe beside the Target holds to 2 px median while one 105 px away throws
# excursions to 34 px. This rule is protection against the failure mode, not a
# replacement for registration that holds. See HANDOVER.md.
#
# It is off because it is validated on two clips and neither is a held-out
# recording. Turn it on with --merge-displaced.
NON_COOCCURRENCE_MERGE = False      # PROVISIONAL: not production behaviour
MAX_DISPLACEMENT_FRACTION = 0.35    # PROVISIONAL: see merge_displaced_tracks


def merge_displaced_tracks(holes, reference, fraction=MAX_DISPLACEMENT_FRACTION):
    """Fold a Bullet Hole that is a displaced sighting of an earlier one.

    Never co-occurring is necessary but nowhere near sufficient — a mark that is
    genuinely covered up, and a later unrelated mark, also never co-occur. All
    three must hold:

    1. **Never seen in the same frame.** The direct evidence of one mark.
    2. **Overlapping spans.** The later track must sit inside the earlier one's
       lifetime, which is what an excursion looks like: A, then B while A is
       absent, then A again. Two marks separated by a long gap in which neither
       was seen fail this, and should.
    3. **Displacement plausible for its distance from the Target.** Registration
       error grows with distance from the one feature constraining the fit, so
       the bound scales with it rather than being a flat radius. Measured: 9.3 px
       at 58 px out (0.16x) and 34 px at 105 px out (0.26x); 0.35 admits both
       with margin and is a guess beyond them.

    Returns `(kept, merged)` where `merged` is [(survivor, absorbed), ...] so the
    caller can report what it did rather than silently dropping a Bullet Hole.
    """
    if not holes or reference is None or not reference.targets:
        return holes, []
    centre = np.asarray(reference.targets[0], np.float64).reshape(-1, 2).mean(axis=0)

    # Identity, not equality: these dicts hold numpy arrays, and `in`/`remove`
    # would compare them elementwise and raise.
    alive, merged = {id(h) for h in holes}, []
    for later in sorted(holes, key=lambda h: h["first_frame"], reverse=True):
        if id(later) not in alive:
            continue
        for earlier in sorted((h for h in holes if id(h) in alive),
                              key=lambda h: h["first_frame"]):
            if earlier is later or earlier["first_frame"] >= later["first_frame"]:
                continue
            if set(earlier["seen"]) & set(later["seen"]):
                continue                                   # (1) they co-occur
            if max(later["seen"]) > max(earlier["seen"]):
                continue                                   # (2) spans do not overlap
            reach = float(np.linalg.norm(later["pos"] - centre))
            if float(np.linalg.norm(later["pos"] - earlier["pos"])) > fraction * reach:
                continue                                   # (3) too far to be a displacement
            alive.discard(id(later))
            merged.append((earlier, later))
            break
    return [h for h in holes if id(h) in alive], merged


def _overlap_fraction(a, b):
    """Box intersection as a fraction of the smaller box's area."""
    dx = min(a[0] + a[2] / 2, b[0] + b[2] / 2) - max(a[0] - a[2] / 2, b[0] - b[2] / 2)
    dy = min(a[1] + a[3] / 2, b[1] + b[3] / 2) - max(a[1] - a[3] / 2, b[1] - b[3] / 2)
    if dx <= 0 or dy <= 0:
        return 0.0
    smaller = min(a[2] * a[3], b[2] * b[3])
    return float(dx * dy / smaller) if smaller > 0 else 0.0


def same_bullet_hole(a, b, floor_px):
    """Are two detections the same Bullet Hole? Each is (cx, cy) or (cx, cy, w, h).

    Counting marks, not bullets — see docs/adr/0001. Two centres inside the
    floor are one Bullet Hole whatever their boxes say; beyond it, the boxes
    decide. Centres-only input keeps the old floor-only behaviour, so callers
    that have no box (and the tracker's own tests) are unaffected.
    """
    distance = float(np.hypot(a[0] - b[0], a[1] - b[1]))
    if distance < floor_px:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    if _overlap_fraction(a, b) > OVERLAP_THRESHOLD:
        return True
    mean_diagonal = (float(np.hypot(a[2], a[3])) + float(np.hypot(b[2], b[3]))) / 2
    return distance < DUP_CENTER_FACTOR * mean_diagonal


def baseline_marks(frames, match_px):
    """Fold detections from several baseline frames into one set of marks.

    `frames` is a list of per-frame detection arrays, each (cx, cy) or
    (cx, cy, w, h). The union is de-duplicated on the template-px floor alone,
    deliberately, for the same reason suppression is: the box arms of
    `same_bullet_hole` belong to clustering, and using them here would fold two
    genuinely distinct pre-existing marks into one, understating the baseline
    and manufacturing a false positive downstream.

    Within the floor the marks are the same, so nothing is lost by keeping the
    first sighting: suppression asks only how far a later detection is from the
    nearest baseline mark.
    """
    marks = []
    for pts in frames:
        for p in np.asarray(pts, np.float32):  # always 2-D, and may be empty
            if not any(np.hypot(m[0] - p[0], m[1] - p[1]) < match_px for m in marks):
                marks.append(p.copy())
    return np.array(marks, np.float32) if marks else np.zeros((0, 4), np.float32)


def strip_pre_existing(pts, baseline, match_px):
    """Drop detections matching a mark already on the Board at the baseline.

    Floor only, deliberately: the box arms of `same_bullet_hole` belong to
    clustering, not to suppression. Measured on CamB_20260915_102250 25-36s,
    using them here swallowed a real new Bullet Hole next to a pre-existing one
    and took recall from 100% to 75%. Same trap as the 40 template-px radius in
    ADR-0003: whatever gates "already in the baseline" bounds recall directly.

    Returns `(survivors, residuals)`. A residual is how far a suppressed
    detection sat from the baseline mark it matched. The mark is stationary and
    the detection is of that same mark, so the distance is registration error
    and nothing else — the one geometry measurement available per frame without
    ground truth. See the [REGISTRATION] line in `process`.
    """
    if not len(pts) or not len(baseline):
        return pts, np.zeros(0, np.float32)
    distance = np.min(np.linalg.norm(
        baseline[None, :, :2] - np.asarray(pts)[:, None, :2], axis=2), axis=1)
    return pts[distance >= match_px], distance[distance < match_px]


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
        for p in np.asarray(pts, np.float32):  # (cx, cy) or (cx, cy, w, h), always 2-D
            match = next((c for c in candidates if same_bullet_hole(c[0], p, match_px)), None)
            if match is None:
                candidates.append([p.copy(), [idx], idx])
            else:
                n = len(match[1])
                match[0] = (match[0] * n + p) / (n + 1)
                match[1].append(idx)

    confirmed = []
    for pos, sightings, first in candidates:
        if first + window > n_frames:
            continue  # window has not elapsed; unconfirmable, not rejected
        span = sum(1 for i in looked_at if first <= i < first + window)
        if span <= 0:
            continue
        # Distinct FRAMES, not sightings: two detections on one mark in one frame
        # both fold into this candidate, and counting each made that frame worth
        # double. Numerator and denominator now take the same window, so the
        # ratio cannot exceed 1 and needs no clamp. The lower bound is not
        # decoration — `first` is the frame the candidate was FIRST ENCOUNTERED
        # in, so out-of-order input put sightings in the numerator that the
        # denominator never saw. Measured at 1.5, hidden by `min(ratio, 1.0)`.
        #
        # Position still averages over every sighting: that running mean is what
        # folds CamB's two halves into one Bullet Hole over 275 frames, pinned by
        # `test_camb_split_is_not_merged_by_the_gate_alone`. Persistence asks how
        # many frames saw the mark, position asks where it is.
        seen = sorted(set(sightings))
        ratio = sum(1 for i in seen if first <= i < first + window) / span
        if ratio >= persist:
            confirmed.append({"pos": pos[:2], "box": pos, "first_frame": first,
                              "seen": seen, "persistence": ratio})
    return sorted(confirmed, key=lambda c: c["first_frame"])


def _detect(model, image, imgsz, conf):
    """Detections as (cx, cy, w, h) in canvas px.

    The size is not decoration: `same_bullet_hole` needs the mark's own
    footprint, because a radius fixed in template px can come out smaller than
    the Bullet Hole it is supposed to merge.
    """
    boxes = []
    for b in model.predict(image, imgsz=imgsz, conf=conf, verbose=False)[0].boxes:
        x0, y0, x1, y1 = (float(v) for v in b.xyxy[0])
        boxes.append([(x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0])
    return np.array(boxes, np.float32).reshape(-1, 4)


def _round32(x):
    return max(32, int(round(x / 32)) * 32)


def _corroborated(point, changed_mask, radius):
    """Did change detection also see something here? Evidence, not a gate."""
    h, w = changed_mask.shape
    x, y = int(point[0]), int(point[1])
    r = int(max(1, radius))
    x0, y0, x1, y1 = max(0, x - r), max(0, y - r), min(w, x + r + 1), min(h, y + r + 1)
    return bool(x1 > x0 and y1 > y0 and changed_mask[y0:y1, x0:x1].any())


def _next_view(cap, template_mask, last):
    """Read one frame and re-register Board space onto it.

    Returns `(frame, view)`. `view` is None when the Board was not found or ECC
    failed — no evidence from that frame, either way — and `(None, None)` when
    the read itself failed, which is the end of what the file holds.

    Every caller that DETECTS goes through `RegisteredFrames.looks`, on
    purpose: a second way of reading and registering frames is a silent
    difference between what one caller measures and what the runtime sees.
    `_render` still reads the clip itself, and may — it repeats no detection,
    so it cannot disagree about the image the model was shown.
    """
    ok, frame = cap.read()
    if not ok:
        return None, None
    try:
        current, _ = board.track_view(frame, template_mask, last)
    except cv2.error:
        current = None
    return frame, current


class Look(NamedTuple):
    """One frame, as the runtime saw it.

    `view` is None — and with it `canvas` and `detections` — when the Board was
    not found or ECC failed. That is deliberately not the same value as an empty
    `detections` array: "the Board was lost" and "looked and saw nothing" mean
    opposite things to any rate whose denominator is frames that got a look, and
    a caller that cannot tell them apart scores a registration failure as a
    detector miss.
    """
    index: int
    view: board.BoardView | None
    canvas: np.ndarray | None
    detections: np.ndarray | None

    @property
    def registered(self):
        return self.view is not None


class RegisteredFrames:
    """One iteration over a recording: read, register, rectify, detect.

    The pipeline and anything measuring the detector go through here, so that a
    probe cannot silently measure a different image than the runtime does. The
    risk is measured, not hypothetical: two scalings compose into the detector's
    effective scale, at net scale 1.81 the model returns ZERO detections, and
    `imgsz` fits the canvas's LONGEST side — an early version of this pipeline
    read it as the width, letterboxed a 709x1063 Board to 0.66 instead of 0.99
    and starved the detector without saying so (HANDOVER.md, "Five things").
    A second loop written beside this one can differ in either and then report a
    number about a distribution the runtime never sees.

    Board space is fixed once, by the frame at `--start`, and every later frame
    is registered onto it.

    Built by `open`. The constructor takes its collaborators directly so the
    iteration can be exercised without a video file or a model.
    """

    def __init__(self, cap, model, template_mask, view, base, imgsz, conf,
                 fps, start):
        self.cap, self.model, self.template_mask = cap, model, template_mask
        # Two views, and the difference matters: `view` is the Board space
        # everything is registered ONTO, fixed by the frame at `--start`, and
        # `last` is the most recently registered frame, which is what the next
        # ECC fit starts from and what Target assignment reads at the end.
        self.view = self.last = view
        self.imgsz, self.conf = imgsz, conf
        self.fps, self.start = fps, start
        self._base = base
        self.net_scale = None   # measured by `open`; see the warning there
        self.processed = self.lost = 0

    @classmethod
    def open(cls, video, start, model_path, conf=DEFAULT_CONFIDENCE,
             template_path=board.DEFAULT_TEMPLATE):
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
        # Detection is zero by net scale 1.81 and flat below ~1.1, so any figure
        # taken through this loop is only comparable to another at the same
        # scale. Kept on the instance rather than only printed, so a caller can
        # say what its measurement was taken under.

        # Correlation is deliberately NOT called a registration-health figure. It
        # sat at 0.94-0.96 on CamB_20260915_102250 through a window in which a
        # stationary mark's Board-space position walked 4.6 px out of place. It says
        # the ECC fit converged, nothing more. The [REGISTRATION] line in `process`
        # is the figure that bears on geometry.
        print(f"[BOARD] {len(view.targets)} Target(s), ECC converged at {correlation:.4f} "
              f"(convergence, not geometric accuracy)")
        print(f"[BOARD] rectified {canvas_w}x{canvas_h}, imgsz {imgsz}, net scale {scale:.2f}")
        if not 0.5 <= scale <= 1.2:
            print(f"[WARN] net scale {scale:.2f} is outside the measured working band "
                  f"(0.5-1.2, flat within it); detection is zero by ~1.8")
        loop = cls(cap, model, template_mask, view, base, imgsz, conf, fps, start)
        loop.net_scale = scale
        return loop

    def frames_until(self, end):
        """How many frames lie between `--start` and `end` seconds."""
        return int((end - self.start) * self.fps)

    def looks(self, n_frames):
        """Yield a `Look` per frame read, up to `n_frames` from `--start`.

        Frames that failed to register are yielded too, unregistered — see
        `Look`. Iteration stops early when the file runs out, which is why
        callers take `processed` from here rather than assuming `n_frames`.

        The first frame is the one Board space was built from, so it is already
        read and already registered; it is yielded like any other.
        """
        try:
            while self.processed < n_frames:
                if self.processed:
                    frame, current = _next_view(self.cap, self.template_mask, self.last)
                    if frame is None:
                        break  # the end of what the file holds
                else:
                    frame, current = self._base, self.view
                index, self.processed = self.processed, self.processed + 1
                if current is None:
                    self.lost += 1
                    yield Look(index, None, None, None)
                    continue
                self.last = current
                canvas = current.rectify(frame)
                yield Look(index, current, canvas,
                           _detect(self.model, canvas, self.imgsz, self.conf))
        finally:
            self.cap.release()


class Run(NamedTuple):
    """What a run found, and the evidence needed to attribute what it got wrong.

    The baseline and the residual leave `process` for the same reason the
    `[REGISTRATION]` line is printed: a false positive sitting on a pre-existing
    mark is registration displacement, not a detector error, and nothing
    downstream can tell those apart without the marks that were already on the
    Board. Board space, all three — `baseline` is directly comparable with
    `holes[i]["pos"]`.
    """
    holes: list
    baseline: np.ndarray   # pre-existing marks, (cx, cy, w, h)
    residual: np.ndarray   # distance from a suppressed detection to its mark


def registration_note(residual, radius, unit="Board px"):
    """The one `[REGISTRATION]` sentence, in whatever units the caller measures in.

    `process` reports it in Board px, `evaluate.py` in the template px a score is
    read in. One sentence either way, so the censoring rule has a single place to
    be wrong in — and one that says the same thing in both.

    It is a disclosure and never a gate. No registration-failure bar has been
    validated, so nothing refuses a run on the strength of this line. See
    docs/adr/0006-every-false-positive-is-attributed.md.
    """
    if not len(residual):
        return ("[REGISTRATION] no detection matched a baseline mark, so this "
                "run measures no registration residual at all")
    # A max sitting at the radius is the ceiling, not the worst error: it says
    # displaced marks are probably being reported as new Bullet Holes.
    return (f"[REGISTRATION] residual on {len(residual)} baseline-matched "
            f"detection(s): median {np.median(residual):.1f}, max "
            f"{residual.max():.1f} {unit}, censored at the {radius:.1f} {unit} "
            f"match radius — beyond it a displaced mark is reported as new, so "
            f"a max at the ceiling means displaced marks are reaching the "
            f"threshold. Not a pass/fail bar; none is validated")


def process(video, start, end, model_path, conf=DEFAULT_CONFIDENCE,
            out_video=None, ring_diameter_mm=None, template_path=board.DEFAULT_TEMPLATE,
            require_change_evidence=REQUIRE_CHANGE_EVIDENCE,
            merge_displaced=NON_COOCCURRENCE_MERGE,
            baseline_frames=BASELINE_FRAMES):
    loop = RegisteredFrames.open(video, start, model_path, conf, template_path)
    fps, match_px = loop.fps, loop.view.match_radius
    n_frames = loop.frames_until(end)
    looks = loop.looks(n_frames)

    # The baseline is built from BASELINE_FRAMES frames, not one. Everything it
    # fails to see is reported as a new Bullet Hole, and a single frame passes
    # its own misses straight through. These frames contribute no persistence
    # evidence: within the baseline window nothing can be new, which is exactly
    # the risk the constant documents.
    #
    # They come off the front of the same iterator the run continues on, so the
    # baseline cannot be built from a differently rectified Board than the one
    # it is subtracted from.
    baseline_frames = max(1, baseline_frames)  # 0 or less would mean no baseline at all
    baseline_canvas, baseline_detections = None, []
    for look in itertools.islice(looks, baseline_frames):
        if not look.registered:
            continue
        if baseline_canvas is None:
            # Always look 0's: Board space is built from that frame, so `open`
            # has already raised if it did not register. This is the image
            # change detection is measured against for the rest of the run.
            baseline_canvas = look.canvas
        baseline_detections.append(look.detections)
    baseline = baseline_marks(baseline_detections, match_px)
    short = ("" if len(baseline_detections) == baseline_frames else
             f" (of {baseline_frames} requested; the rest were lost or unread)")
    print(f"[INFO] baseline: {len(baseline)} pre-existing Bullet Holes over "
          f"{len(baseline_detections)} frame(s) from {start}s{short}")

    per_frame, corroboration, residuals_per_frame, lost = [], [], [], 0
    for look in looks:
        if not look.registered:
            lost += 1
            continue  # no evidence from this frame, either way
        pts, matched = strip_pre_existing(look.detections, baseline, match_px)
        residuals_per_frame.append(matched)
        if len(pts):
            changed = board.changed_regions(baseline_canvas, look.canvas)
            corroboration += [p for p in pts if _corroborated(p, changed, match_px / 2)]
        per_frame.append((look.index, pts))  # empty is meaningful: looked, saw nothing

    processed = loop.processed
    if lost:
        print(f"[WARN] Board lost on {lost} frame(s); excluded from persistence")

    # A short read is not a crash. The interpreter is alive, the window is simply
    # shorter than asked for, and the frames never read must not lengthen the
    # confirmation horizon: a candidate whose window runs past where reading
    # stopped is unconfirmable, exactly as one running past --end is.
    if processed < n_frames:
        print(f"[WARN] truncated: processed {processed} of {n_frames} requested "
              f"frames; confirmation is measured against what was read")

    # Registration error on stationary marks. Each residual is the distance from
    # a detection to the baseline mark it matched — same physical mark, so the
    # distance is registration and nothing else. Measured on CamB 25-27s it
    # ramps rather than spiking: a displaced mark is a perfectly persistent
    # false positive, and persistence cannot filter it. See HANDOVER.md.
    residuals = (np.concatenate(residuals_per_frame)
                 if any(len(r) for r in residuals_per_frame) else np.zeros(0))
    print(registration_note(residuals, match_px))

    # Target assignment reads ONE frame — the last that registered — and Target
    # identity is that frame's contour order, largest first. So a Bullet Hole on
    # a Target that frame happened to lose is reported as a Miss, and its
    # "Target 2" need not be the baseline's Target 2. Not fixed here: it changes
    # Target/Miss assignment, which is a measured output, and no labelled
    # footage is available to measure the change against. Said out loud instead,
    # so a run cannot hide it — this project has twice sent work to the wrong
    # place by diagnosing a symptom it could not see.
    if len(loop.last.targets) != len(loop.view.targets):
        print(f"[WARN] the frame Targets are assigned from sees "
              f"{len(loop.last.targets)} Target(s) where the baseline saw "
              f"{len(loop.view.targets)}: Target numbers below need not match the "
              f"baseline's, and a Bullet Hole on a Target this frame lost is "
              f"reported as a Miss")

    new = track_new_bullet_holes(per_frame, processed, match_px)
    for hole in new:
        hole["target"] = loop.last.assign(hole["pos"])
        hole["corroborated"] = any(
            same_bullet_hole(c, hole["box"], match_px) for c in corroboration)

    if require_change_evidence:
        before = len(new)
        new = [h for h in new if h["corroborated"]]
        print(f"[FILTER] change evidence required: {before} -> {len(new)} Bullet Holes")

    if merge_displaced:
        new, merged = merge_displaced_tracks(new, loop.last)
        for survivor, absorbed in merged:
            print(f"[MERGE] displaced sighting at t="
                  f"{start + absorbed['first_frame'] / fps:.2f}s folded into the Bullet Hole "
                  f"at t={start + survivor['first_frame'] / fps:.2f}s "
                  f"({float(np.linalg.norm(absorbed['pos'] - survivor['pos'])):.0f} Board px, "
                  f"never co-occurring)")
        if not merged:
            print("[MERGE] no displaced sightings found")

    _report(new, start, fps, loop.last, ring_diameter_mm,
            [idx for idx, _ in per_frame])
    if out_video:
        _render(video, start, processed, fps, loop.template_mask, loop.view,
                baseline, new, out_video)
    return Run(new, baseline, residuals)


def _report(new, start, fps, view, ring_diameter_mm, looked_at):
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

    # Scoring needs no calibration: it is a ratio inside one picture.
    for hole in new:
        hole["score"] = None
        if hole["target"] is not None:
            hole["score"] = board.score([hole["pos"]], view, hole["target"])[0]

    for i, hole in enumerate(new, 1):
        where = "MISS" if hole["target"] is None else f"Target {hole['target'] + 1}"
        evidence = "changed" if hole["corroborated"] else "model only"
        scored = "" if hole["score"] is None else (
            "  outside rings" if hole["score"] == board.OUTSIDE_RINGS
            else f"  scores {hole['score']}")
        line = (f"  #{i}  t={start + hole['first_frame'] / fps:5.2f}s  {where:<9} "
                f"persistence {hole['persistence']:.0%}  [{evidence}]{scored}")
        if hole["mm"] is not None:
            line += f"  X {hole['mm'][0]:+7.1f} mm  Y {hole['mm'][1]:+7.1f} mm"
        elif hole["target"] is not None and ring_diameter_mm is not None:
            line += "  (mm unavailable)"
        print(line)

        # Observation facts, not a claim about the mark. A detection ceasing is
        # not evidence that the Bullet Hole ceased: on CamB_20260915_102250 a
        # mark stopped being detected at any confidence from ~4s and stayed
        # plainly visible to the operator until 25s. The Bullet Hole stays
        # confirmed; the operator gets to see that it stopped being seen.
        # Denominator is frames that REGISTERED since first sighting, not frames
        # read: a Board-lost frame neither counts for nor against a Bullet Hole,
        # the same rule `track_new_bullet_holes` applies to persistence. Counting
        # reads here would understate detection on a clip with dropouts.
        seen = hole["seen"]
        span = sum(1 for i in looked_at if i >= hole["first_frame"])
        share = f", {len(seen) / span:.0%} of frames since" if span > 0 else ""
        print(f"      first detected: {start + hole['first_frame'] / fps:.2f}s   "
              f"last detected: {start + max(seen) / fps:.2f}s   "
              f"detected in {len(seen)} frame(s){share}")


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
            cv2.circle(vis, tuple(np.int32(p[:2])), 9, (150, 150, 150), 2)
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
    p = argparse.ArgumentParser("Report Bullet Holes that are new since the baseline")
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
    p.add_argument("--merge-displaced", action="store_true",
                   help="PROVISIONAL, off by default. Fold a Bullet Hole that "
                        "never co-occurs with an earlier one, overlaps its span "
                        "and sits within a plausible displacement — one mark "
                        "moved by registration rather than two marks. Protection "
                        "against the failure mode, not a registration fix.")
    p.add_argument("--baseline-frames", type=int, default=BASELINE_FRAMES,
                   help="PROVISIONAL. How many frames from --start the baseline "
                        "is built from. One frame passes its own misses through "
                        "as new Bullet Holes; a Hit landing inside this window is "
                        "absorbed into the baseline and never reported, so the "
                        "window must precede the shooting.")
    p.add_argument("--out", help="write an annotated video of the rectified Board here")
    manifest.add_flag(p)
    a = p.parse_args()

    # Split membership before anything is opened: a sealed recording is refused
    # unless this run says it is the final one. See manifest.py and ADR-0005.
    manifest.gate(a.video, a.final_run, a.model, "new_bullet_holes.py")

    process(a.video, a.start, a.end, a.model, a.confidence, a.out, a.ring_mm,
            a.template, not a.no_change_filter, a.merge_displaced, a.baseline_frames)
