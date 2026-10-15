"""Report the Bullet Holes that appear on a Board after a baseline frame.

The runtime pipeline from bullet_hole_detection_pipeline_updated.md:

    frame
      -> locate Board            board.find_targets, one hue threshold
      -> homography              board.register (baseline), board.track_view (#50)
      -> rectified Board         board.BoardView.rectify, at TARGET_NET_SCALE
      -> YOLO on the rectified Board
      -> Target / Miss           board.BoardView.assign
      -> baseline + persistence  Persistence, here
      -> millimetres, score      NOT IMPLEMENTED, see board.to_millimetres

Two things the plain detector cannot do on its own:

- **Baseline (SOW 2.1.6).** A Board usually arrives already shot. Bullet Holes
  present in the baseline frame are recorded once and never reported again.
- **Persistence.** A real Bullet Hole appears and then stays put. A false
  positive on gravel or a shadow flickers. Measured on CamA_20260914_141546,
  requiring a detection to survive its persistence window cut 70 candidates to
  7 — with no retraining, and where no confidence threshold could separate them.

Change detection runs alongside as corroborating evidence only, never as the
gate: it covers at best 4 of 5 known new Bullet Holes at any threshold.

Counts are Bullet Holes, never Hits — see
docs/adr/0001-report-bullet-holes-not-hits.md. Two bullets through one mark are
one Bullet Hole, and no amount of temporal evidence separates them.
"""
from __future__ import annotations

import argparse
import bisect
import contextlib
import csv
import itertools
import math
import os
import platform
import signal
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from urllib.parse import urlsplit, urlunsplit

import cv2
import numpy as np

from detection import board, groups, webapp
from tools import manifest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ImageRecognitionService/

# Single-class yolo26n, trained on Bullet Holes only. Replaces
# kanat_model10_v.2.0 (3-class, board/bullet_hole/target), which scored below its
# own Capture Profile floor on real range footage and so reported nothing.
BULLET_HOLE_CLASS = "bullet_hole"   # by name: its id differs between checkpoints
DEFAULT_MODEL = os.path.join(BASE_DIR, "trained_models", "kanat_yolo26n_v1", "weights", "best.pt")

# --- Provisional working values --------------------------------------------
# Not validated. Hand-set against a single clip, and fixed before the sealed
# run, which evaluates them and is never tuned on (ADR-0005). See board.py for
# the same warning about the geometry constants.
# Measured against operator ground truth on CamA_20260914_141546 (6 Hits, all in
# one group): at 0.70 only 1 of the group survived; at 0.50 all 4 the model found
# survived. The four that 0.70 discarded had persistences of 0.50-0.62 — real
# Bullet Holes, rejected by a bar set from nothing but intuition.
PERSIST = 0.50        # PROVISIONAL
PERSIST_FRAMES = 50   # PROVISIONAL length, but FIXED by design: measured to the end
                      # of the clip instead, the same Bullet Hole persists over
                      # 13-17s and fails over 13-25s purely because registration
                      # drifts further over the longer run.
DEFAULT_CONFIDENCE = 0.40  # PROVISIONAL

# Canvas px of the margin canvas each exposed-Board band carries for context,
# so a mark straddling the margin canvas's edge is seen whole (#46). One
# stride-32 cell; measured at this value on the four spent/threshold-work
# recordings, not swept.
BAND_CONTEXT_PX = 32       # PROVISIONAL

# Consecutive lost frames before the loop re-acquires the Board on its own
# (#80): 1 s at 25 fps and stride 1, ~17 s at LIVE_STRIDE (ADR-0007, #84).
# Counted in frames the loop attempted. A failed attempt
# is itself a lost frame, so attempts fall every this many frames while the
# Board stays lost. Set from the SOW wording, not from footage.
REANCHOR_AFTER_LOST = 25   # PROVISIONAL

# A converged fit can be on the wrong scene altogether: CamA_20260914_150248
# pans off the Board at frame 19 and tracking converges on the Board next over
# for ~80 frames (#92). At or past this silhouette disagreement
# (`board.silhouette_disagreement`, Board px at the reference Target's centre)
# the frame counts as lost, so it feeds the re-anchor above (#110). #92's gap:
# wrong 180-1008 on `_150248`; right at most 24 on `_141846`'s re-aim, its
# artefact burst included, and 3.1 on still clips. The bound is the gap's
# geometric mean, ~2.7x clear of each side. Two CamA clips, at their board scale.
GROSS_DISAGREEMENT_PX = 66.0    # PROVISIONAL
# Below the gross bound nothing is rejected: a moderately wrong fit (`_144747`'s
# occlusion 2-21, #91's synthetic shift 5.0-6.4) reads like one following a real
# re-aim (`_141846`, 5-9). Past the most a still clip read, a checked fit is
# counted and the run warns once.
MODERATE_DISAGREEMENT_PX = 3.1  # PROVISIONAL: the most a right fit read on a still clip

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

# Require change detection to corroborate a persisted Candidate.
#
# This is a narrower role than the gate rejected in ADR-0003: it filters
# PERSISTED Candidates rather than deciding what the model looks at, so a
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


def _fold(candidates, idx, pts, match_px):
    """One Look's Detections into the candidates, in place, for `Persistence`.
    A candidate is [pos, seen_frame_idxs, first_idx].

    ponytail: each Detection is matched against every candidate so far, kept
    or not, as the whole-run fold always was. That is once a Look, so a very
    long Range slows its Looks; index candidates spatially if one does."""
    for p in np.asarray(pts, np.float32):  # (cx, cy) or (cx, cy, w, h), always 2-D
        match = next((c for c in candidates if same_bullet_hole(c[0], p, match_px)), None)
        if match is None:
            candidates.append([p.copy(), [idx], idx])
        else:
            n = len(match[1])
            match[0] = (match[0] * n + p) / (n + 1)
            match[1].append(idx)


def _judge(candidate, looked_at, lost, persist=PERSIST, window=PERSIST_FRAMES,
           unseen=()):
    """The persisted Candidate a candidate whose window has elapsed is, or
    None. `looked_at`, `lost` and `unseen` are sorted frame indices, as
    `Persistence` keeps them.
    Counted by bisection, so judging does not slow as a run's history grows
    (#83)."""
    pos, sightings, first = candidate
    span = _count_in(looked_at, first, first + window)
    tried = (span + _count_in(lost, first, first + window)
             + _count_in(unseen, first, first + window))
    if span <= 0 or span < persist * tried:
        # Too few looks survived registration to call anything persistent:
        # 100% of one frame among lost ones is not persistence.
        # Unconfirmable, not rejected, as above. Measured on
        # CamA_20260914_150248 once its pan frames were lost (#110): two
        # surviving wrong fits confirmed 9 false Bullet Holes on 1-2 looks.
        # Against frames tried, not the window: a stride (#81) leaves ~4
        # looks a window at 13 on purpose.
        return None
    # Distinct FRAMES, not sightings: two detections on one mark in one frame
    # both fold into this candidate, and counting each made that frame worth
    # double. Numerator and denominator now take the same window, so the
    # ratio cannot exceed 1 and needs no clamp. The lower bound is part of
    # the window's definition, kept though Looks now arrive in order: without
    # it, out-of-order input once put sightings in the numerator that the
    # denominator never saw. Measured at 1.5, hidden by `min(ratio, 1.0)`.
    #
    # Position still averages over every sighting: that running mean is what
    # folds CamB's two halves into one Bullet Hole over 275 frames, pinned by
    # `test_camb_split_is_not_merged_by_the_gate_alone`. Persistence asks how
    # many frames saw the mark, position asks where it is.
    seen = sorted(set(sightings))
    ratio = sum(1 for i in seen if first <= i < first + window) / span
    if ratio < persist:
        return None
    return {"pos": pos[:2], "box": pos, "first_frame": first,
            "seen": seen, "persistence": ratio}


def _count_in(sorted_indices, lo, hi):
    """How many of `sorted_indices` fall in [lo, hi)."""
    return bisect.bisect_left(sorted_indices, hi) - bisect.bisect_left(sorted_indices, lo)


def _detect(model, image, imgsz, conf, device=None):
    """Detections as (cx, cy, w, h) in canvas px, on `device` when one is
    given. Without one the detector is handed none, so its library's default
    stands: CUDA if available, else CPU, never MPS (#129).

    The size is not decoration: `same_bullet_hole` needs the mark's own
    footprint, because a radius fixed in template px can come out smaller than
    the Bullet Hole it is supposed to merge.

    Bullet Holes only: the v2.0 checkpoint also emits Board and Target boxes,
    and a Target box read as a mark is a false positive nothing downstream
    can tell apart.
    """
    boxes, handed = [], {} if device is None else {"device": device}
    for b in model.predict(image, imgsz=imgsz, conf=conf, verbose=False,
                           classes=_bullet_hole_classes(model), **handed)[0].boxes:
        x0, y0, x1, y1 = (float(v) for v in b.xyxy[0])
        boxes.append([(x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0])
    return np.array(boxes, np.float32).reshape(-1, 4)


def _bullet_hole_classes(model):
    classes = [k for k, v in model.names.items() if v == BULLET_HOLE_CLASS]
    if not classes:
        raise SystemExit(f"model has no {BULLET_HOLE_CLASS!r} class: {model.names}")
    return classes


def _round32(x):
    return max(32, int(round(x / 32)) * 32)


def _band_imgsz(crop):
    """A band's imgsz, by the same rule as the canvas's: its longest side."""
    x0, y0, x1, y1 = crop
    return _round32(max(x1 - x0, y1 - y0))


def _corroborated(point, changed_mask, radius):
    """Did change detection also see something here? Evidence, not a gate."""
    h, w = changed_mask.shape
    x, y = int(point[0]), int(point[1])
    r = int(max(1, radius))
    x0, y0, x1, y1 = max(0, x - r), max(0, y - r), min(w, x + r + 1), min(h, y + r + 1)
    return bool(x1 > x0 and y1 > y0 and changed_mask[y0:y1, x0:x1].any())


def merge_band_detections(inner, band_hits, match_radius):
    """Detections on the margin canvas, plus those on the exposed Board past it.

    All are (cx, cy, w, h) in grown-canvas px; `band_hits` pairs each `Band`
    with what was detected on its crop. The margin canvas's are kept whole:
    they are what it reported before #46. A band's are kept only inside the
    region it owns, which lies past the margin canvas and no other band's,
    and only if no margin-canvas detection is within `match_radius`.

    That last test is the one suppression here, and it does not merge Bullet
    Holes (ADR-0002): its crop overlaps the margin canvas by the context strip,
    so a mark straddling the boundary is seen by both inferences, and it is the
    margin canvas's to report. It uses the existing match radius, no new
    threshold."""
    inner = np.asarray(inner, np.float64).reshape(-1, 4)
    kept = []
    for band, found in band_hits:
        found = np.asarray(found, np.float64).reshape(-1, 4)
        x0, y0, x1, y1 = band.owns
        kept.append(found[(found[:, 0] >= x0) & (found[:, 0] < x1)
                          & (found[:, 1] >= y0) & (found[:, 1] < y1)])
    bands = np.vstack(kept) if kept else np.zeros((0, 4))
    if len(inner) and len(bands):
        nearest = np.hypot(bands[:, None, 0] - inner[None, :, 0],
                           bands[:, None, 1] - inner[None, :, 1]).min(axis=1)
        bands = bands[nearest >= match_radius]
    return np.vstack([inner, bands])


def change_evidence(points, view, inner_changed, changed, radius):
    """`_corroborated` for each point, on the canvas it was detected on.

    A point on the margin canvas is judged on the margin canvas's change mask
    at its own px, exactly as before #46 — `changed_regions` normalises over
    the whole canvas, so the grown canvas's mask would move it. A point past
    it is judged on the grown canvas's. The masks are callables, built only if
    a point needs them. Points are float64 so that removing the whole-pixel
    offset recovers the margin canvas px exactly."""
    points = np.asarray(points, np.float64).reshape(-1, 2)
    on_inner = view.in_inner(points)
    dx, dy = view.inner.offset
    inner_mask = inner_changed() if on_inner.any() else None
    grown_mask = changed() if (~on_inner).any() else None
    return [_corroborated((p[0] - dx, p[1] - dy), inner_mask, radius) if inside
            else _corroborated(p, grown_mask, radius)
            for p, inside in zip(points, on_inner)]


def _is_stream(source):
    """Is the source a live stream (#83), rather than a recording's path?"""
    return urlsplit(source).scheme in ("rtsp", "rtsps")


def _redacted(source):
    """The source as printed: a stream URL's credentials never are (#83)."""
    if not _is_stream(source):
        return source
    parts = urlsplit(source)
    return urlunsplit(parts._replace(netloc=parts.netloc.rpartition("@")[2]))


def _gate(source, final_run, model):
    """The manifest entry for a recording, refused unless it may be looked at
    (ADR-0005). A stream is no recording the manifest knows: it is not gated,
    and has no entry (#83). So nothing here stops a Sealed recording published
    over RTSP: "never stream a Sealed recording" is #85's acceptance rule, kept
    by hand."""
    if _is_stream(source):
        return None
    return manifest.gate(source, final_run, model, "new_bullet_holes.py")


def _open_stream(url):
    """A stream's capture. FFmpeg by name: OpenCV's fallback backends print a
    URL they cannot open, credentials and all (#83). Opening and each read are
    bounded by `STREAM_TIMEOUT_MS`, so a connection that stays open but stops
    delivering frames fails a read, a drop to recover from, instead of
    blocking for FFmpeg's default 30 s (#84)."""
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG,
                            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, STREAM_TIMEOUT_MS,
                             cv2.CAP_PROP_READ_TIMEOUT_MSEC, STREAM_TIMEOUT_MS])


def _same_file(path, others):
    """Is `path` one of `others` under any name: a symlink or a hard link too,
    or a file neither has created yet? Writing an output there would destroy
    that input or other output: `--timing` truncates its file before the
    recording is read (#129). A stream's URL is no file."""
    return any(os.path.realpath(path) == os.path.realpath(o) or
               os.path.exists(path) and os.path.exists(o) and os.path.samefile(path, o)
               for o in others)


def _outputs_clash(timing, out):
    """Do `--timing` and `--out` name one file? Asked of the filesystem, so
    `timing` is created for the question if it is missing, and removed again:
    only the filesystem knows whether two names neither has created yet, such
    as `Run.mp4` and `run.mp4` on macOS, are one file (#158 review). Probed
    where a write lands, past any symlink, a dangling one too, so only the
    file it made is removed and the link is left as it was."""
    target = os.path.realpath(timing)
    made = False
    # Created only if absent, in one step: a file already there, an earlier
    # run's or one another process just made, is neither truncated nor removed.
    with contextlib.suppress(FileExistsError):
        open(target, "x").close()
        made = True
    try:
        return _same_file(target, [out])
    finally:
        if made:
            os.remove(target)


def _clock(t):
    """A wall-clock time as a live run prints it."""
    return datetime.fromtimestamp(t).strftime("%H:%M:%S.%f")[:-4]


class Frame(NamedTuple):
    """A due frame, as a source's `read` hands it over: its index, counted
    from frame 0, and its image. `wait` is a Stream's Frame Wait (CONTEXT.md),
    in seconds from the reader having it decoded to the loop taking it, and
    None on a Recording, which has none (#130)."""
    index: int
    image: np.ndarray
    wait: float | None = None


class BulletHoleConfirmed(NamedTuple):
    """A Confirmed Bullet Hole as `process` publishes it (#155): once, built
    on the detection thread when it is Confirmed, and never updated
    (ADR-0004). `first_seen_at` is its first frame's `wall_clock`, UTC
    (#152). `template_xy` is its place on the Board in Template coordinates,
    unclipped. `target` is None for a Miss, and `mm` its Position, or None
    without one."""
    first_frame: int
    first_seen_at: datetime
    template_xy: tuple[float, float]
    target: int | None
    mm: tuple[float, float] | None


def _confirmed(hole, view, wall_clock):
    """A measured Bullet Hole as published: Board space mapped back onto the
    template by `view`, its first frame's time by `wall_clock` (#155)."""
    inv = np.linalg.inv(view.tpl_to_board).astype(np.float32)
    x, y = cv2.perspectiveTransform(np.array([[hole["pos"]]], dtype=np.float32), inv)[0, 0]
    mm = hole["mm"]
    seen = wall_clock(hole["first_frame"]).astimezone(timezone.utc)   # --ref-time's offset, if any
    return BulletHoleConfirmed(hole["first_frame"], seen, (float(x), float(y)), hole["target"],
                               None if mm is None else (float(mm[0]), float(mm[1])))


class Recording:
    """A Recording's frames from `--start` (CONTEXT.md: Recording), read
    through the interface every source answers (`RegisteredFrames`).

    With a `stride` (#81) the first `baseline_frames` are all due, and past
    them only indices that are multiples of `stride`. The rest are grabbed
    without decoding and never handed over: gaps, not lost frames. Indices
    stay positions in the Recording, and `passed` counts every frame passed,
    due or not, gaps after the last due one included. `read` hands back None
    at the end of the file, or once `n_frames` have passed.

    `ref_time` is the wall clock at the Recording's t=0, `--ref-time`, and
    by default the time the run opened it.
    """
    live = False
    unseen = ()   # a Recording misses no frame

    def __init__(self, cap, fps, start, ref_time=None):
        self.cap, self.fps, self.start_s = cap, fps, start
        self.ref_time = ref_time or datetime.now(timezone.utc)
        self.passed = 0

    @classmethod
    def open(cls, path, start, ref_time=None):
        """The Recording at `start` seconds, and frame 0, read there."""
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
        ok, frame = cap.read()
        if not ok:
            raise SystemExit(f"cannot read {path} at {start}s")
        return cls(cap, fps, start, ref_time), frame

    def start(self, n_frames, stride, baseline_frames):
        self._wanted, self._stride, self._baseline_frames = n_frames, stride, baseline_frames
        self.passed = 1 if n_frames > 0 else 0   # frame 0, the one `open` read

    def read(self):
        while self.passed < self._wanted:
            index = self.passed
            if _looked_at(index, self._stride, self._baseline_frames):
                ok, image = self.cap.read()
                if not ok:
                    return None   # the end of what the file holds
                self.passed += 1
                return Frame(index, image)
            if not self.cap.grab():
                return None
            self.passed += 1
        return None

    def when(self, index):
        """Seconds into the Recording, as printed."""
        return f"{self.start_s + index / self.fps:.2f}s"

    def wall_clock(self, index):
        """The wall clock by `ref_time`, as posted (#152)."""
        return self.ref_time + timedelta(seconds=self.start_s + index / self.fps)

    def close(self):
        self.cap.release()


class Stream:
    """A Stream (CONTEXT.md: Stream), read on a thread of its own so that
    frames keep arriving while a look is being processed (#83). `start`
    makes SIGINT and SIGTERM `stop` it and starts the thread; `close` stops
    and joins it, restores the handlers and prints the live report.

    A failed read is a drop, never the end: the stream closed, or stalled past
    `STREAM_TIMEOUT_MS`. The thread reopens it with `reopen` every
    `RECONNECT_EVERY_S`, for as long as the run goes on, and the frames the
    drop missed, counted at `LIVE_FPS` from the last frame received, are gaps:
    indices jump past them (#84). Those a look was due on are `unseen`, and
    count against persistence's floor as lost frames do: a window a drop
    emptied confirms nothing, rather than confirm on the one look before it.
    Nothing else restarts, so registration resumes from the last view, in
    the same Board space.

    The thread grabs every frame, keeps those a look is due on (`_looked_at`),
    and holds the newest for the loop. A due frame a newer one replaces before
    the loop takes it is one the loop was too late for: dropped and counted,
    and a gap for persistence, so nothing queues. Until the loop asks for its
    first frame past the baseline, each is held until taken instead, so the
    baseline is consecutive frames however slow its looks, and lateness and
    catching up start once it is built.

    `read` hands back the frame held as a `Frame` with its Frame Wait (#130),
    about a Look Time at most since a newer frame replaces it. Not so the
    first past the baseline, or two: decoded while the reader still blocked
    for the baseline, they waited out its last Looks, and a short run's max
    and P99 are theirs. Or None once the run is
    stopped, the thread has ended, or `n_frames` have passed: one past the
    last frame looked at, `passed`. A frame's index is its position in the
    stream: by its timestamp (`cv2.CAP_PROP_POS_MSEC`), at `LIVE_FPS` from
    its RTSP session's first frame (#117). Frame 0 is the one `open` read and
    built Board space from. `when` is a looked-at frame's time by the same
    timestamps, from the wall clock frame 0 was read at (a later RTSP
    session's first frame, after a drop), not when it was read, and
    `wall_clock` the same time as posted to the WebApp (#152).

    Frames lost upstream are gaps too (#117). Until the baseline is built
    nothing reads the stream past the frame in hand, and MediaMTX discards
    for a reader about 2.6 s behind at 8 Mbit/s (#85). Those frames never
    arrive, but the next frame's timestamp is past them, so indices jump past
    them: each gap is logged, and its due frames are `unseen`. A frame whose
    timestamp is not later than the one before is untrusted: placed one past
    it and counted, as is each after it until a timestamp advances again, and
    frames are indexed from that one, as from an RTSP session's first. It is
    placed by its advance on the last frame a step timed, so a loss before it
    is still a gap, or one past the frame before with none this session or a
    timestamp behind it (a reset). So a backend with no timestamps counts
    frames as read. When the timestamps timed no more than half the frames,
    the report warns so and gives the wall-clock arrival rate instead of
    theirs (#83). Indices are counted at `LIVE_FPS`, the configured 25 fps,
    for gap accounting (ADR-0007): a stream at another rate is unsupported,
    and its windows would count stream time, not frames.

    Still not counted or corrected: a discard smaller than a frame leaves no
    gap in the timestamps, only a frame that decodes corrupt (25 RTP packets
    in #117's replay). Frames after a gap decode corrupt up to the next
    keyframe too, and are looked at all the same. The frames a drop missed
    are #84's wall-clock estimate, since timestamps restart with each RTSP
    session (1.4 s over in #85). And `open` reads frame 0 once FFmpeg has
    buffered about 1.2 s of stream (#85), so every time is about that late.
    """
    live = True

    def __init__(self, cap, arrived, reopen):
        self.cap, self.index, self._reopen = cap, 0, reopen
        self.fps = LIVE_FPS   # the configured rate, not the stream's (ADR-0007)
        self.times = {0: arrived}
        self.received, self.first, self.latest = 1, arrived, arrived
        self.late, self.stopped = 0, False
        self.drops, self._down = [], False   # (seconds, frames missed) each
        self.unseen = []   # due frames a drop or an upstream gap missed, in order
        self.upstream, self.untimed = [], 0   # (frames lost, due) each gap (#117)
        self.resumed = 0   # frames the first to advance after an untimed one
        # Each timed step's rate, rounded, and the stream time the timestamps
        # span, the frames received over it, and those received since it last
        # grew (#117).
        self._steps, self._spanned = Counter(), 0.0
        self._spanned_frames, self._unspanned = 0, 0
        # The frame indices count from: its timestamp, index and wall clock.
        # An RTSP session's first, or the first to advance after an untimed one;
        # None until then (#117).
        self._origin = (cap.get(cv2.CAP_PROP_POS_MSEC), 0, arrived)
        self._pos = self._origin[0]   # the last frame's timestamp, in ms
        # The last frame its timestamp timed this RTSP session, in the origin's
        # form: what a frame resuming after untimed ones is placed from (#117).
        self._trusted = None
        self._held, self._ended = None, False
        self._taken, self._dropping, self._baseline_frames = 0, False, 1
        self._ready = threading.Condition()
        self._reader = None

    @classmethod
    def open(cls, url, start=None, ref_time=None):
        """The stream at `url`, read from where it is, and frame 0. `start`
        and `ref_time` are a Recording's: a stream cannot be seeked (#83), and
        its times are its own (#117)."""
        print(f"[LIVE] {_redacted(url)}: a stream, read from where it is. Board space "
              f"is built from the first frame read, times are the stream's timestamps "
              f"from the wall clock it was read at (#117), and "
              f"SIGINT or SIGTERM ends the run with its report (#83)")
        cap = _open_stream(url)
        ok, frame = cap.read()
        arrived = time.time()
        if not ok:
            raise SystemExit(f"cannot read {_redacted(url)}")
        return cls(cap, arrived, lambda: _open_stream(url)), frame

    def start(self, n_frames, stride, baseline_frames):
        self._wanted, self._baseline_frames = n_frames, baseline_frames
        self._handlers = {s: signal.signal(s, self.stop)
                          for s in (signal.SIGINT, signal.SIGTERM)}
        self._reader = threading.Thread(target=self._read, args=(stride, baseline_frames),
                                        daemon=True)
        self._reader.start()

    def stop(self, *signal_args):
        """End iteration after the look in hand. A signal handler, so it only
        sets a flag: taking a lock here could deadlock the thread it interrupts."""
        self.stopped = True

    def _read(self, stride, baseline_frames):
        index, offered = 0, 1   # frame 0, the one `open` read
        try:
            while not self.stopped:
                began = time.monotonic()
                # A read the timeout cut short can still return a frame
                # (measured over HTTP, #84): a stall all the same, so a drop
                # measured from the frame before it, whose time it would hide.
                if (not self.cap.grab()
                        or time.monotonic() - began >= STREAM_TIMEOUT_MS / 1000):
                    self._reconnect()
                    continue
                now = time.time()
                placed, at, step, span = self._place(index, now)
                if not self._down and placed > index + 1:
                    # Counted before the decode: the frame after a gap may not
                    # decode, and the drop that starts there must not take the
                    # gap with it, nor count its time again. So it runs from
                    # the last lost frame, a frame interval before this one,
                    # and misses this one (Codex on #121).
                    self._lost_upstream(at, range(index + 1, placed), stride, baseline_frames)
                    index, self.latest = placed - 1, now - 1 / LIVE_FPS
                # `_looked_at`, but the baseline counted in frames offered, so
                # that it stays consecutive frames across a drop (#84).
                frame = None
                if _looked_at(offered if offered < baseline_frames else placed,
                              stride, baseline_frames):
                    ok, frame = self.cap.retrieve()
                    decoded = time.perf_counter()   # Frame Wait starts here (#130)
                    if not ok:
                        # Not a frame received: a drop stays open until one
                        # is in hand, so a reopened stream that grabs but
                        # cannot decode is the same drop, not a second.
                        self._count(step, span, received=False)
                        self._reconnect()
                        continue
                self._count(step, span)
                if self._down:
                    self._back_from_drop(now, range(index + 1, placed), stride, baseline_frames)
                index, self.received, self.latest = placed, self.received + 1, now
                if frame is None:
                    continue
                offered += 1
                with self._ready:
                    # Until the loop asks for its first frame past the
                    # baseline, nothing held is replaced: the next due
                    # frame waits for the loop to take it.
                    while self._held is not None and not (self._dropping or self.stopped):
                        self._ready.wait(0.1)
                    if self._held is not None:
                        self.late += 1
                    self._held = (index, frame, at, decoded)
                    self._ready.notify()
        finally:
            with self._ready:
                self._ended = True   # however the read ended, so `read` never waits on it
                self._ready.notify()

    def _reconnect(self):
        """Reopen the stream after `RECONNECT_EVERY_S`, unless stopped. A new
        RTSP session: its timestamps restart (#117)."""
        self._origin = self._trusted = None
        if not self._down:
            self._down = True
            print(f"[LIVE] stream dropped: no frame since {_clock(self.latest)}; reopening "
                  f"every {RECONNECT_EVERY_S:g} s until it is back or the run is stopped (#84)")
        self.cap.release()
        resume = time.monotonic() + RECONNECT_EVERY_S
        while not self.stopped and time.monotonic() < resume:
            time.sleep(0.05)   # polled, so a stop is seen while waiting
        if not self.stopped:
            self.cap = self._reopen()

    def _place(self, index, now):
        """The index and time of the frame just grabbed, the one after frame
        `index`, by its timestamp (#117): counted at `LIVE_FPS` from the
        origin, and timed from the origin's wall clock. And its step from the
        frame before, in ms, None for an origin, and the stream time its
        timestamp advanced on the last frame they timed, None if none, which
        `_count` counts once the frame is received. A new RTSP session's first
        frame is the origin, placed by #84's count of the frames the drop
        missed and timed when it was read. A frame whose timestamp is not later than the one before is
        untrusted and counted, placed one past it and timed when it was read,
        and so is each after it until a timestamp advances again: that frame
        is the origin, placed and timed by its advance on the last frame its
        timestamp timed, so frames lost upstream meanwhile are still a gap. With
        none this session, or a timestamp behind it, it is placed one past the
        frame before. So neither a repeated nor a reset timestamp, nor zeros
        before real ones, shifts anything after it (Codex on #121)."""
        before, self._pos = self._pos, self.cap.get(cv2.CAP_PROP_POS_MSEC)
        if self._origin is None and (self._down or self._pos > before):
            placed, at, span = index + 1 + self._missed(now), now, None
            if not self._down and self._trusted:
                trusted_pos, trusted_index, trusted_at = self._trusted
                span = self._pos - trusted_pos
                if span > 0:
                    placed = max(placed, trusted_index + round(span * LIVE_FPS / 1000))
                    at = trusted_at + span / 1000
                    self._trusted = (self._pos, placed, at)
                else:
                    span = None
            self._origin = (self._pos, placed, at)
            return placed, at, None, span
        step = self._pos - before
        if step <= 0:
            self._origin = None
            return index + 1, now, step, None
        first_pos, first_index, first_at = self._origin
        since = self._pos - first_pos
        # Never onto the frame before's index: a step under half a frame
        # interval rounds onto it, on a stream faster than LIVE_FPS.
        placed = max(index + 1, first_index + round(since * LIVE_FPS / 1000))
        self._trusted = (self._pos, placed, first_at + since / 1000)
        return placed, self._trusted[2], step, step

    def _count(self, step, span, received=True):
        """Count a frame, by `_place`'s step and span, towards the report: a
        frame grabbed but not decoded is not received, so only its span
        counts (Codex on #121). Before the drop it may end is closed, so
        `_down` still tells an RTSP session's first. The rate is the frames
        received over the stream time the timestamps span: each span takes in
        every frame received since the last, untimed ones too, so a gap found
        on resuming, or before a frame that does not decode, shows in it; an
        origin no span reaches starts afresh (Codex on #121)."""
        if received:
            if step is None:
                if not self._down:
                    self.resumed += 1
            elif step <= 0:
                self.untimed += 1
            else:
                self._steps[round(1000 / step, 2)] += 1
            self._unspanned += 1
        if span is not None:
            self._spanned_frames += self._unspanned
            self._spanned += span / 1000
        if span is not None or step is None:
            self._unspanned = 0

    def _missed(self, now):
        """How many frames the drop the stream is back from missed, if any."""
        return max(0, round((now - self.latest) * LIVE_FPS) - 1) if self._down else 0

    def _lost_upstream(self, at, gap, stride, baseline_frames):
        """Count the frames lost upstream before the frame timed `at`: `gap`
        is their indices, and those a look was due on are `unseen` (#117)."""
        due = [i for i in gap if _looked_at(i, stride, baseline_frames)]
        self.unseen += due   # one extend: the loop's thread bisects it
        self.upstream.append((len(gap), len(due)))
        print(f"[LIVE] {len(gap)} frame(s) lost upstream, {len(gap) / LIVE_FPS:.1f} s of "
              f"stream before {_clock(at)}: {len(due)} of them due a look, counted against "
              f"persistence's floor. Frames up to the next keyframe may decode corrupt (#117)")

    def _back_from_drop(self, now, gap, stride, baseline_frames):
        """Close the drop the stream is back from. `gap` is the indices of the
        frames it missed; those a look was due on are `unseen`."""
        self._down = False
        seconds = now - self.latest
        due = [i for i in gap if _looked_at(i, stride, baseline_frames)]
        self.unseen += due   # one extend: the loop's thread bisects it
        self.drops.append((seconds, len(gap)))
        print(f"[LIVE] stream back at {_clock(now)} after {seconds:.1f} s without a frame: "
              f"{len(gap)} frame(s) missed at {LIVE_FPS} fps, {len(due)} of them due a "
              f"look and counted against persistence's floor (#84)")

    def read(self):
        if self.passed >= self._wanted:
            return None
        with self._ready:
            # Frame 0 was the baseline's first; asked for one past its last,
            # the baseline is built and lateness starts.
            self._dropping = self._taken >= self._baseline_frames - 1
            # Timed, so a stop is seen while no frame comes.
            while self._held is None and not (self._ended or self.stopped):
                self._ready.wait(0.1)
            if self.stopped or self._held is None:
                return None
            (self.index, frame, self.times[self.index], decoded), self._held = self._held, None
            wait = time.perf_counter() - decoded
            self._taken += 1
            self._ready.notify()   # the reader may be waiting for its turn
            return Frame(self.index, frame, wait)

    @property
    def passed(self):
        return self.index + 1   # one past the last frame looked at

    def when(self, index):
        """The wall clock by the stream's timestamps, as printed (#117)."""
        return _clock(self.times[index])

    def wall_clock(self, index):
        """`when`, as posted (#152)."""
        return datetime.fromtimestamp(self.times[index], timezone.utc)

    def close(self):
        for s, handler in self._handlers.items():
            signal.signal(s, handler)
        self.stopped = True
        if self._reader is not None:
            # A stalled read returns within STREAM_TIMEOUT_MS (#84).
            self._reader.join()
        self.cap.release()
        self.report(self.fps)

    def report(self, fps):
        down = sum(seconds for seconds, _ in self.drops)
        # Only timestamps that timed most frames measure the run. A frame is
        # timed by a step; an untimed frame is not, nor the first after it, nor
        # an RTSP session's first (Codex on #121).
        timed = self._steps.total()
        if 2 * timed > self.received - 1:
            # The commonest step is the camera's rate; frames received over the
            # stream time they span fall short of it by any lost (#117).
            rate = (f"by the stream's timestamps, frames step at "
                    f"{self._steps.most_common(1)[0][0]:.2f} fps, and were received at "
                    f"{self._spanned_frames / self._spanned:.2f} fps over {self._spanned:.1f} s "
                    f"of stream. Frames are indexed from them at the configured {fps:g} fps "
                    f"(ADR-0007, #117): a stream at another rate is unsupported, and its "
                    f"windows would count stream time, not frames")
        else:
            if self.received > 1:   # however the frames went untimed (Codex on #121)
                print(f"[WARN] the stream's timestamps timed only {timed} of "
                      f"{self.received} frame(s). The rest were not timed by a step: frame 0, "
                      f"{self.untimed} untimed, {self.resumed} the first to advance after "
                      f"one, and {len(self.drops)} the first after a drop. Frames lost "
                      f"upstream next to them may be neither counted nor indexed, and the "
                      f"rate is the wall clock's, high by FFmpeg's ~1.2 s of buffering at "
                      f"open (#117, #85)")
            # Time the stream was down is no time for frames to arrive in.
            elapsed = self.latest - self.first - down
            arrived = (f"{(self.received - 1) / elapsed:.2f} fps" if elapsed > 0
                       else "a rate not measured")
            rate = (f"frames arrived at {arrived} by the wall clock, over {self.received} "
                    f"frame(s) in {elapsed:.1f} s up. Persistence, the baseline and the stride "
                    f"count frames, so a stream short of {fps:g} fps stretches each of them "
                    f"(ADR-0007)")
        print(f"[LIVE] configured {fps:g} fps; {rate}")
        # Frame 0 is looked at too, read by `open` rather than taken here.
        print(f"[LIVE] {self._taken + 1} frame(s) looked at; {self.late} due frame(s) "
              f"dropped: the loop was too late for them, and they are gaps for "
              f"persistence (#83)")
        drops, still = len(self.drops), ""
        if self._down:
            drops, down = drops + 1, down + time.time() - self.latest
            still = f"; the last still down at the end, no frame since {_clock(self.latest)}"
        print(f"[LIVE] {drops} drop(s), {down:.1f} s down in all, "
              f"{sum(missed for _, missed in self.drops)} frame(s) missed{still} (#84)")
        print(f"[LIVE] {len(self.upstream)} gap(s) upstream, "
              f"{sum(lost for lost, _ in self.upstream)} frame(s) lost, "
              f"{sum(due for _, due in self.upstream)} of them due a look; {self.untimed} "
              f"frame(s) untimed: a timestamp not later than the frame before's, so placed "
              f"one past it (#117)")


def _open_source(video, start, ref_time=None):
    """A Stream for an rtsp:// URL, else a Recording, opened at `start`, and
    its frame 0: the source opener `process` uses unless handed another
    (#164)."""
    return (Stream if _is_stream(video) else Recording).open(video, start, ref_time)


def _looked_at(index, stride, baseline_frames):
    """Is this frame looked at under a stride (#81)? Every baseline frame is;
    past them, only multiples of the stride. One rule, applied by
    `Recording.read`, `Stream`'s thread and `_render`, so that they cannot
    disagree on which frames are gaps."""
    return index < baseline_frames or index % stride == 0


class Registration:
    """Places each Look's frame onto the Board as the baseline frame showed it
    (CONTEXT.md: Registration, Lost).

    Board space is fixed once, by the frame at `--start`, and every later frame
    is registered onto it, tracked from the last registered view. After
    `REANCHOR_AFTER_LOST` consecutive Lost Looks the next one is re-anchored
    into that same Board space (#80), here and only here, so evaluation and
    runtime cannot differ on it. A fit converged on the wrong scene altogether
    is Lost too (#110). How far each registered view runs off the canvas is
    kept for the end of the run (#41).

    Every caller that DETECTS registers through here, by way of
    `RegisteredFrames.looks`, on purpose: a second way of registering frames is
    a silent difference between what one caller measures and what the runtime
    sees. `_render` registers nothing: it replays the views `looks` produced,
    re-anchors included (#80).

    Built from Board space (the baseline frame's view), the baseline frame,
    the Target artwork's mask a re-anchor seeds from, and `when(index)`, a
    frame's time as printed.
    """

    def __init__(self, view, base, template_mask, when):
        # Two views, and the difference matters: `_space` is the Board space
        # everything is registered ONTO, and `last` is the most recently
        # registered frame, which is what the next ECC fit starts from. Both
        # carry the baseline's Targets (#33).
        self._space = self.last = view
        # The frame `last` was registered on: the Board's shift since it seeds
        # the next fit (#171). One frame, not one a view: `--out` keeps every view.
        self._previous = base
        self._template_mask, self._when = template_mask, when
        self._lost_run = 0      # consecutive Lost Looks, up to this one
        self.reanchors = self._reanchored = 0   # attempts, and those that registered (#80)
        # Converged fits after the first, those checked, and the verdicts (#110).
        self._converged = self._checked = self._gross = self._moderate = 0
        # How far past each canvas edge any registered frame's view has run,
        # in Board px — the baseline's is only the first (#41).
        uncovered = board.uncovered_view(view, (base.shape[1], base.shape[0]))
        self._reach = self._baseline_reach = uncovered and uncovered[1]
        self._unmeasured = 0   # later frames whose view had no footprint to measure

    def register(self, frame, index):
        """`frame`'s view, or None for a Lost Look: the Board was not found,
        ECC failed, or the fit was grossly wrong. No evidence from that frame,
        either way. `index` is the frame's, for the log."""
        due = self._lost_run > 0 and self._lost_run % REANCHOR_AFTER_LOST == 0
        try:
            view, correlation = (board.reanchor_view(frame, self._template_mask, self.last)
                                 if due else board.track_view(frame, self.last,
                                                              previous=self._previous))
        except cv2.error:
            view = None
        if view is not None and self._grossly_wrong(frame, view, correlation):
            view = None   # Lost, so it feeds the re-anchor (#110)
        if due:
            self._report_reanchor(index, view is not None)
        if view is None:
            self._lost_run += 1
            return None
        self._lost_run = 0
        self.last, self._previous = view, frame
        self._track_reach(view, frame)
        return view

    def report(self):
        """The end-of-run lines."""
        self._report_reach()
        print(f"[REGISTRATION] {self.reanchors} re-anchor attempt(s): {self._reanchored} "
              f"registered, {self.reanchors - self._reanchored} failed (#80)")
        self._report_checks()

    def _grossly_wrong(self, frame, view, correlation):
        """Is this converged fit on the wrong scene altogether (#110)?

        Only a fit converging below the re-anchor floor is checked: the check
        costs ~0.5-1 s a 1080p frame (0.96 on `_141846`, #110), against 0.2-0.6 s
        for `track_view` itself.
        Every wrong fit #92 measured converged at 0.82 or less, the gross ones
        at 0.29 or less; still clips at 0.917 or more.

        ponytail: a gross fit converging at or above the floor passes unchecked;
        #92 measured none. Check every Nth frame too if one turns up.
        """
        self._converged += 1
        if correlation >= board.REANCHOR_MIN_CORRELATION:
            return False
        disagreement = board.silhouette_disagreement(frame, self._template_mask, view)
        if disagreement is None:
            return False   # no verdict: the frame keeps its fit
        self._checked += 1
        if disagreement >= GROSS_DISAGREEMENT_PX:
            self._gross += 1
            return True
        self._moderate += disagreement > MODERATE_DISAGREEMENT_PX
        return False

    def _report_checks(self):
        floor = board.REANCHOR_MIN_CORRELATION
        print(f"[REGISTRATION] {self._checked} of {self._converged} converged fit(s) checked "
              f"against an independent silhouette fit (only those converging below "
              f"{floor}): {self._gross} grossly wrong, at or past {GROSS_DISAGREEMENT_PX:.0f} "
              f"Board px, counted lost (#110)")
        if self._moderate:
            print(f"[WARN] silhouette disagreement of {MODERATE_DISAGREEMENT_PX}-"
                  f"{GROSS_DISAGREEMENT_PX:.0f} Board px on {self._moderate} of "
                  f"{self._checked} checked fit(s): moderately wrong, or following real "
                  f"camera motion, which #92 could not tell apart, so none was rejected. "
                  f"Fits converging at or above {floor} were not checked (#110)")

    def _report_reanchor(self, index, registered):
        self.reanchors += 1
        self._reanchored += registered
        result = ("registered" if registered else
                  f"failed, the frame stays lost; next attempt after "
                  f"{REANCHOR_AFTER_LOST} more")
        print(f"[REGISTRATION] re-anchor at t={self._when(index)} "
              f"(frame {index}) after {self._lost_run} lost frame(s): {result} (#80)")

    def _track_reach(self, current, frame):
        if self._reach is None:
            return  # the baseline's view was already unmeasurable; said so
        uncovered = board.uncovered_view(current, (frame.shape[1], frame.shape[0]))
        if uncovered is None:
            self._unmeasured += 1
        else:
            self._reach = {k: max(v, uncovered[1][k]) for k, v in self._reach.items()}

    def _report_reach(self):
        """The camera moving can uncover what the baseline's view did not: say
        so once, at the end, rather than per frame.

        It cannot say the camera moved. Reach is the frame corners, extrapolated
        far from the Targets, and wanders with registration: on the still CamB
        close pose (CamB_20260915_102450, 0-3s) the left reach ran 4.4-7.0
        Target spans frame to frame while the uncovered fraction held at 94%.
        """
        if self._reach is None:
            return
        if self._unmeasured:
            print(f"[WARN] {self._unmeasured} registered frame(s)' view did not map "
                  f"onto the Board plane; how much of it was off the canvas there "
                  f"is unknown (#41)")
        # The same rounding floor the baseline's reach is cut at; anything past
        # it is Board the baseline's view did not show.
        grew = {k: v for k, v in self._reach.items()
                if v > self._baseline_reach[k] + board.ROUNDING_PX}
        if grew:
            span = board.target_span(self._space)
            where = ", ".join(f"{v / span:.2f} {k}" for k, v in grew.items())
            print(f"[WARN] registered frames put the view further off the canvas "
                  f"than the baseline did, up to {where} (Target spans): the "
                  f"camera moved, or registration far from the Targets wandered. "
                  f"A Bullet Hole there is a miss no setting can recover (#41)")


class Persistence:
    """Folds each Look's Detections into Candidates and judges which persisted
    (CONTEXT.md: Look, Lost, Candidate, Persistence; ADR-0003). A recording
    and a stream both feed it every Look, in frame order.

    A Look's Detections are Board-space (cx, cy[, w, h]), already stripped of
    anything matching the baseline. A Look that saw nothing adds an empty
    array: it counts against a Candidate. A Lost Look adds None: it counts
    neither for nor against one, down to a floor: a window in which under
    `persist` of the frames tried registered confirms nothing (#110). So do
    `unseen`, the due frames a stream missed through a drop (#84) or upstream
    loss (#117), passed by reference since the stream's thread extends it, and
    empty on a recording. A frame that was neither looked at nor due, a
    stride's gap (#81), counts for nothing, floor included.

    A Candidate is judged once its window has passed, never before. Shortening
    the window instead would find a Candidate persisted on 7 of the 10 frames
    that happened to remain: exactly the clip-length dependence the fixed
    window exists to remove. A Candidate's verdict counts only what falls
    inside its window, all known once the window has passed, so judging at
    that Look gives the verdict judging at the end of the run would.

    Change Evidence is not checked here: when it is differs by mode, on
    purpose (ADR-0003, amended 2026-10-11).

    Kept free of cv2 and the model so the logic is testable on plain arrays.
    """

    def __init__(self, match_px, persist=PERSIST, window=PERSIST_FRAMES, unseen=()):
        self.match_px, self.persist, self.window = match_px, persist, window
        self.unseen = unseen
        self.looked_at, self.lost = [], []   # frame indices, in order
        self._candidates = []
        self._judged = 0   # candidates are made in frame order, so the judged are a prefix
        self._persisted = {}   # id(hole) -> (hole, its candidate)

    def add(self, index, pts):
        """One Look: its Detections, or None if it was Lost. Returns the
        Candidates that persisted at it, each with its position and sightings
        as of now. `index + 1` frames have passed, in both modes."""
        if pts is None:
            self.lost.append(index)
        else:
            self.looked_at.append(index)
            _fold(self._candidates, index, pts, self.match_px)
        return self._judge_due(index + 1)

    def end(self, processed):
        """Judge whatever became due after the last Look, `processed` frames
        having passed: a stride can pass frames past its last Look. Returns
        every persisted Candidate in first-Detection order, refreshed in place
        to its final position and sightings. A Candidate still inside its
        window stays unconfirmable, not rejected."""
        self._judge_due(processed)
        for hole, (pos, sightings, _) in self._persisted.values():
            hole.update(pos=pos[:2], box=pos, seen=sorted(set(sightings)))
        return sorted((hole for hole, _ in self._persisted.values()),
                      key=lambda h: h["first_frame"])

    def position(self, hole):
        """Where a persisted Candidate is now, (cx, cy[, w, h])."""
        return self._persisted[id(hole)][1][0]

    def _judge_due(self, processed):
        persisted = []
        while (self._judged < len(self._candidates)
               and self._candidates[self._judged][2] + self.window <= processed):
            candidate = self._candidates[self._judged]
            self._judged += 1
            hole = _judge(candidate, self.looked_at, self.lost, self.persist, self.window,
                          self.unseen)
            if hole is not None:
                self._persisted[id(hole)] = (hole, candidate)
                persisted.append(hole)
        return persisted


class Look(NamedTuple):
    """One frame, as the runtime saw it.

    `canvas` is the whole rectified Board; `inner` is the margin canvas the
    detector was shown as it was before #46 — the same array as `canvas` when
    the canvas did not grow past it. Detections are in `canvas` px.

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
    inner: np.ndarray | None = None

    @property
    def registered(self):
        return self.view is not None


class _LookClock:
    """One Look's clock (#129, CONTEXT.md: Look Time, Inference Time).
    `start` once its frame is in hand; each `lap` closes a stage, timed from
    the boundary before it, so a Look's stages add up to its Look Time.
    `calls` is each detector call's wall clock: what the loop waited for,
    letterboxing, post-processing and, on MPS, the GPU sync included. `wait`
    is its frame's Frame Wait, None on a Recording (#130). Only the Look in
    hand is kept: rows are `process`'s, and only with `timing`."""

    def __init__(self):
        self.start()

    def start(self, wait=None):
        self.began = self._at = time.perf_counter()
        self.stages, self.calls, self.wait = {}, [], wait

    def lap(self, stage):
        now = time.perf_counter()
        self.stages[stage], self._at = now - self._at, now

    @property
    def elapsed(self):
        """From `start` to the last lap."""
        return self._at - self.began


class RegisteredFrames:
    """One iteration over a Recording or a Stream: read, register, rectify,
    detect.

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
    is registered onto it by `registration`, a `Registration` (#138).

    Frames come from `source`, a `Recording` or a `Stream`, through one
    interface (#148), so nothing here asks which. `opener(video, start,
    ref_time)` gives it and frame 0, by default `_open_source`; `start` takes
    the frames wanted, the stride and the baseline's frames; `read` hands back
    each due `Frame`, then None; `close` releases it. `passed` is the frames
    passed, `when` a frame's time as printed, `wall_clock` its time as posted
    to the WebApp (#152), `unseen` the due frames a Stream missed, and `live`
    which it is.

    `device`, when given, is handed to the detector on every call (#129).
    `clock` times the Look in hand: `looks` starts it and laps registration,
    rectification and the detector; `process` laps the rest.

    Built by `open`. The constructor takes its collaborators directly so the
    iteration can be exercised without a video file or a model.
    """

    def __init__(self, source, model, view, base, imgsz, conf, registration, device=None):
        self.source, self.model, self.device = source, model, device
        self.clock = _LookClock()
        self.view = view   # Board space, fixed by the frame at `--start`
        self.imgsz, self.conf = imgsz, conf
        self.fps, self.live, self.when = source.fps, source.live, source.when
        self.wall_clock = source.wall_clock
        self._base = base
        self.net_scale = None   # measured by `open`; see the warning there
        self.registration = registration
        self.lost = 0
        # The Board past the margin canvas, searched by a second inference (#46).
        self.bands = view.exposed_bands(BAND_CONTEXT_PX)

    @classmethod
    def open(cls, video, start, model_path, conf=DEFAULT_CONFIDENCE,
             template_path=board.DEFAULT_TEMPLATE, ref_time=None, device=None, opener=None):
        from ultralytics import YOLO  # imported lazily: pulls in torch
        model = YOLO(model_path)
        _bullet_hole_classes(model)   # refuse a wrong checkpoint before any video work

        template = cv2.imread(template_path)
        if template is None:
            raise SystemExit(f"cannot read Target artwork at {template_path}")
        _, template_mask = board.find_targets(template, min_area=1)

        # How long building Board space takes is measured from opening the
        # source, so the model load above is not in it (#79).
        opened_at = time.perf_counter()
        source, base = (opener or _open_source)(video, start, ref_time)

        view, correlation = board.build_view(base, template_mask)
        if view is None:
            raise SystemExit("no Target found in the baseline frame; cannot locate the Board")
        # A disclosure for agreeing what "fast" means with the customer, and
        # never a gate: no bar is agreed (#77).
        print(f"[REGISTRATION] Board space built in {time.perf_counter() - opened_at:.2f} s, "
              f"wall time from opening the source. Not a pass/fail bar; none is "
              f"agreed (#79)")
        canvas_w, canvas_h = view.canvas_size
        # The detector is shown the margin canvas exactly as before #46, and
        # the Board past it as bands of their own (#46); imgsz and the net scale
        # are the margin canvas's. ultralytics fits the LONGEST side to imgsz, so
        # that is what must match.
        inner_w, inner_h = view.inner.size
        imgsz = _round32(max(inner_w, inner_h))
        frame_span = board.contour_span(board.find_targets(base)[0][0])
        tpl_span = board.contour_span(board.template_contour(template_mask))
        scale = board.net_scale(view.board_scale, tpl_span, frame_span, imgsz,
                                max(inner_w, inner_h))
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
        if not view.grew:
            print(f"[BOARD] rectified {canvas_w}x{canvas_h}, imgsz {imgsz}, net scale {scale:.2f}")
        else:
            bands = view.exposed_bands(BAND_CONTEXT_PX)
            band_scales = ", ".join(
                f"{x1 - x0}x{y1 - y0} at net scale "
                f"{board.net_scale(view.board_scale, tpl_span, frame_span, _band_imgsz(b.crop), max(x1 - x0, y1 - y0)):.2f}"
                for b in bands for x0, y0, x1, y1 in [b.crop])
            print(f"[BOARD] rectified {canvas_w}x{canvas_h} to the Board's edge: the margin "
                  f"canvas {inner_w}x{inner_h} at {view.inner.offset}, imgsz {imgsz}, net scale "
                  f"{scale:.2f}, and {len(bands)} band(s) of Board past it: {band_scales} (#46)")
        uncovered = board.uncovered_view(view, (base.shape[1], base.shape[0]))
        if uncovered is None:
            print("[WARN] the camera's view does not map onto the Board plane; "
                  "how much of it is off the canvas is unknown (#41)")
        # Any reach past the canvas warns; uncovered_view already drops rounding.
        elif any(uncovered[1].values()):
            outside, reach = uncovered
            span = board.target_span(view)
            # Past a found edge the reach is Board; elsewhere it is the view (#46).
            found = lambda k: ("Board, to its edge" if view.edges[k] is not None
                               else "view, no edge found")
            where = ", ".join(f"{v / span:.2f} {k} ({found(k)})"
                              for k, v in reach.items() if v)
            print(f"[WARN] {outside:.1%} of the camera's view is off the canvas short of "
                  f"any Board edge found, up to {where} (Target spans). Board there is "
                  f"never searched: a Bullet Hole on it is a miss no setting can recover "
                  f"(#41, #46)")
        if not 0.5 <= scale <= 1.2:
            print(f"[WARN] net scale {scale:.2f} is outside the measured working band "
                  f"(0.5-1.2, flat within it); detection is zero by ~1.8")
        registration = Registration(view, base, template_mask, source.when)
        loop = cls(source, model, view, base, imgsz, conf, registration, device)
        loop.net_scale = scale
        return loop

    @property
    def last(self):
        """The most recently registered view (`Registration.last`)."""
        return self.registration.last

    @property
    def processed(self):
        """Frames passed, looked at or not: the source's `passed`."""
        return self.source.passed

    def frames_until(self, end):
        """How many frames of a Recording lie between `--start` and `end` seconds."""
        return int((end - self.source.start_s) * self.fps)

    def looks(self, n_frames, stride=1, baseline_frames=0):
        """Yield a `Look` per frame looked at, up to `n_frames` from `--start`.

        Frames that failed to register are yielded too, unregistered — see
        `Look`. Iteration stops early when the source runs out, which is why
        callers take `processed` from here rather than assuming `n_frames`.

        The first frame is the one Board space was built from, so it is already
        read and already registered; it is yielded like any other. Each later
        one is read from the source, then handed to `registration`: two calls,
        not one. Which frames are read, under a `stride` (#81) past the first
        `baseline_frames`, is the source's, and so is `processed`: see
        `Recording` and `Stream`. A stream has no end but a stop: SIGINT or
        SIGTERM ends iteration after the look in hand, and callers report as
        at any end.
        """
        self.source.start(n_frames, stride, baseline_frames)
        try:
            first = [Frame(0, self._base)] if n_frames > 0 else []
            for index, frame, wait in itertools.chain(first, iter(self.source.read, None)):
                self.clock.start(wait)   # the frame is in hand: read, decoded, handed over
                current = self.view if index == 0 else self.registration.register(frame, index)
                self.clock.lap("registration")
                if current is None:
                    self.lost += 1
                    yield Look(index, None, None, None)
                    continue
                canvas = current.rectify(frame)
                inner = current.rectify_inner(frame) if self.bands else canvas
                self.clock.lap("rectification")
                detections = (self._detect_grown(current, canvas, inner) if self.bands
                              else self._call_detector(canvas, self.imgsz))
                self.clock.lap("detector")
                yield Look(index, current, canvas, detections, inner)
        finally:
            try:
                self.registration.report()   # before the source's, the live report
            finally:
                self.source.close()   # whatever the report did: it restores the signals

    def _call_detector(self, image, imgsz):
        """`_detect` on the loop's device, timed as one detector call (#129)."""
        began = time.perf_counter()
        found = _detect(self.model, image, imgsz, self.conf, self.device)
        self.clock.calls.append(time.perf_counter() - began)
        return found

    def _detect_grown(self, view, canvas, inner):
        """Inference A on the margin canvas, B on each band, merged in canvas px."""
        a = self._call_detector(inner, self.imgsz).astype(np.float64)
        a[:, :2] += view.inner.offset
        hits = []
        for band in self.bands:
            x0, y0, x1, y1 = band.crop
            found = self._call_detector(canvas[y0:y1, x0:x1],
                                        _band_imgsz(band.crop)).astype(np.float64)
            found[:, :2] += (x0, y0)
            hits.append((band, found))
        return merge_band_detections(a, hits, view.match_radius)


class Run(NamedTuple):
    """What a run found, and the evidence needed to attribute what it got wrong.

    The baseline and the residual leave `process` for the same reason the
    `[REGISTRATION]` line is printed: a false positive sitting on a pre-existing
    mark is registration displacement, not a detector error, and nothing
    downstream can tell those apart without the marks that were already on the
    Board. Board space, all three — `baseline` is directly comparable with
    `holes[i]["pos"]`. `lost` and `reanchors` are the Lost Looks past the
    baseline and the re-anchor attempts, as the end-of-run lines count them:
    what tells a Board move never noticed from one lost and recovered (#165).
    """
    holes: list
    baseline: np.ndarray   # pre-existing marks, (cx, cy, w, h)
    residual: np.ndarray   # distance from a suppressed detection to its mark
    lost: int
    reanchors: int


# The stride a live 25 fps stream is looked at with (ADR-0007, #82): the
# slowest per-frame time on record on the development Mac, 646 ms on CamB,
# times 25, rounded up. Measured to lose no true Bullet Hole on the spent truth
# recordings. A count of frames, so it holds only at 25 fps; on another live
# host, re-derive it from the time per look measured there.
LIVE_STRIDE = 17           # PROVISIONAL

# The frame rate a stream is taken to run at (#83): the AXIS Q6315-LE is set to
# a constant 25 fps (#85), the rate PERSIST_FRAMES, BASELINE_FRAMES and
# LIVE_STRIDE are counted at (ADR-0007). Not read off the stream, whose
# reported rate is unreliable; a live run reports the rate its timestamps
# measure beside it (#117), and indexes frames by them at this rate.
LIVE_FPS = 25

# How long opening a stream, or a read on it, may take before it fails (#84):
# a connection that stays open but delivers no frame is then a drop, recovered
# from like any other. Through VideoService's multicast ingest a silent camera
# need not close the RTSP session. Five keyframe intervals (GOP 25 at 25 fps,
# #85), with network slack; not tuned on a live stream.
STREAM_TIMEOUT_MS = 5000   # PROVISIONAL

# The wait before each reopen of a dropped stream, for as long as the run goes
# on (#84). An attempt that opens a silent stream, or cannot reach the host,
# fails only after STREAM_TIMEOUT_MS on top, so attempts then fall ~6 s apart.
RECONNECT_EVERY_S = 1.0


def add_stride_flag(parser):
    """The `--stride` flag, identical in every tool that runs `process`."""
    def stride(text):
        n = int(text)
        if n < 1:
            raise argparse.ArgumentTypeError("a stride is 1 frame or more")
        # From PERSIST_FRAMES on, a window holds one look and any single
        # sighting persists at 1/1: persistence would filter nothing.
        if n >= PERSIST_FRAMES:
            raise argparse.ArgumentTypeError(
                f"a stride under the {PERSIST_FRAMES}-frame persistence window, so "
                f"each window holds more than one look")
        return n
    parser.add_argument("--stride", type=stride, default=None,
                        help="look at every Nth frame past the baseline; the "
                             "rest are gaps for persistence (#81). The baseline "
                             "is still its first --baseline-frames consecutive "
                             "frames. 1, the default on a recording, looks at "
                             f"every frame; on a stream it is {LIVE_STRIDE} "
                             f"(ADR-0007). It must be under {PERSIST_FRAMES}, the "
                             "persistence window.")


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
            out_video=None, mm_per_tpl_px=None, template_path=board.DEFAULT_TEMPLATE,
            require_change_evidence=REQUIRE_CHANGE_EVIDENCE,
            merge_displaced=NON_COOCCURRENCE_MERGE,
            baseline_frames=BASELINE_FRAMES, stride=None, publish=None, ref_time=None,
            timing=None, device=None, opener=None):
    """`video` is a recording's path, or a stream's rtsp:// URL (#83), which
    has no `start` or `end`: it runs until stopped, at `LIVE_STRIDE` unless
    `stride` says otherwise, and prints each Bullet Hole as it is confirmed.

    `publish`, when given, is handed each Confirmed Bullet Hole once, as a
    `BulletHoleConfirmed` (#155): a Stream's as it is announced, a
    Recording's after the end-of-run report has measured it, in first-frame
    order. Without it nothing is published. `ref_time` is a Recording's wall
    clock at its t=0 (`Recording`).

    `timing`, a path, times each Look past the baseline (#129): a CSV row a
    Look there, and n/P50/P95/P99/max printed at the end (`_report_timing`).
    Without it nothing is written, printed or kept. `device` is the
    detector's for every call (`_detect`). `opener` opens the source
    (`RegisteredFrames`): the scoring tool's moved Recording comes in this
    way (#164)."""
    if timing:
        open(timing, "w").close()   # a path it cannot write fails now, not after the run
    loop = RegisteredFrames.open(video, start, model_path, conf, template_path, ref_time,
                                 device, opener)
    fps, match_px = loop.fps, loop.view.match_radius
    n_frames = math.inf if loop.live else loop.frames_until(end)
    stride = stride or (LIVE_STRIDE if loop.live else 1)
    baseline_frames = max(1, baseline_frames)  # 0 or less would mean no baseline at all
    # The stride starts past the baseline, never inside it: built from frames
    # 0, 13, 26... it would span seconds, and a Hit landing in them would be
    # absorbed and never reported (#81).
    looks = loop.looks(n_frames, stride, baseline_frames)

    # The baseline is built from BASELINE_FRAMES frames, not one. Everything it
    # fails to see is reported as a new Bullet Hole, and a single frame passes
    # its own misses straight through. These frames contribute no persistence
    # evidence: within the baseline window nothing can be new, which is exactly
    # the risk the constant documents.
    #
    # They come off the front of the same iterator the run continues on, so the
    # baseline cannot be built from a differently rectified Board than the one
    # it is subtracted from.
    baseline_canvas, baseline_inner, baseline_detections = None, None, []
    # Frame index -> the view detection used, for `_render`. Seeded with look
    # 0's view, Board space itself, so a run that reads no frame still has one.
    # Kept only for `--out`: nothing else reads it, and a view a frame adds up.
    views = {0: loop.view}
    for look in itertools.islice(looks, baseline_frames):
        if not look.registered:
            continue
        if out_video:
            views[look.index] = look.view
        if baseline_canvas is None:
            # Always look 0's: Board space is built from that frame, so `open`
            # has already raised if it did not register. This is the image
            # change detection is measured against for the rest of the run —
            # on the margin canvas, and on the Board grown past it (#46).
            baseline_canvas, baseline_inner = look.canvas, look.inner
        baseline_detections.append(look.detections)
    baseline = baseline_marks(baseline_detections, match_px)
    short = ("" if len(baseline_detections) == baseline_frames else
             f" (of {baseline_frames} requested; the rest were lost or unread)")
    print(f"[INFO] baseline: {len(baseline)} Baseline Marks over "
          f"{len(baseline_detections)} frame(s) from "
          f"{loop.when(0) if loop.live else f'{start}s'}{short}")

    # ponytail: a live run still keeps every look's index, time and
    # residuals, and every candidate, for the end-of-run report: a few MB an
    # hour (#83). Keep only the persistence window and running totals if a
    # Range ever runs for days.
    corroboration, residuals_per_frame = [], []
    timed = [] if timing else None   # a row a Look, kept only when asked for (#129)
    persistence = Persistence(match_px, unseen=loop.source.unseen)
    announce = (_Announcer(loop, persistence, corroboration, require_change_evidence,
                           mm_per_tpl_px, publish) if loop.live else None)
    for look in looks:
        pts, corroborating = None, []   # None: Lost, no evidence, but it counts towards the floor
        if look.registered:
            if out_video:
                views[look.index] = look.view
            pts, matched = strip_pre_existing(look.detections, baseline, match_px)
            residuals_per_frame.append(matched)
            loop.clock.lap("baseline strip")
            if len(pts):
                evidence = change_evidence(
                    pts[:, :2], look.view,
                    lambda: board.changed_regions(baseline_inner, look.inner),
                    lambda: board.changed_regions(baseline_canvas, look.canvas), match_px / 2)
                corroborating = [p for p, seen in zip(pts, evidence) if seen]
                corroboration += corroborating
            loop.clock.lap("change filter")
        persisted_now = persistence.add(look.index, pts)  # empty is meaningful: looked, saw nothing
        # The Look's clock stops once Persistence has taken it: the announcer's
        # Change Evidence check and print fall outside it, as a recording's
        # end-of-run check does (#129).
        loop.clock.lap("persistence")
        if timed is not None:
            timed.append(_timing_row(look, loop.clock))
        if announce:
            announce(persisted_now, corroborating)

    processed = loop.processed
    if persistence.lost:
        print(f"[WARN] Board lost on {len(persistence.lost)} frame(s); excluded from "
              f"persistence, and a window mostly lost confirms nothing (#110)")

    # A short read is not a crash. The interpreter is alive, the window is simply
    # shorter than asked for, and the frames never read must not lengthen the
    # persistence horizon: a candidate whose window runs past where reading
    # stopped is unconfirmable, exactly as one running past --end is. A stream
    # has no end to fall short of.
    if not loop.live and processed < n_frames:
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

    # Refreshed in place, announced ones too. Live it judges nothing new, the last
    # `add` having passed `processed` frames: the count is announced plus waiting.
    persisted = persistence.end(processed)
    if announce:
        # What was announced, no more and no less (ADR-0004).
        new = sorted(announce.announced, key=lambda h: h["first_frame"])
    else:
        new = persisted
        for hole in new:
            hole["corroborated"] = _corroborates(corroboration, hole["box"], match_px)
        if require_change_evidence:
            new = [h for h in new if h["corroborated"]]
    for hole in new:
        hole["target"] = loop.last.assign(hole["pos"])
    if require_change_evidence:
        print(f"[FILTER] change evidence required: {len(persisted)} -> {len(new)} Bullet Holes")

    if merge_displaced:
        new, merged = merge_displaced_tracks(new, loop.last)
        for survivor, absorbed in merged:
            print(f"[MERGE] displaced sighting at t="
                  f"{loop.when(absorbed['first_frame'])} folded into the Bullet Hole "
                  f"at t={loop.when(survivor['first_frame'])} "
                  f"({float(np.linalg.norm(absorbed['pos'] - survivor['pos'])):.0f} Board px, "
                  f"never co-occurring)")
        if not merged:
            print("[MERGE] no displaced sightings found")

    print("[INFO] stride 1: every frame looked at" if stride == 1 else
          f"[INFO] stride {stride}: past the baseline, every {stride}th frame looked "
          f"at; the frames between are gaps, counting neither for nor against a "
          f"Bullet Hole (#81)")
    _report(new, baseline, loop.when, loop.last, mm_per_tpl_px, persistence.looked_at)
    if timed is not None:
        _report_timing(timing, timed, loop.model)
    if publish and not loop.live:
        for hole in new:   # in first-frame order, as `Persistence.end` gave them
            publish(_confirmed(hole, loop.last, loop.wall_clock))
    if out_video:
        _render(video, start, processed, fps, views, baseline, new, out_video,
                stride, baseline_frames)
    return Run(new, baseline, residuals, len(persistence.lost), loop.registration.reanchors)


# A Look's stages, in order (#129). Each runs from the boundary before it, so
# they add up to its Look Time.
STAGES = ("registration", "rectification", "detector", "baseline strip", "change filter",
          "persistence")
# A row's times, in ms, each its own CSV column. Frame Wait is live only: a
# Recording's is empty (#130).
TIMES = ("look", "inference", *STAGES, "frame wait")

# Said wherever Frame Wait shows (#130), so a small one is never read as a
# small delay from the camera.
FRAME_WAIT_EXCLUDES = ("Frame Wait is only the wait inside the system, from the reader "
                       "having the frame decoded to the loop taking it. It excludes "
                       "FFmpeg's buffering, the reader's lag behind the stream, MediaMTX, "
                       "the network and the camera: end-to-end latency (SOW 2.3.4), not "
                       "measured here")


class _Timed(NamedTuple):
    """A Look's timing (#129): `ms` its times by `TIMES`, `calls` each
    detector call's, all in ms."""
    index: int
    registered: bool
    ms: dict
    calls: list


def _timing_row(look, clock):
    """A Look's `_Timed`. A stage the Look never reached is None, as is a
    Lost Look's Inference Time: past registration it reached nothing, and no
    detector ran, so the Looks it is taken over are those that did."""
    ms = {"look": clock.elapsed * 1000,
          "inference": sum(clock.calls) * 1000 if look.registered else None,
          "frame wait": None if clock.wait is None else clock.wait * 1000,
          **{s: clock.stages[s] * 1000 for s in clock.stages}}
    return _Timed(look.index, look.registered, ms, [c * 1000 for c in clock.calls])


def _percentiles(ms):
    """n beside every percentile, so a P99 of a few Looks is read as one."""
    if not ms:
        return "n 0"
    p50, p95, p99 = np.percentile(ms, (50, 95, 99))
    return f"n {len(ms)}  P50 {p50:.1f}  P95 {p95:.1f}  P99 {p99:.1f}  max {max(ms):.1f} ms"


def _report_timing(path, rows, model):
    """`rows`, `_Timed` each, written to `path` as CSV and their n, P50, P95,
    P99 and max printed (#129). A measurement on whatever host ran it,
    compared with nothing: what the 40 ms of SOW 2.3.1 measures is not agreed
    (#128). The file's first line, a `#` comment, says so as the printed
    header does, so a copy passed on alone says where it was measured.

    The device is the one the detector resolved to, whatever was asked for:
    ultralytics' predictor's, which it sets up on the first call.

    A live run's Frame Wait gets a line of its own, and the file a second
    comment, each saying what it excludes (#130)."""
    device = getattr(getattr(model, "predictor", None), "device", None) or "no device: no call"
    header = (f"WIP, not an acceptance result: {len(rows)} Look(s) past the baseline on "
              f"{platform.node()} ({platform.platform()}), the detector on {device}. Compared "
              f"with no bar: what SOW 2.3.1 measures is not agreed (#128)")
    waits = [r.ms["frame wait"] for r in rows if r.ms["frame wait"] is not None]
    cell = lambda v: "" if v is None else f"{v:.3f}"
    width = max((len(r.calls) for r in rows), default=0)
    with open(path, "w", newline="") as f:
        f.write(f"# {header}\n")
        if waits:
            f.write(f"# {FRAME_WAIT_EXCLUDES}\n")
        out = csv.writer(f)
        out.writerow(["frame", "registered", *(f"{t.replace(' ', '_')}_ms" for t in TIMES),
                      *(f"call_{i}_ms" for i in range(1, width + 1))])
        for r in rows:
            out.writerow([r.index, int(r.registered), *(cell(r.ms.get(t)) for t in TIMES),
                          *map(cell, r.calls), *[""] * (width - len(r.calls))])
    print(f"[TIMING] {header}")
    figures = {"Inference Time": "inference", "Look Time": "look", **{s: s for s in STAGES}}
    for name, key in figures.items():
        print(f"[TIMING] {name:<16} "
              f"{_percentiles([r.ms[key] for r in rows if r.ms.get(key) is not None])}")
    print(f"[TIMING] {'a detector call':<16} "
          f"{_percentiles([c for r in rows for c in r.calls])}")
    if waits:
        print(f"[TIMING] {'Frame Wait':<16} {_percentiles(waits)}. {FRAME_WAIT_EXCLUDES}")
    print(f"[TIMING] -> {path}")


class _Announcer:
    """Prints each Bullet Hole of a live run once, as soon as it is Confirmed
    (#83): persisted, by `Persistence`, and corroborated by Change Evidence.

    Called after every Look with the Candidates that persisted at it and the
    Detections Change Evidence saw on it. A newly persisted one is checked
    against every Detection corroborated so far (`corroboration`, `process`'s
    list), at its position then. With Change Evidence required, one it does
    not corroborate waits, and is checked against each later Look's, at its
    Candidate's position at that Look (ADR-0003, amended 2026-10-11).

    `announced` is what was printed. The end-of-run report lists these and no
    others, at the positions `Persistence.end` refreshes them to: re-deciding
    at the end, on positions averaged since, could drop one already printed,
    which ADR-0004 rules out. Each is handed to `publish`, when given, right
    after it is printed, as a `BulletHoleConfirmed` at its position then (#155).
    """

    def __init__(self, loop, persistence, corroboration, require_change_evidence,
                 mm_per_tpl_px, publish):
        self.loop, self.persistence, self.corroboration = loop, persistence, corroboration
        self.require, self.mm_per_tpl_px = require_change_evidence, mm_per_tpl_px
        self.publish = publish
        self.waiting, self.announced = [], []

    def __call__(self, persisted, corroborating):
        match_px = self.persistence.match_px
        for hole in self.waiting:
            hole["corroborated"] = _corroborates(corroborating,
                                                 self.persistence.position(hole), match_px)
        for hole in persisted:
            hole["corroborated"] = _corroborates(self.corroboration, hole["box"], match_px)
        waiting = []
        for hole in self.waiting + persisted:
            if self.require and not hole["corroborated"]:
                waiting.append(hole)
                continue
            hole["target"] = self.loop.last.assign(hole["pos"])
            _measure(hole, self.loop.last, self.mm_per_tpl_px)
            print(f"[NEW] {_bullet_hole_line(hole, self.loop.when)}")
            self.announced.append(hole)
            if self.publish:
                self.publish(_confirmed(hole, self.loop.last, self.loop.wall_clock))
        self.waiting = waiting


def _corroborates(points, box, match_px):
    """Did change evidence see any of `points` on this Bullet Hole?"""
    return any(same_bullet_hole(c, box, match_px) for c in points)


def _measure(hole, view, mm_per_tpl_px):
    """Set a Bullet Hole's score and millimetres; return why there are no
    millimetres, if calibration is the reason.

    A Miss has no Target and so no Shot Distance — by definition, not by
    omission. Measuring it against some Target's centre would be a number with
    no meaning. See CONTEXT.md, Miss.
    """
    hole["mm"] = hole["score"] = None
    if hole["target"] is None:
        return None
    # Scoring needs no calibration: it is a ratio inside one picture.
    hole["score"] = board.score([hole["pos"]], view, hole["target"])[0]
    try:
        hole["mm"] = board.to_millimetres([hole["pos"]], view, mm_per_tpl_px,
                                          hole["target"])[0]
    except board.NotCalibrated as why:
        return why
    return None


def _where(hole):
    return "MISS" if hole["target"] is None else f"Target {hole['target'] + 1}"


def _measurement(hole):
    """A measured Bullet Hole's or Baseline Mark's ring score and millimetres,
    as its line ends. On a Target with no millimetres it says so: the end
    report's `[BLOCKED]` line says why."""
    line = "" if hole["score"] is None else (
        "  outside rings" if hole["score"] == board.OUTSIDE_RINGS
        else f"  scores {hole['score']}")
    if hole["mm"] is not None:
        line += f"  X {hole['mm'][0]:+7.1f} mm  Y {hole['mm'][1]:+7.1f} mm"
    elif hole["target"] is not None:
        line += "  (mm unavailable)"
    return line


def _bullet_hole_line(hole, when):
    """A measured Bullet Hole, as the report lists it and a live run announces it."""
    evidence = "changed" if hole["corroborated"] else "model only"
    return (f"t={when(hole['first_frame']):>6}  {_where(hole):<9} "
            f"persistence {hole['persistence']:.0%}  [{evidence}]{_measurement(hole)}")


def _on_target_or_miss(holes):
    """`(n on a Target, m Miss)`, for a count line."""
    misses = sum(1 for h in holes if h["target"] is None)
    return f"({len(holes) - misses} on a Target, {misses} Miss)"


def _report(new, baseline, when, view, mm_per_tpl_px, looked_at):
    """`when(index)` is a looked-at frame's time as printed (`RegisteredFrames.when`).

    The Baseline Marks come first, P1...Pn in `baseline`'s order, each placed
    and measured through `view` as a new Bullet Hole is, so the two lists
    compare directly (#163). Only new Bullet Holes are numbered, and only
    they make Groups."""
    marks = [{"pos": m[:2], "target": view.assign(m[:2])} for m in baseline]
    blocked = [why for why in [_measure(h, view, mm_per_tpl_px) for h in marks + new]
               if why is not None]
    if blocked:
        print(f"[BLOCKED] millimetres unavailable: {blocked[0]}")

    if not marks:
        print("[INFO] no Baseline Marks: the detector saw nothing in the baseline Looks")
    else:
        print(f"[INFO] {len(marks)} Baseline Marks {_on_target_or_miss(marks)}: what the detector "
              f"saw in the baseline Looks, not truth")
    for k, mark in enumerate(marks, 1):
        print(f"  P{k}  {_where(mark):<9}{_measurement(mark)}".rstrip())

    print(f"[INFO] {len(new)} new Bullet Holes {_on_target_or_miss(new)}")
    for i, hole in enumerate(new, 1):
        print(f"  #{i}  {_bullet_hole_line(hole, when)}")

        # Observation facts, not a claim about the mark. A detection ceasing is
        # not evidence that the Bullet Hole ceased: on CamB_20260915_102250 a
        # mark stopped being detected at any confidence from ~4s and stayed
        # plainly visible to the operator until 25s. The Bullet Hole stays
        # confirmed; the operator gets to see that it stopped being seen.
        # Denominator is frames that REGISTERED since first sighting, not frames
        # read: a Board-lost frame neither counts for nor against a Bullet Hole,
        # the same rule `Persistence` applies. Counting
        # reads here would understate detection on a clip with dropouts.
        seen = hole["seen"]
        span = sum(1 for i in looked_at if i >= hole["first_frame"])
        share = f", {len(seen) / span:.0%} of frames since" if span > 0 else ""
        print(f"      first detected: {when(hole['first_frame'])}   "
              f"last detected: {when(max(seen))}   "
              f"detected in {len(seen)} frame(s){share}")

    _report_groups(new, mm_per_tpl_px)


def _report_groups(new, mm_per_tpl_px):
    """One block per Target with new Bullet Holes. Millimetres only: with no
    print scale there is no Group block, never a pixel-unit stand-in."""
    if mm_per_tpl_px is None:
        print("[GROUP] no Group statistics: the print scale is not configured for "
              "this Capture Setup")
        return
    stats, misses = groups.groups(new)
    if misses:
        print(f"[GROUP] {misses} Miss excluded from every Group" if misses == 1 else
              f"[GROUP] {misses} Misses excluded from every Group")
    for target, g in stats.items():
        print(f"[GROUP] Target {target + 1}: {g['n']} Bullet Hole{'s' if g['n'] > 1 else ''}"
              f" (counts Bullet Holes, not Hits: a tight Group can be under-counted, ADR-0001)")
        print(f"      MPI  X {g['mpi'][0]:+7.1f} mm  Y {g['mpi'][1]:+7.1f} mm")
        if g["n"] < 2:
            print("      spread measures need at least two Bullet Holes")
            continue
        print(f"      CEP {g['cep']:.1f} mm (CEP50: median distance from the MPI)   "
              f"Mean Radius {g['mean_radius']:.1f} mm   RMS radius {g['rms_radius']:.1f} mm")
        print(f"      Extreme Spread {g['extreme_spread']:.1f} mm (centre to centre)")


def _render(video, start, n_frames, fps, views, baseline, new, out_video,
            stride=1, baseline_frames=0):
    """Redraw the clip as the rectified Board. Neither detection nor
    registration is repeated: `views` is what detection used, by frame index,
    and a lost frame is drawn with the last view before it.

    A stride's gaps are left out (#81): no fit was made on them, and the last
    look's could be stale by up to a stride. The output then plays faster
    than the clip; each frame's own t stays on it."""
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    view = views[0]  # Board space's own view; `process` always records it
    w, h = view.canvas_size
    vw = cv2.VideoWriter(out_video, cv2.VideoWriter_fourcc(*"avc1"), fps, (w, h))
    for idx in range(n_frames):
        if not _looked_at(idx, stride, baseline_frames):
            if not cap.grab():
                break
            continue
        ok, frame = cap.read()
        if not ok:
            break
        view = views.get(idx, view)
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
        cv2.putText(vis, f"Baseline Marks {len(baseline)}", (16, 66),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 2)
        cv2.putText(vis, f"NEW {shown}", (16, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        vw.write(vis)
    cap.release()
    vw.release()
    print(f"[INFO] -> {out_video}")


if __name__ == "__main__":
    p = argparse.ArgumentParser("Report Bullet Holes that are new since the baseline")
    p.add_argument("video", help="a recording, or a stream's rtsp:// URL, normally a "
                                 "VideoService (MediaMTX) path "
                                 "rtsp://<mtx-host>:8554/<path> (#83)")
    p.add_argument("--start", type=float,
                   help="baseline timestamp, seconds. A recording's only: a stream "
                        "is read from where it is")
    p.add_argument("--end", type=float,
                   help="end of the window, seconds. Allow at least "
                        f"{PERSIST_FRAMES} frames after the last expected Hit: a "
                        "Bullet Hole whose persistence window runs past the end "
                        "is not reported. A recording's only: a stream runs until "
                        "SIGINT or SIGTERM, then reports.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--template", default=board.DEFAULT_TEMPLATE,
                   help="printed Target artwork used to register the Board")
    p.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    p.add_argument("--mm-per-px", type=board.checked_scale, default=None,
                   help="print scale: millimetres per template px on the printed "
                        "Target, measured off its outline (docs/ring_measurement.md), "
                        "not a ruler reading of any ring. Overrides "
                        "config/print_scale.json for this recording's Capture "
                        "Setup; a stream has no Capture Setup on record and takes "
                        "it from here only. Without either, positions stay in Board pixels: "
                        "every millimetre figure scales linearly with this, so "
                        "it is not guessed.")
    p.add_argument("--no-change-filter", action="store_true",
                   help="keep persisted Candidates that change detection did "
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
    add_stride_flag(p)
    p.add_argument("--out", help="write an annotated video of the rectified Board here. "
                                 "A recording's only: it replays the source")
    p.add_argument("--session-id",
                   help="WebApp session UUID; when given, POST each confirmed Bullet Hole "
                        "to POST /sessions/{id}/bullets on the backend")
    p.add_argument("--backend-url", default="http://localhost:8000",
                   help="WebApp backend base URL (default: http://localhost:8000)")
    p.add_argument("--ref-time",
                   help="UTC wall-clock time at the recording's t=0, ISO 8601 "
                        "(e.g. 2026-10-11T10:30:00Z). Derives first_seen_at timestamps. "
                        "Defaults to when the recording is opened. A recording's "
                        "only: a stream's times are its own timestamps")
    p.add_argument("--timing", metavar="PATH",
                   help="time each Look past the baseline: a CSV row a Look here, in ms, "
                        "and n/P50/P95/P99/max printed at the end. A WIP measurement on "
                        "this host, never an acceptance result (#129). On a stream, "
                        f"each Look's Frame Wait too (#130). {FRAME_WAIT_EXCLUDES}")
    p.add_argument("--device",
                   help="the detector's device for every call: cpu, mps, or a CUDA index "
                        "(#129). Without it, its library's default: CUDA if available, "
                        "else CPU, never MPS")
    manifest.add_flag(p)
    a = p.parse_args()
    if _is_stream(a.video):
        if a.start is not None or a.end is not None or a.out:
            p.error("a stream takes no --start, --end or --out: it can be neither "
                    "seeked nor replayed (#83)")
        if a.ref_time:
            p.error("a stream takes no --ref-time: its times are its own "
                    "timestamps (#117, #152)")
        if a.merge_displaced:
            p.error("a stream takes no --merge-displaced: it would fold away Bullet "
                    "Holes already announced (ADR-0004)")
    elif a.start is None or a.end is None:
        p.error("a recording needs --start and --end")
    # Before the gate, so a refused run spends no sealed recording either.
    for flag, out in (("--timing", a.timing), ("--out", a.out)):
        if out and _same_file(out, (a.video, a.model, a.template)):
            p.error(f"{flag} names an input of the run, which writing it would overwrite")
    if a.timing and a.out and _outputs_clash(a.timing, a.out):
        p.error("--timing and --out name the same file: the video would overwrite the CSV")

    # Split membership before anything is opened: a sealed recording is refused
    # unless this run says it is the final one. See manifest.py and ADR-0005.
    # The print scales are checked before the gate too: a malformed one found
    # after it would spend a sealed recording on a run that reports nothing.
    scales = board.print_scales()
    entry = _gate(a.video, a.final_run, a.model)
    scale = a.mm_per_px
    if scale is None and entry is not None:
        scale = scales.get(entry["capture_setup"])
        if scale is not None:
            print(f"[INFO] print scale {scale} mm per template px, configured for "
                  f"{entry['capture_setup']} in config/print_scale.json")

    ref_time = None
    if a.ref_time:
        ref_time = datetime.fromisoformat(a.ref_time.replace("Z", "+00:00"))
        if ref_time.tzinfo is None:
            p.error("--ref-time must include a UTC offset (e.g. 2026-10-11T10:30:00Z or +02:00)")

    # Drained on leaving, after the report and even if the run raised (#155).
    with (webapp.WebAppPublisher(a.session_id, a.backend_url) if a.session_id
          else contextlib.nullcontext()) as publisher:
        process(a.video, a.start, a.end, a.model, a.confidence, a.out, scale,
                a.template, not a.no_change_filter, a.merge_displaced, a.baseline_frames,
                a.stride, publish=publisher.publish if publisher else None,
                ref_time=ref_time, timing=a.timing, device=a.device)
