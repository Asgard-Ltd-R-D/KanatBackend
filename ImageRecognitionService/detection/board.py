"""Board geometry: find it, register it, rectify it, and place Targets in it.

Board space is the coordinate system everything downstream works in. It is the
Target artwork's own pixel grid, scaled so detection runs at the right apparent
size and shifted so the canvas corner is the origin. Two properties make it the
right frame of reference:

- It does not move. The camera drifts ~16px over 12s on real footage, and the
  Board itself moves in wind; Board space absorbs both.
- It is tied to printed artwork, so every Board-space length converts to
  millimetres once the print scale is known — see `to_millimetres`.

**One homography for the whole Board**, with Targets located inside it: the
baseline frame's is fitted to the reference Target's silhouette as an affine
(ADR-0012: the silhouette does not constrain perspective), and every later
frame is registered to the baseline frame on the Board's own texture (#50). This
assumes the Board is a single plane. The sheets are stapled separately and
visibly curl, so the assumption is known to be imperfect; `residuals` exists to
measure what it costs if SOW 2.3.2's 5mm proves unreachable. The alternative is
one homography per Target, which absorbs curl a Board-level fit cannot.
"""
import functools
import json
import math
import os
from typing import NamedTuple

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ImageRecognitionService/
DEFAULT_TEMPLATE = os.path.join(BASE_DIR, "data", "targets", "kanat_silhouette_a4.png")
PRINT_SCALE_PATH = os.path.join(BASE_DIR, "config", "print_scale.json")

# --- Target artwork landmarks, measured on the source PNG -------------------
# Readings off the artwork, not tuning knobs.
RING_CENTRE_TPL = np.array([695.4, 639.2])  # white 10-ring centre, template px
# White 10-ring diameter, template px: twice the median radius of its edge, at
# half level, over 720 rays (`tools/ring_landmarks.py`, #70). The disk is ~2%
# taller than wide (221.1 x 224.6). 227 until #70, which was 1-3 px outside it.
RING_DIAMETER_TPL = 223.0

# Outer radius of each scoring ring, template px. The 10-ring ends at the white
# disk's edge. Each ring after it ends at the centre of the white line, the
# median over 720 rays from the ring centre (`tools/ring_landmarks.py`, #70).
# The rings are ~2% taller than wide, so one radius is off by up to ±1.4 px at
# the 10-ring and ±5 px at the 7-ring.
# ponytail: circular rings, well under the 7-8 px registration error (#50);
# score an ellipse (one y/x aspect, ~1.022) if registration gets that good.
RING_RADII_TPL = (RING_DIAMETER_TPL / 2, 220.5, 322.4, 425.1, 528.2)
RING_SCORES = (10, 9, 8, 7, 6)
OUTSIDE_RINGS = 0          # on the Target, beyond the 6-ring

# --- Provisional working values --------------------------------------------
# NONE of these are validated. They were set by hand against a single clip
# (CamA_20260914_141546) and fixed before the sealed run, which evaluated them
# once (#31); sealing is gone since (ADR-0010). Every number below is a
# starting point, not a requirement. See docs/adr/0003-a-bullet-hole-is-new-when-it-persists.md.

GREEN_LO = (35, 40, 30)    # PROVISIONAL: hue gate for the printed Target
GREEN_HI = (95, 255, 255)  # PROVISIONAL: one artwork, one lighting condition
MIN_TARGET_AREA_PX = 5000  # PROVISIONAL: rejects specks, may reject distant Targets

# Apparent size at which the detector actually works.
#
# What reproduces: upscaling past ~1.8 gives ZERO detections, at three canvas
# resolutions an octave apart. That ceiling is solid and is why nothing here
# upscales.
#
# What does NOT reproduce: a sharp optimum. On a single-Target crop yield peaked
# at 0.86 and halved by 1.04; on the full Board canvas the same sweep is flat —
# 14 detections at 0.53, 16 at 0.70, 14 at 0.89, 12 at 1.12. Anywhere in 0.5-1.1
# is defensible on the evidence available, and the difference between them is
# within single-frame noise.
#
# So this value is inside a flat band, not on a measured peak. Another sweep of
# one clip will not settle it, and the sealed run only tests the value fixed
# before it (ADR-0005).
TARGET_NET_SCALE = 0.90    # PROVISIONAL

# Two detections are the same Bullet Hole within this many template px. Expressed
# in template px precisely so it survives a change of camera distance, unlike a
# frame-pixel value. It converts to millimetres with the print scale, as
# `to_millimetres` does.
#
# Swept against data/truth/cama-20260914-141546 (6 Bullet Holes): 40 scores
# 5 true / 1 false / 1 missed, 20 scores 6 / 1 / 0. The radius also gates
# which detections count as "already in the baseline", so an over-wide value
# discards real Bullet Holes near a pre-existing one — which is how 40 lost a
# Bullet Hole 125 template px clear of its neighbour.
MATCH_TPL_PX = 20.0        # PROVISIONAL

# Deliberately loose. Change detection only ever ADDS confidence to a detection
# the model already made, so a false "changed" costs nothing while a missed one
# wastes the channel. At 2.5 it produced a single component across a whole Board
# and the evidence was dead.
ABSDIFF_SIGMA = 2.0        # PROVISIONAL: change-detection gate, evidence only

# How far past the Targets the rectified Board extends, as a fraction of the
# Target spread: the canvas `BoardView.rectify` draws, for `--out` and the
# negatives miner. The detector never sees it; it sees the Target Sheets.
BOARD_MARGIN = 0.50

# The Target Sheets (ADR-0011): detection runs only on each sheet, the
# `sheet_tpl_px` rectangle config/print_scale.json holds (#271), grown by this
# bound. A Detection beyond every sheet's bound is dropped.
SHEET_BOUND_MM = 5.0
# Board px of context round each bound on its sheet canvas. At least the
# canvas-shift control's largest shift (#272), so a shifted run still sees the
# whole bound. Picked by #275's bench.
SHEET_CONTEXT_PX = 32      # PROVISIONAL


# Registration after the baseline frame (#50): ECC on the greyscale Target
# Sheets (`texture_region`), fitted at this fraction of the frame's resolution.
ECC_SCALE = 0.5            # PROVISIONAL: half resolution
ECC_CROP_MARGIN = 64       # frame px round the region: room for the camera drift

# ECC's stopping rule for tracking (#274). On many frames ECC flips between two
# near-identical warps every iteration, so the old 200 / 1e-6 ran to the cap:
# CamB's slow mode and CamA's 3 s spikes. Measured 2026-10-29 at stride 1
# against 200 / 1e-6, docs/latency_wip.md "ECC's stopping rule": registration
# P50 646 -> 24 ms on CamB, P99 2950 -> 85 on CamA; correlation within 4e-4;
# the regression bench passes. Not swept.
ECC_MAX_ITERATIONS = 20    # PROVISIONAL
ECC_EPS = 1e-3             # PROVISIONAL

# A re-anchor (#80) is seeded from every Target in view and keeps the best fit,
# and only above this. The Targets share one artwork, so a neighbour's seed can
# converge one Target over. Measured 2026-10-05 seeding every contour against
# the baseline, four CamA/CamB clips: the right Target 0.97-0.99, a neighbour
# 0.55 (182 frame px off) and 0.20, or no convergence. Not swept.
REANCHOR_MIN_CORRELATION = 0.9   # PROVISIONAL


class NotCalibrated(RuntimeError):
    """Raised when a physical measurement is requested before calibration."""


def _as_matrix(scale, offset=(0.0, 0.0)):
    return np.array([[scale, 0.0, offset[0]],
                     [0.0, scale, offset[1]],
                     [0.0, 0.0, 1.0]], np.float32)


def apply(matrix, points):
    pts = np.asarray(points, np.float32).reshape(-1, 1, 2)
    if not len(pts):
        return np.zeros((0, 2), np.float32)
    return cv2.perspectiveTransform(pts, matrix.astype(np.float32)).reshape(-1, 2)


def find_targets(frame, min_area=MIN_TARGET_AREA_PX):
    """Every printed Target visible in `frame`, largest first, plus the mask.

    One hue threshold does this: the artwork is saturated green against paper,
    dirt and plywood. No model is involved, and none is needed.
    """
    mask = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), GREEN_LO, GREEN_HI)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    keep = [c for c in contours if cv2.contourArea(c) >= min_area]
    return sorted(keep, key=cv2.contourArea, reverse=True), mask


def template_contour(template_mask):
    contours, _ = cv2.findContours(template_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return max(contours, key=cv2.contourArea)


def contour_span(contour):
    """Longest bounding-box edge — the span both scale calculations compare."""
    _, _, w, h = cv2.boundingRect(contour)
    return float(max(w, h))


def spread(points):
    """Longest side of the points' bounding box — the Target span
    `BOARD_MARGIN` measures in."""
    return float(np.ptp(np.asarray(points).reshape(-1, 2), axis=0).max())


def _blurred(mask):
    return cv2.GaussianBlur(mask.astype(np.float32) / 255, (21, 21), 0)


def box_seed(source_contour, reference_contour):
    """Homography taking one contour's bounding box onto another's."""
    def corners(contour):
        x, y, w, h = cv2.boundingRect(contour)
        return np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
    return cv2.getPerspectiveTransform(corners(source_contour), corners(reference_contour))


def register(template_mask, frame_mask, reference_contour, init=None,
             motion=cv2.MOTION_HOMOGRAPHY):
    """Homography mapping template coordinates onto the frame; with
    `motion=cv2.MOTION_AFFINE` its perspective row is fixed at (0, 0, 1).

    Bounding-box correspondence for an initial guess, then ECC refinement on the
    blurred masks. Feature matching (SIFT/ORB) is not used and does not work
    here: the artwork is flat colour with thin rings, giving ~132 keypoints and a
    degenerate homography that collapses to a sliver.

    Returns `(H, correlation)`. Raises `cv2.error` if ECC fails to converge, which
    callers must treat as "this frame is no evidence" rather than as a position.
    """
    if init is None:
        init = box_seed(template_contour(template_mask), reference_contour)
    rows = 3 if motion == cv2.MOTION_HOMOGRAPHY else 2
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    correlation, H = cv2.findTransformECC(
        _blurred(template_mask), _blurred(frame_mask),
        (init if rows == 3 else init[:2] / init[2, 2]).astype(np.float32), motion, criteria, None, 5)
    return (H if rows == 3 else np.vstack([H, [0, 0, 1]]).astype(np.float32)), correlation


# --- Board space on the printed interior (#302) ------------------------------
# The silhouette's edge is not the artwork's on either camera (#297): CamA's
# GREEN_HI cuts the blue-shifted rim (+3.3%), CamB's green spills into the
# paper (-2 to -3.5%, centre 1.5-3 mm off). Two edge-free readings correct it:
# the white disk's own centre, where opposite rays balance, and the scale that
# maps the artwork's digit row (6 7 8 9 | 9 8 7 6) onto the frame's, read
# centre to centre. Both on a template-space patch round the ring at
# `_PATCH_K` px per template px.
_PATCH_K = 0.5
_PATCH_HALF = np.array([600.0, 200.0])          # template px round the ring
_PATCH_ORIGIN = RING_CENTRE_TPL - _PATCH_HALF
_DISK_RAYS = np.radians(np.arange(0, 360, 10))
_DISK_MIN_RAYS = 24       # of 36: a third may be a Bullet Hole or an occluder
_DISK_RAY_TOL = 6.0       # template px; clean disks' rays sit within ~5.6 (ellipse, noise)
_DISK_ITERATIONS = 20
_DIGIT_XS = np.arange(-560, 560, 1.0)            # template px along the row
_DIGIT_ZONE = (np.abs(_DIGIT_XS) > 140) & (np.abs(_DIGIT_XS) < 520)  # digits only
_DIGIT_BAND = np.arange(-16, 17, 2.0)            # template px across it
_DIGIT_SCALES = np.arange(0.80, 1.15, 0.0025)
_DIGIT_SHIFTS = np.arange(-24, 24.5, 1.0)
# Below this correlation on either half of the digit row the plain
# silhouette fit stands (#302). The five truth baselines read 0.68-0.93 a half;
# a half covered by an occluder 0.00-0.52, where the other half alone fits
# scales 2-4% wrong. Set between the two, not swept.
INTERIOR_MIN_CORRELATION = 0.6   # PROVISIONAL


def _patch(image, H):
    """`image` (the frame H maps the template onto; the template for an
    identity H) on the template-space patch round the ring, greyscale float."""
    k = _PATCH_K
    P = np.array([[k, 0, -_PATCH_ORIGIN[0] * k], [0, k, -_PATCH_ORIGIN[1] * k], [0, 0, 1]])
    size = tuple(int(v) for v in 2 * _PATCH_HALF * k)
    flags = cv2.INTER_AREA if H is None else cv2.INTER_CUBIC
    M = P if H is None else P @ np.linalg.inv(H)
    out = cv2.warpPerspective(image, M, size, flags=flags, borderValue=(255, 255, 255))
    return cv2.cvtColor(out, cv2.COLOR_BGR2GRAY).astype(np.float32)


def _sample(g, x, y):
    """`g` (a `_patch`) at template-px points."""
    to = lambda v, o: ((v - o) * _PATCH_K).astype(np.float32)
    return cv2.remap(g, to(x, _PATCH_ORIGIN[0]), to(y, _PATCH_ORIGIN[1]), cv2.INTER_LINEAR)


def disk_centre(g):
    """The white disk's own centre on a `_patch`, template px, or None when
    the disk is no evidence (#302).

    Each ray's half-level edge; a circle fitted to them, rays more than
    `_DISK_RAY_TOL` off it dropped (a Bullet Hole on the edge, something in
    front of the disk), refitted; repeated from the new centre until it
    moves under 0.05 px. None when fewer than `_DISK_MIN_RAYS` rays are kept
    or it does not settle in `_DISK_ITERATIONS`."""
    g = cv2.GaussianBlur(g, (0, 0), 1)
    rs = np.arange(60, 170, 0.5)
    c = RING_CENTRE_TPL.copy()
    for _ in range(_DISK_ITERATIONS):
        profiles = _sample(g, c[0] + np.outer(np.cos(_DISK_RAYS), rs),
                           c[1] + np.outer(np.sin(_DISK_RAYS), rs))
        radii, angles = [], []
        for p, a in zip(profiles, _DISK_RAYS):
            half = (np.percentile(p[:60], 75) + np.median(p[-40:])) / 2
            below = np.flatnonzero(p < half)
            if not len(below) or below[0] == 0:
                continue
            i = below[0]
            radii.append(rs[i - 1] + (p[i - 1] - half) / (p[i - 1] - p[i]) * 0.5)
            angles.append(a)
        if len(radii) < _DISK_MIN_RAYS:
            return None
        r, a = np.array(radii), np.array(angles)
        # r = R + dx cos a + dy sin a, to first order in the centre's error
        X = np.column_stack([np.ones_like(a), np.cos(a), np.sin(a)])
        keep = np.ones(len(r), bool)
        for _ in range(3):
            fit = np.linalg.lstsq(X[keep], r[keep], rcond=None)[0]
            keep = np.abs(r - X @ fit) <= _DISK_RAY_TOL
        if keep.sum() < _DISK_MIN_RAYS:
            return None
        fit = np.linalg.lstsq(X[keep], r[keep], rcond=None)[0]
        c = c + fit[1:]
        if np.hypot(*fit[1:]) < 0.05:
            return c
    return None


def _digit_profile(g, c, blur=0.0):
    """High-passed luma along the digit row through `c`, one sample per
    template px, averaged across `_DIGIT_BAND`, blurred by `blur` template px."""
    p = _sample(g, np.tile(c[0] + _DIGIT_XS, (len(_DIGIT_BAND), 1)),
                np.repeat(c[1] + _DIGIT_BAND, len(_DIGIT_XS)).reshape(len(_DIGIT_BAND), -1))
    p = p.mean(axis=0)[None]
    if blur:
        p = cv2.GaussianBlur(p, (0, 0), blur)
    return (p - cv2.GaussianBlur(p, (0, 0), 40))[0]


def digit_scale(frame_profile, template_profile):
    """`(scale, correlation)`: the scale s about the row's centre, with the
    best shift, under which the frame's profile at s x reads the template's
    at x, by grid search. The correlation is the weaker half's at that fit
    (6 7 8 9 left, 9 8 7 6 right): a half hidden behind something reads
    0.0-0.52, and the other half alone can fit a wrong scale (#302)."""
    def corr(q, a):
        q, a = q - q.mean(axis=-1, keepdims=True), a - a.mean()
        return (q @ a) / np.maximum(np.linalg.norm(q, axis=-1) * np.linalg.norm(a), 1e-9)
    xs, a = _DIGIT_XS[_DIGIT_ZONE], template_profile[_DIGIT_ZONE]
    best = -2.0, 1.0, 0.0
    for s in _DIGIT_SCALES:
        r = corr(np.interp(s * xs + _DIGIT_SHIFTS[:, None], _DIGIT_XS, frame_profile), a)
        if r.max() > best[0]:
            best = float(r.max()), float(s), float(_DIGIT_SHIFTS[r.argmax()])
    _, s, dx = best
    q = np.interp(s * xs + dx, _DIGIT_XS, frame_profile)
    return s, float(min(corr(q[side], a[side]) for side in (xs < 0, xs > 0)))


@functools.cache
def _artwork():
    """The artwork's `_patch` and its disk centre."""
    g = _patch(cv2.imread(DEFAULT_TEMPLATE), None)
    return g, disk_centre(g)


def interior_fit(frame, H):
    """`(A, correlation)`: the template -> template similarity about the ring
    that `H @ A` corrects the silhouette fit `H` by (#302), and the digit
    row's weaker half's correlation. A is None, keep `H`, when the disk is
    no evidence (`disk_centre`) or that correlation is below
    `INTERIOR_MIN_CORRELATION`.

    A puts the artwork's disk centre on the frame's and scales by the digit
    row, both axes alike: the row reads the horizontal scale only.
    ponytail: one isotropic scale; read a vertical ruler too if dY ever
    carries a scale error dX does not."""
    g = _patch(frame, H)
    c = disk_centre(g)
    if c is None:
        return None, None
    art, art_c = _artwork()
    frame_px = math.sqrt(abs(np.linalg.det(H[:2, :2])))   # frame px per template px, affine H
    s, correlation = digit_scale(_digit_profile(g, c), _digit_profile(art, art_c, 1.0 / frame_px))
    if correlation < INTERIOR_MIN_CORRELATION:
        return None, correlation
    A = np.array([[s, 0, c[0] - s * art_c[0]], [0, s, c[1] - s * art_c[1]], [0, 0, 1]])
    return A, correlation


def ecc_warp(ref, cur, motion, init, mask=None):
    """`(W, correlation)`: the 3x3 warp taking `ref` frame coordinates onto
    `cur`'s, by ECC at `ECC_SCALE`, seeded with `init` (same convention), over
    `mask`'s nonzero pixels of `ref` (all when None). Raises `cv2.error` when
    ECC does not converge.

    The mask goes to ECC as its mask. Multiplied into both images instead, its
    fixed edge would pull W towards no motion. ECC reads its mask in `cur`'s
    coordinates, so the region is first carried there by `init`; left in
    `ref`'s, background at its leading edge votes as the camera moves.

    ECC works over the whole image and masks afterwards, so both images are
    first cropped to the box round the mask in both frames plus
    `ECC_CROP_MARGIN`: the region is ~12% of a CamB frame, and the fit ran 4x
    slower than the old chain uncropped."""
    T = np.eye(3, dtype=np.float32)
    if mask is not None:
        # ponytail: carried by the seed, not the converged W; refit once if seeds jump
        moved = cv2.warpPerspective(mask, init.astype(np.float32), mask.shape[::-1],
                                    flags=cv2.INTER_NEAREST)
        x, y, w, h = _union(_box(mask), cv2.boundingRect(moved))
        mask = moved
        x0, y0 = max(0, x - ECC_CROP_MARGIN), max(0, y - ECC_CROP_MARGIN)
        x1 = min(ref.shape[1], x + w + ECC_CROP_MARGIN)
        y1 = min(ref.shape[0], y + h + ECC_CROP_MARGIN)
        box = (x0, y0, x1, y1)
        cur, mask = (im[y0:y1, x0:x1] for im in (cur, mask))
        T[:2, 2] = x0, y0
    D = np.diag([ECC_SCALE, ECC_SCALE, 1.0]).astype(np.float32) @ np.linalg.inv(T)
    small = lambda im, how=cv2.INTER_AREA: cv2.resize(im, None, fx=ECC_SCALE, fy=ECC_SCALE,
                                                      interpolation=how)
    rows = 3 if motion == cv2.MOTION_HOMOGRAPHY else 2
    seed = (D @ init @ np.linalg.inv(D))[:rows].astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, ECC_MAX_ITERATIONS, ECC_EPS)
    small_ref = small(ref) if mask is None else _small_crop(ref, box)
    correlation, w = cv2.findTransformECC(small_ref, small(cur), seed, motion, criteria,
                                          None if mask is None else small(mask, cv2.INTER_NEAREST), 5)
    w = w if rows == 3 else np.vstack([w, [0, 0, 1]])
    return (np.linalg.inv(D) @ w @ D).astype(np.float32), correlation


# The last `_small_crop`, `(ref, box, small)`: `ref` is the baseline frame on
# every Look, and its crop box repeats from one Look to the next.
_last_small = (None, None, None)


def _small_crop(ref, box):
    """`ref` cropped to `box`, `(x0, y0, x1, y1)`, at `ECC_SCALE` as
    `ecc_warp` resizes it, reused while both repeat. A read and a write of
    one tuple, so a Run on another thread can only make it compute again."""
    global _last_small
    last_ref, last_box, last = _last_small
    if last_ref is ref and last_box == box:
        return last
    x0, y0, x1, y1 = box
    out = cv2.resize(ref[y0:y1, x0:x1], None, fx=ECC_SCALE, fy=ECC_SCALE,
                     interpolation=cv2.INTER_AREA)
    _last_small = ref, box, out
    return out


def _union(*rects):
    """`cv2.boundingRect` of the masks these are the boxes of, OR-ed: the box
    round the non-empty ones, `(0, 0, 0, 0)` when none is."""
    rects = [r for r in rects if r[2] and r[3]]
    if not rects:
        return 0, 0, 0, 0
    x, y = min(r[0] for r in rects), min(r[1] for r in rects)
    return (x, y, max(r[0] + r[2] for r in rects) - x,
            max(r[1] + r[3] for r in rects) - y)


def board_shift(previous, frame, W, region):
    """The translation, frame px as a 3x3, that takes the Board in `previous`
    onto the Board in `frame` (#171), both greyscale (`gray`). Read by phase
    correlation at `ECC_SCALE`, with a Hanning window, over the bounding box of `region` (baseline frame
    coords) as `W` carries it into `previous`.

    That box and nothing round it: when only the Board moves, the gravel and
    sky round it stay put and pull the estimate towards zero. On #171's
    synthetic Board, an `ECC_CROP_MARGIN` of dense gravel round the box held it
    at zero.

    ponytail: no gate on phase correlation's response; the #171 probe found no
    estimate that threw ECC off, and a low-response one read ~zero, leaving
    the seed as it was. Gate on the response if one ever does."""
    moved = cv2.warpPerspective(region, W.astype(np.float32), region.shape[::-1],
                                flags=cv2.INTER_NEAREST)
    x, y, w, h = cv2.boundingRect(moved)
    small = lambda im: cv2.resize(im[y:y + h, x:x + w], None, fx=ECC_SCALE, fy=ECC_SCALE,
                                  interpolation=cv2.INTER_AREA)
    before, after = small(previous), small(frame)
    (dx, dy), _ = cv2.phaseCorrelate(before, after,
                                     cv2.createHanningWindow(before.shape[::-1], cv2.CV_32F))
    return np.float32([[1, 0, dx / ECC_SCALE], [0, 1, dy / ECC_SCALE], [0, 0, 1]])


def texture_region(board_to_frame, frame_size, sheets):
    """ECC mask in the frame: the Target Sheets' bounds (ADR-0011, Board px),
    carried into the frame by `board_to_frame`. A sheet is the one surface
    known to be flat. Anything round it (gravel, a stand, a chair's mesh
    back) need not lie in its plane, and once the Board turns, a mesh's
    texture outvotes the paper and pulls the homography off the sheet:
    a turned chair duplicated its sheet's holes 15-30 Board px out. It was
    the square within 1.5 Target spans of the ring (#50) before. Nothing
    off the sheets is detected (ADR-0011), so nothing there needs placing."""
    region = np.zeros(frame_size[::-1], np.uint8)
    for x0, y0, x1, y1 in sheets:
        corners = apply(board_to_frame, [[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        cv2.fillConvexPoly(region, np.round(corners).astype(np.int32), 255)
    return region


def _remembered(size):
    """Remember a function of one array for the last `size` arrays it was
    called with, by identity (#276): an image a Look has already converted
    is converted once. An array changed in place after would read stale;
    none is. One read and one write of a tuple per call, so a Run on another
    thread can only make it compute again."""
    def wrap(fn):
        memo = ()

        @functools.wraps(fn)
        def call(arg):
            nonlocal memo
            seen = memo
            for a, out in seen:
                if a is arg:
                    return out
            out = fn(arg)
            memo = ((arg, out),) + seen[:size - 1]
            return out
        return call
    return wrap


@_remembered(2)
def gray(frame):
    """A BGR frame as greyscale, 0-1 float32: what registration on Board
    texture (`track_view`) reads. Remembered for two frames, so a frame
    tracked now and handed back as the next Look's `previous`, or tracked
    from each seed in `reanchor_view`, is greyed once."""
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255


# The ECC region's box: the same mask every Look
_box = _remembered(1)(cv2.boundingRect)


class Anchor(NamedTuple):
    """The baseline frame every later frame is registered to (#50)."""
    gray: np.ndarray     # the baseline frame, greyscale, 0-1
    region: np.ndarray   # the ECC mask, baseline frame coords
    H: np.ndarray        # template -> baseline frame


def net_scale(board_scale, template_span_px, frame_span_px, imgsz, canvas_long_side):
    """Apparent size of a Bullet Hole in the tensor, relative to the raw frame.

    The number that decides whether the detector sees anything at all. Two
    scalings compose — the warp into Board space, and ultralytics' own resize of
    the canvas to `imgsz` — and only their product matters, which is why setting
    `imgsz` alone tells you nothing.

    Measured on real footage: exactly zero detections at 1.81, at three canvas
    resolutions an octave apart. Below that the response is flat rather than
    peaked — see TARGET_NET_SCALE for what did and did not reproduce.

    `canvas_long_side` is max(width, height), because that is the side
    ultralytics fits to `imgsz`. Passing the width of a portrait canvas silently
    overstates the net scale — on a 709x1063 Board the true letterbox factor is
    0.66, not 0.99.
    """
    warp = (board_scale * template_span_px) / frame_span_px
    letterbox = imgsz / canvas_long_side
    return warp * letterbox


def board_scale_for(template_span_px, frame_span_px, wanted=TARGET_NET_SCALE):
    """Board-space scale that puts the detector's canvases at `wanted` net scale.

    Paired with `imgsz == the canvas's longest side`, so ultralytics' resize is
    ~1.0 and the warp alone carries the net scale.
    """
    return wanted * frame_span_px / template_span_px


class BoardView:
    """A rectified Board for one frame, with its Targets located inside it.

    Positions taken from this view are directly comparable with positions from
    any other frame's view, because both live in Board space.
    """

    def __init__(self, H, tpl_to_board, canvas_size, targets, anchor=None, sheets=(),
                 crops=()):
        self.H = H                        # template -> frame
        self.tpl_to_board = tpl_to_board  # template -> Board space (scale + origin)
        self.canvas_size = canvas_size    # (width, height) of the rectified Board
        self.targets = targets            # Target polygons, Board-space coords
        self.anchor = anchor              # what `track_view` registers onto
        # Per Target, its sheet's bound, (x0, y0, x1, y1) Board px (ADR-0011),
        # and the canvas the detector is shown it on, (x, y, w, h) whole Board
        # px. The canvases are fixed by the baseline frame and all one size.
        self.sheets = [tuple(map(float, b)) for b in sheets]
        self.crops = [tuple(map(int, c)) for c in crops]

    @property
    def board_scale(self):
        return float(self.tpl_to_board[0, 0])

    def ring_centre(self, target_index=None):
        """A Target's 10-ring centre in Board space — SOW 2.3.2's origin.

        `target_index` None falls back to the registered reference position,
        which is only correct for the Target the homography was fitted to.
        Measuring a Bullet Hole on Target 2 against Target 1's centre is a
        silent, large error, so callers pass the Target the Bullet Hole is on.

        Target 1's is its registered ring; every other's is that moved by
        its centroid's offset from Target 1's, as `sheet_bounds` places the
        sheets. The silhouettes share the artwork and its edge bias, so the
        offset cancels it; the silhouette's centroid itself does not (#302:
        2-5.5 mm off the disk on CamB). Assumes Targets are not rotated
        relative to one another, as the single-plane Board does.
        """
        ring = self.template_to_board([RING_CENTRE_TPL])[0]
        if target_index is None or not self.targets:
            return ring
        polygons = self.targets[0], self.targets[target_index]
        if not all(cv2.moments(t)["m00"] for t in polygons):
            return ring
        return ring + (_centroid(polygons[1]) - _centroid(polygons[0])).astype(np.float32)

    @property
    def match_radius(self):
        """`MATCH_TPL_PX` expressed in Board-space pixels."""
        return MATCH_TPL_PX * self.board_scale

    def template_to_board(self, points):
        return apply(self.tpl_to_board, points)

    def board_to_template(self, points):
        return apply(np.linalg.inv(self.tpl_to_board), points)

    def _frame_to_board(self):
        return self.tpl_to_board @ np.linalg.inv(self.H)

    def frame_to_board(self, points):
        return apply(self._frame_to_board(), points)

    def board_to_frame(self, points):
        return apply(self.H @ np.linalg.inv(self.tpl_to_board), points)

    def rectify(self, frame):
        """The Board viewed square-on, at Board scale: `--out`'s canvas. The
        detector is shown `sheet_canvases`, cut from the same grid."""
        return cv2.warpPerspective(frame, self._frame_to_board(), self.canvas_size)

    def sheet_canvases(self, frame):
        """Each sheet's canvas, cut from Board space on `rectify`'s pixel grid,
        warped straight from the frame (ADR-0011). The same pixels to the
        warp's sub-pixel rounding, a few grey levels on ~0.1% of them."""
        to_board = self._frame_to_board()
        return [cv2.warpPerspective(frame, _as_matrix(1.0, (-x, -y)) @ to_board, (w, h))
                for x, y, w, h in self.crops]

    def sheet_of(self, points):
        """For each Board-space point, the first sheet whose bound holds it
        (edges included), or -1 beyond every sheet's."""
        p = np.asarray(points, np.float64).reshape(-1, 2)
        found = np.full(len(p), -1)
        for i, (x0, y0, x1, y1) in reversed(list(enumerate(self.sheets))):
            found[(p[:, 0] >= x0) & (p[:, 0] <= x1) & (p[:, 1] >= y0) & (p[:, 1] <= y1)] = i
        return found

    def assign(self, point):
        """Index of the Target this Bullet Hole is on, or None for a Miss.

        A Miss is a real Hit on the Board, counted, but carrying no Shot Distance
        and no score.
        """
        if not self.targets:
            return None
        p = (float(point[0]), float(point[1]))
        inside = [i for i, t in enumerate(self.targets)
                  if cv2.pointPolygonTest(t, p, False) >= 0]
        return inside[0] if inside else None


def build_view(frame, template_mask, board_scale=None, init_H=None):
    """Locate the Board in `frame` and return `(BoardView, ECC correlation)`.

    The largest Target is the registration reference; every other Target is
    mapped into the same Board space through that one homography — the
    Board-level fit described in the module docstring.

    Returns `(None, None)` when no Target is visible.
    """
    contours, frame_mask = find_targets(frame)
    if not contours:
        return None, None
    # #296: affine, as the silhouette does not constrain a perspective term (#295).
    H, correlation = register(template_mask, frame_mask, contours[0], init_H, cv2.MOTION_AFFINE)
    # #302: scale and centre from the printed interior, not the silhouette's edge.
    A, _ = interior_fit(frame, H)
    if A is not None:
        H = (H @ A).astype(np.float32)

    if board_scale is None:
        board_scale = board_scale_for(contour_span(template_contour(template_mask)),
                                      contour_span(contours[0]))

    # Where the Targets land before the origin is chosen.
    unshifted = _as_matrix(board_scale) @ np.linalg.inv(H)
    placed = [apply(unshifted, c.reshape(-1, 2)) for c in contours]
    allpts = np.vstack(placed)

    # The canvas spans every Target plus a margin, for `--out`.
    margin = BOARD_MARGIN * spread(allpts)
    lo = allpts.min(axis=0) - margin
    size = tuple(int(v) for v in np.ceil(allpts.max(axis=0) - lo + margin))
    tpl_to_board = _as_matrix(board_scale, (-lo[0], -lo[1]))
    targets = [(apply(_as_matrix(1.0, (-lo[0], -lo[1])), p)
                .reshape(-1, 1, 2).astype(np.float32)) for p in placed]
    sheets = sheet_bounds(targets, tpl_to_board)
    anchor = Anchor(gray(frame), texture_region(H @ np.linalg.inv(tpl_to_board),
                                                frame.shape[1::-1], sheets), H)
    return (BoardView(H, tpl_to_board, size, targets, anchor, sheets, sheet_crops(sheets)),
            correlation)


def _centroid(polygon):
    m = cv2.moments(polygon)
    return np.array([m["m10"] / m["m00"], m["m01"] / m["m00"]])


def sheet_bounds(targets, tpl_to_board, bound_tpl=None):
    """Each Target's sheet bound in Board px, `(x0, y0, x1, y1)`: the
    reference Target's (`targets[0]`, the one Board space was fitted to)
    through Board space, every other's the same moved by its centroid's offset
    from the reference's (#271). `bound_tpl` defaults to `sheet_bound_tpl()`.

    ponytail: axis-aligned in Board space, as #271 placed the sheets; a Target
    turned against the reference gets an upright bound. A Target the frame's
    edge cuts (CamA's second) has its centroid, and so its sheet, pulled
    toward what is in view. Place each sheet by its own silhouette fit if a
    sheet's truth ever sits near that edge."""
    x0, y0, x1, y1 = sheet_bound_tpl() if bound_tpl is None else bound_tpl
    ref = apply(tpl_to_board, [[x0, y0], [x1, y1]]).astype(np.float64).ravel()
    origin = _centroid(targets[0])
    return [tuple(ref + np.tile(_centroid(t) - origin, 2)) for t in targets]


def sheet_crops(sheets, context=None):
    """Each sheet's canvas, `(x, y, w, h)` whole Board px: its bound plus at
    least `context` (`SHEET_CONTEXT_PX`) on every side, grown evenly to whole
    multiples of 32, the detector's largest stride, so imgsz equal to the
    longer side resizes and pads nothing. All one size, so they share one
    detector call. Whole px, so a sheet canvas sits on the Board canvas's
    pixel grid."""
    c = SHEET_CONTEXT_PX if context is None else context
    if not sheets:
        return []
    x0, y0, x1, y1 = sheets[0]
    need = np.array([x1 - x0, y1 - y0]) + 2 * c
    w, h = (int(math.ceil(v / 32)) * 32 for v in need)
    sx, sy = (np.array([w, h]) - need) / 2 + c
    return [(math.floor(b[0] - sx), math.floor(b[1] - sy), w, h) for b in sheets]


@functools.cache
def sheet_bound_tpl(path=PRINT_SCALE_PATH):
    """The Target Sheet grown by `SHEET_BOUND_MM`, `(x0, y0, x1, y1)` template
    px about the reference Target's artwork (#271, ADR-0011).

    ponytail: one print for every Capture Setup, as the file holds today, and
    refused if the setups ever disagree: a stream has no Capture Setup to pick
    one by. Look it up per setup once two prints are in use."""
    with open(path) as f:
        entries = json.load(f)
    prints = {(tuple(e["sheet_tpl_px"]), checked_scale(e["mm_per_tpl_px"]))
              for e in entries.values()}
    if len(prints) != 1:
        raise ValueError(f"{os.path.basename(path)}: the Capture Setups hold {len(prints)} "
                         "different sheets or print scales; detection takes one (ADR-0011)")
    (rect, mm_per_tpl_px), = prints
    grow = SHEET_BOUND_MM / mm_per_tpl_px
    x0, y0, x1, y1 = rect
    return x0 - grow, y0 - grow, x1 + grow, y1 + grow


def track_view(frame, reference, seed=None, previous=None):
    """Re-register the reference view's Board space onto a later frame.

    Board space — scale, origin, canvas size and the Targets in it — is fixed
    once, by the baseline view, and every subsequent frame reuses it. Only the
    homography is re-estimated. The Targets are the baseline's polygons in the
    baseline's order, not this frame's contours: a Target lost to a shadow here
    would turn its Bullet Holes into Misses, and re-sorting by area would
    renumber the rest (#33). This is what makes a position from frame 300
    comparable with a position from frame 1; rebuilding Board space per frame
    would silently move the origin under the history.

    Each frame is registered to the BASELINE frame (`reference.anchor`), not
    the previous one, on the greyscale Board round the Target: H = W @ H0.
    The old chain — ECC on the one Target's silhouette, seeded frame to frame —
    had nothing past that Target to hold its perspective, and wandered p95
    63-66 template px at 1.2 Target spans against 7-8 for this (#50). The previous
    frame's W seeds the search, so the camera drift is tracked incrementally;
    `reference` may be the baseline view or any view tracked from it. `seed`
    (template -> frame) replaces the previous frame's fit as the starting point;
    `reanchor_view` passes one once the Board has moved out of its reach.

    `previous` is the frame `reference` was registered on. Given, and with no
    `seed`, the fit starts from `reference`'s moved by `board_shift` from
    `previous` to `frame`. A Board Move of 40x20 or 80x40 frame px puts the
    previous fit outside ECC's reach, and it converged to a wrong fit that was
    never Lost; the shift puts the start back inside it (#171).

    ponytail: one fixed reference frame, on purpose. A lost Board re-anchors
    against it (`reanchor_view`, #80) rather than against a recent frame, since
    every hop between frames adds its error to Board space. New Bullet Holes,
    shadows and wind still change the Board against it over a long session; if
    re-anchors start failing, the anchor itself needs refreshing, chained to
    this one.

    No Target need be visible: a fit with none in view converges low, and
    `silhouette_disagreement` then calls it grossly wrong (#276).

    Returns `(BoardView, ECC correlation)`. Raises `cv2.error` when
    registration fails to converge: "no evidence from this frame".
    """
    a = reference.anchor
    W = (reference.H if seed is None else seed) @ np.linalg.inv(a.H)
    if seed is None and previous is not None:
        W = board_shift(gray(previous), gray(frame), W, a.region) @ W
    W, correlation = ecc_warp(a.gray, gray(frame), cv2.MOTION_HOMOGRAPHY, W, a.region)
    return BoardView(W @ a.H, reference.tpl_to_board, reference.canvas_size,
                     reference.targets, a, reference.sheets, reference.crops), correlation


def shifted(view, d):
    """`view` with Board space translated up-left by `d` Board px under fixed
    canvases: the canvas-shift control (#46, #272). Everything on the Board,
    sheet bounds included, lands `d` px up and left of where it was on the
    sheet canvases, so each mark sits at another phase of the detector's
    stride grid. Positions read back through `board_to_template`
    are unmoved. A result that changes under it is grid noise."""
    move = _as_matrix(1.0, (-d, -d))
    return BoardView(view.H, move @ view.tpl_to_board, view.canvas_size,
                     [t - d for t in view.targets], view.anchor,
                     [tuple(np.subtract(b, d)) for b in view.sheets], view.crops)


def reanchor_view(frame, template_mask, reference):
    """Find the Board again after tracking lost it, in the same Board space (#80).

    `track_view` starts each fit from the last registered frame's, which is no
    use once the Board has moved out of ECC's reach (wind, a bumped stand). The
    silhouette registration the baseline was built with is run on this frame
    only as a seed; `track_view` then refines it against the same baseline
    frame on Board texture. Board space, the Targets (#33) and the anchor are
    `reference`'s. Rebuilding them with `build_view` instead would bring back the
    pre-#50 far-field error, 63-66 template px, as Registration Displacement.

    The Targets share one artwork, so a silhouette fit to a neighbour is a good
    fit one Target over, and neither proximity nor size says which Target is
    which after a jump. Every Target in view seeds a fit and the Board texture
    decides: the best correlation against the baseline frame is kept, and only
    above `REANCHOR_MIN_CORRELATION` — with the reference Target out of view,
    the best is a neighbour.

    Returns `(None, None)` when no Target is visible or no fit clears the floor.
    """
    contours, frame_mask = find_targets(frame)
    best = None, None
    for contour in contours:
        try:
            seed, _ = register(template_mask, frame_mask, contour)
            fit = track_view(frame, reference, seed)
        except cv2.error:
            continue
        if fit[1] is not None and fit[1] >= max(REANCHOR_MIN_CORRELATION, best[1] or 0):
            best = fit
    return best


def silhouette_disagreement(frame, template_mask, view):
    """How far an independent silhouette fit puts the reference Target's
    centre from where `view` puts it, in Board px (#92, #110).

    The silhouette registration the baseline was built with, from a box seed
    on the frame's largest Target, knows nothing of the tracked fit, so a
    tracked fit on the wrong part of the scene disagrees with it grossly. It
    sees only the reference Target, so it under-reads error elsewhere on the
    Board (#92: 21 here against 98 at another Target's centre).

    ponytail: seeded from the frame's largest Target, as #92 measured it, not
    the one nearest the tracked fit's reference: a wrong fit landing on a
    lookalike Target would agree with a fit seeded there. A right fit on a frame
    where a neighbour is largest reads ~one Target spacing and is lost; none was
    on #110's six clips. Match the contour to the baseline's Target if one is.

    Infinite when no Target is visible: a fit with nothing to fit is wrong
    (`track_view` does not look for one). None when the silhouette fit
    fails: no verdict.
    """
    contours, frame_mask = find_targets(frame)
    if not contours:
        return math.inf
    try:
        own_H, _ = register(template_mask, frame_mask, contours[0])
    except cv2.error:
        return None
    centre = view.targets[0].reshape(-1, 2).mean(axis=0, keepdims=True)
    own = apply(view.tpl_to_board @ np.linalg.inv(own_H), view.board_to_frame(centre))
    return float(np.linalg.norm(own - centre))


def residuals(frame, template_mask, view):
    """Per-Target registration error under the Board-level homography, in Board px.

    The measurement that settles the single-plane assumption. Each Target is
    registered on its own and compared against where the Board-level fit puts it;
    a Target whose own fit disagrees is one the Board-level homography is placing
    wrongly, which is how sheet curl would show up.

    Run this before spending effort on per-Target homographies: if the residuals
    are small, curl is not what is costing the 5mm.
    """
    contours, frame_mask = find_targets(frame)
    out = []
    for contour in contours:
        centre_board = view.frame_to_board(
            [contour.reshape(-1, 2).mean(axis=0)])[0]
        try:
            own_H, _ = register(template_mask, frame_mask, contour)
        except cv2.error:
            out.append(None)
            continue
        own_centre = apply(view.tpl_to_board @ np.linalg.inv(own_H),
                           [contour.reshape(-1, 2).mean(axis=0)])[0]
        out.append(float(np.linalg.norm(centre_board - own_centre)))
    return out


def _canvas_gray(canvas):
    return cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY).astype(np.float32)


# A Run's baseline sheet canvases, the same arrays every Look.
# ponytail: room for two Runs of two sheets; more thrash (recompute, never
# wrong). Key it per Run if that many ever run at once.
_baseline_gray = _remembered(4)(_canvas_gray)


def changed_regions(baseline_canvas, current_canvas, sigma=ABSDIFF_SIGMA):
    """Mask of what differs between two rectified images: a sheet canvas at
    the baseline frame and the same one now (ADR-0011).

    **Evidence only.** Change detection is deliberately not the gate: measured on
    real footage it covers at best 4 of 5 known new Bullet Holes at any
    threshold, so as the sole candidate source it would cap recall near 80%
    before the model is consulted. A detection that also changed is more likely
    real; one that did not is not thereby rejected.
    """
    base, b = _baseline_gray(baseline_canvas), _canvas_gray(current_canvas)
    valid = (base > 0) & (b > 0)
    if valid.sum() < 100:
        return np.zeros(b.shape, np.uint8)
    a = base - base[valid].mean()   # `base` is remembered: not changed in place
    a /= max(float(a[valid].std()), 1e-6)
    b -= b[valid].mean()
    b /= max(float(b[valid].std()), 1e-6)
    diff = np.abs(a - b)
    diff[~valid] = 0
    mask = (diff > sigma).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def print_scales(path=PRINT_SCALE_PATH):
    """Each Capture Setup's print scale, mm per template px.

    Each entry in `path` is `{"mm_per_tpl_px": ..., "source": ...}`, keyed by
    Capture Setup: the Boards of different setups may come from different
    prints. `source` says which print and how it was measured
    (docs/ring_measurement.md); an entry without one is refused, because a
    scale nobody can trace is a guess. Each entry also carries the Target
    Sheet's rectangle, `sheet_tpl_px` with its `sheet_source` (#271), which
    this does not read.

    The whole file is checked, not just one setup's entry, so a caller can read
    it before opening a recording: a malformed entry found after would cost a
    run that reports nothing.
    """
    name = os.path.basename(path)
    with open(path) as f:
        entries = json.load(f)
    scales = {}
    for capture_setup, entry in entries.items():
        where = f"{name}: {capture_setup!r}"
        if not entry.get("source"):
            raise ValueError(f"{where} has no source. Record which print and "
                             "how it was measured.")
        scales[capture_setup] = checked_scale(entry["mm_per_tpl_px"], where)
    return scales


def checked_scale(value, where="print scale"):
    """A print scale as a float, refused unless finite and above zero.

    It is a physical length ratio applied to every Shot Distance: zero would
    put every Bullet Hole on the centre, a negative one would mirror them.
    """
    scale = float(value)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError(f"{where}: mm_per_tpl_px {value!r} is not a finite "
                         "length above zero")
    return scale


def to_millimetres(board_points, view, mm_per_tpl_px=None, target_index=None):
    """Board-space positions as millimetres from a Target's centre.

    `mm_per_tpl_px` is the print scale: millimetres per template px on the
    printed Target, measured off its outline against the sheet
    (docs/ring_measurement.md). It is not a ruler reading of any ring.

    `target_index` names the Target the Bullet Holes are on. A Miss has no
    Target and therefore no Shot Distance — do not call this for one.

    Deliberately refuses to guess. Every millimetre figure scales linearly with
    the print scale, and it depends on how the Targets were printed — an
    unchecked assumption here would silently corrupt SOW 2.3.2's 5mm budget and
    every Grouping Analytic derived from it.
    """
    if mm_per_tpl_px is None:
        raise NotCalibrated(
            "no print scale (mm per template px) for this Board. Configure it "
            "for the Capture Setup in config/print_scale.json, or pass it; "
            "docs/ring_measurement.md has how it is measured. Not a ring's "
            "ruler reading. Everything downstream scales linearly with it, so "
            "it is not guessed.")
    mm_per_board_px = mm_per_tpl_px / view.board_scale
    return to_printed_axes(np.asarray(board_points, np.float32).reshape(-1, 2)
                           - view.ring_centre(target_index), mm_per_board_px)


def to_printed_axes(offsets, mm_per_unit):
    """Image-axis offsets as millimetres along the Target's printed axes, X
    right and Y up, at `mm_per_unit` millimetres per unit of `offsets`.

    A Position and its Position Error both take Y up from here, so dY cannot
    change sign against its Position. Each caller's offsets keep their own
    precision: float32 Board px for a Position, float64 template px for a
    Position Error.
    """
    mm = offsets * mm_per_unit
    mm[:, 1] *= -1  # image y grows downward, the printed Target's Y grows up
    return mm


def score(board_points, view, target_index=None):
    """Scoring ring for each Bullet Hole, from its distance to the ring centre.

    **Needs no calibration.** A score is which printed ring contains the Bullet
    Hole — a ratio between two lengths in the same picture, not a physical
    measurement. The ring radii and the Bullet Hole are both in template pixels,
    so the millimetre scale cancels and `to_millimetres`'s missing print scale
    does not block this.

    Returns `OUTSIDE_RINGS` for a Bullet Hole on the Target but beyond the
    6-ring. A Miss has no Target and so no score — do not call this for one.
    """
    centre = view.ring_centre(target_index)
    points = np.asarray(board_points, np.float32).reshape(-1, 2)
    if not len(points):
        return []
    # Board space is template space scaled, so dividing recovers template px.
    distances = np.linalg.norm(points - centre, axis=1) / view.board_scale
    return [next((s for radius, s in zip(RING_RADII_TPL, RING_SCORES) if d <= radius),
                 OUTSIDE_RINGS) for d in distances]
