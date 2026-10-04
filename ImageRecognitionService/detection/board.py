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
baseline frame's is fitted to the reference Target's silhouette, and every later
frame is registered to the baseline frame on the Board's own texture (#50). This
assumes the Board is a single plane. The sheets are stapled separately and
visibly curl, so the assumption is known to be imperfect; `residuals` exists to
measure what it costs if SOW 2.3.2's 5mm proves unreachable. The alternative is
one homography per Target, which absorbs curl a Board-level fit cannot.
"""
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

# Ring centre relative to the silhouette's centroid. Every Target on a Board is
# the same artwork, but only the reference Target is registered against the
# template; this offset places the ring centre on the others from their own
# outline, without a second registration. Assumes Targets are not rotated
# relative to one another — consistent with the single-plane Board.
RING_OFFSET_TPL = RING_CENTRE_TPL - np.array([696.8, 648.9])

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
# (CamA_20260914_141546). Any tuning happens on footage that is not sealed; they
# are fixed before the sealed run, which evaluates them once and changes none of
# them (ADR-0005, #31). Every number below is a starting point, not a
# requirement. See docs/adr/0003-a-bullet-hole-is-new-when-it-persists.md.

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
# Target spread. Bullet Holes outside this are not merely unscored, they are
# never seen — so this bounds recall, not just presentation.
#
# It is now the floor, not the whole extent: `canvas_layout` grows the canvas
# past it to the Board's edge where one is found (#46), and never cuts inside it.
# The detector is still shown this margin canvas exactly as before, and the
# Board past it only as separate bands (`Inner`, `BoardView.exposed_bands`):
# shown one grown image, borderline marks moved with sub-pixel phase and with
# Board added far from them, and the canvas-shift control failed.
# It broke on the CamB close pose (#41), where Bullet Holes ~1.2 Target spans
# below the Target were off the canvas. Growing the canvas to the whole camera
# view was measured and rejected — CamA fell from F1 0.92 to 0.77, because any
# change to its canvas moves its marginal detections — and so was the
# colour-connected Board (#46). CamA finds no Board edge past this margin, so
# its canvas is unchanged.
BOARD_MARGIN = 0.50        # PROVISIONAL

# The Board's edge (#46): the canvas grows past `BOARD_MARGIN` to the first
# straight edge round the Targets, where the Board ends at the ground or at a
# seam with the next Board of the stand. Colour cannot find it: the Boards
# abutting it are the same white. Set against the four spent/threshold-work
# recordings' baseline frames; not swept.
EDGE_GAP_SPANS = 0.3       # PROVISIONAL: skip the Target print's own border, nearer in
EDGE_SEARCH_SPANS = 2.0    # PROVISIONAL: how far from the ring the edge is looked for
EDGE_MIN = 20.0            # PROVISIONAL: mean Sobel along the edge, 8-bit grey
EDGE_PX = 0.25             # search resolution, per template px: 268 px a Target span
EDGE_BLUR = 2.0            # search px; the border erosion below covers its reach


# Registration after the baseline frame (#50). ECC on the greyscale Board within
# this many Target spans of the ring (a square: its corners reach ~2.1), fitted
# at this fraction of the frame's resolution. Measured with
# registration_reach.py on the four spent/threshold-work recordings; not swept.
REGION_SPANS = 1.5         # PROVISIONAL
ECC_SCALE = 0.5            # PROVISIONAL: half resolution
ECC_CROP_MARGIN = 64       # frame px round the region: room for the camera drift


class NotCalibrated(RuntimeError):
    """Raised when a physical measurement is requested before calibration."""


def _as_matrix(scale, offset=(0.0, 0.0)):
    return np.array([[scale, 0.0, offset[0]],
                     [0.0, scale, offset[1]],
                     [0.0, 0.0, 1.0]], np.float32)


def _apply(matrix, points):
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
    `BOARD_MARGIN` and `uncovered_view` both measure in."""
    return float(np.ptp(np.asarray(points).reshape(-1, 2), axis=0).max())


SIDES = ("left", "right", "above", "below")
AXIS = {"left": 0, "right": 0, "above": 1, "below": 1}   # which coordinate a side bounds


def find_board_edges(frame, H, template_span):
    """Where the Board the Targets are on ends, per side, in template px:
    x for `left`/`right`, y for `above`/`below`; None where no edge was found.

    The frame is viewed square-on round the ring, and each side is walked
    outward from `EDGE_GAP_SPANS` past the Targets. The edge is the first row
    (or column) whose gradient, averaged along the Targets' whole width, is at
    least `EDGE_MIN`: averaged signed, so a straight edge adds up while the
    ground's texture or a Bullet Hole cancels out. The first, not the strongest: past the seam the next Board's print is the
    stronger line. The walk stops, edgeless, where the frame's view ends or
    `EDGE_SEARCH_SPANS` does.

    ponytail: one straight line per side, read only along the Targets' width
    and parallel to Board space's axes, which tilt ~5 degrees against the
    stand on CamB; a side can take a sliver of ground at one end. A Target
    strip leaving the search square or the frame (CamA's second Target) finds
    no edge on the sides across it. A Board edge inside `EDGE_GAP_SPANS` is
    walked past, and the next straight line out, on the ground or the next
    Board, is taken instead: CamA's panel top is inside the gap and its frame
    ends first. Fit the line, not a row, and check the far side is not Board,
    if any of that costs."""
    contours, _ = find_targets(frame)
    lo = RING_CENTRE_TPL - EDGE_SEARCH_SPANS * template_span
    M = _as_matrix(EDGE_PX, -lo * EDGE_PX)
    n = int(2 * EDGE_SEARCH_SPANS * template_span * EDGE_PX)
    to_work = M @ np.linalg.inv(H)
    grey = cv2.warpPerspective(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32),
                               to_work, (n, n))
    grey = cv2.GaussianBlur(grey, (0, 0), EDGE_BLUR)
    seen = cv2.warpPerspective(np.full(frame.shape[:2], 255, np.uint8), to_work, (n, n),
                               flags=cv2.INTER_NEAREST)
    seen = cv2.erode(seen, np.ones((17, 17), np.uint8)) > 0   # the blur reaches the border
    placed = np.vstack([_apply(to_work, c.reshape(-1, 2)) for c in contours])
    (x0, y0), (x1, y1) = np.clip(placed.min(axis=0), 0, n - 1).astype(int), \
        np.clip(placed.max(axis=0), 0, n - 1).astype(int)
    rows = cv2.Sobel(grey, cv2.CV_32F, 0, 1)[:, x0:x1 + 1].mean(axis=1)
    cols = cv2.Sobel(grey, cv2.CV_32F, 1, 0)[y0:y1 + 1].mean(axis=0)
    rows_seen, cols_seen = seen[:, x0:x1 + 1].all(axis=1), seen[y0:y1 + 1].all(axis=0)
    gap = int(EDGE_GAP_SPANS * template_span * EDGE_PX)

    def walk(profile, visible, start, step, axis):
        for i in range(start, n if step > 0 else -1, step):
            if not 0 <= i < n or not visible[i]:
                return None
            if abs(profile[i]) >= EDGE_MIN:   # climb from the ramp to its peak
                while 0 <= i + step < n and visible[i + step] \
                        and abs(profile[i + step]) > abs(profile[i]):
                    i += step
                return float(i / EDGE_PX + lo[axis])
        return None

    return {"left": walk(cols, cols_seen, x0 - gap, -1, 0),
            "right": walk(cols, cols_seen, x1 + gap, 1, 0),
            "above": walk(rows, rows_seen, y0 - gap, -1, 1),
            "below": walk(rows, rows_seen, y1 + gap, 1, 1)}


def canvas_bounds(targets, edges, ring, span):
    """`(lo, hi)` corners of the canvas round `targets`, all in one frame of
    reference: `BOARD_MARGIN` past them, grown to each Board edge (see
    `find_board_edges`) but no further than `REGION_SPANS` of the `ring`, the
    ECC region registration is fitted on (#50; its wander was measured to 1.3
    spans, so 1.3-1.5 is unmeasured). An edge inside the margin, or none,
    leaves the margin canvas: it only ever grows, so a recording that finds
    no edge past it — CamA — searches exactly what it did before."""
    margin = BOARD_MARGIN * spread(targets)
    lo, hi = targets.min(axis=0) - margin, targets.max(axis=0) + margin
    reach = REGION_SPANS * span
    for side, edge in edges.items():
        if edge is None:
            continue
        axis = AXIS[side]
        if side in ("left", "above"):
            lo[axis] = min(lo[axis], max(edge, ring[axis] - reach))
        else:
            hi[axis] = max(hi[axis], min(edge, ring[axis] + reach))
    return lo, hi


class Layout(NamedTuple):
    """Where the canvas sits, and the `BOARD_MARGIN` canvas inside it (#46)."""
    lo: np.ndarray          # canvas origin, unshifted Board px
    size: tuple             # (width, height)
    inner_lo: np.ndarray    # the margin canvas's origin, exactly as before #46
    inner_size: tuple
    offset: tuple           # whole px from the canvas origin to the margin canvas's


def canvas_layout(targets, edges, ring, span):
    """The margin canvas, and the canvas grown from it to the Board's edges.

    The margin canvas is computed with the expressions `build_view` used
    before #46, so what the detector is shown there is that canvas to the bit
    (see `Inner`). The
    growth up and left is rounded up to whole pixels, so it sits on the grown
    canvas's pixel grid; the grown canvas therefore reaches up to a pixel past
    `canvas_bounds`' extent, and never short of it."""
    margin = BOARD_MARGIN * spread(targets)
    inner_lo = targets.min(axis=0) - margin
    inner_size = tuple(int(v) for v in np.ceil(targets.max(axis=0) - inner_lo + margin))
    grown_lo, grown_hi = canvas_bounds(targets, edges, ring, span)
    offset = tuple(max(0, int(np.ceil(inner_lo[a] - grown_lo[a] - 1e-6))) for a in (0, 1))
    size = tuple(offset[a] + max(inner_size[a], int(np.ceil(grown_hi[a] - inner_lo[a] - 1e-6)))
                 for a in (0, 1))
    return Layout(inner_lo - np.array(offset, inner_lo.dtype), size, inner_lo, inner_size, offset)


def _blurred(mask):
    return cv2.GaussianBlur(mask.astype(np.float32) / 255, (21, 21), 0)


def box_seed(source_contour, reference_contour):
    """Homography taking one contour's bounding box onto another's."""
    def corners(contour):
        x, y, w, h = cv2.boundingRect(contour)
        return np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
    return cv2.getPerspectiveTransform(corners(source_contour), corners(reference_contour))


def register(template_mask, frame_mask, reference_contour, init=None):
    """Homography mapping template coordinates onto the frame.

    Bounding-box correspondence for an initial guess, then ECC refinement on the
    blurred masks. Feature matching (SIFT/ORB) is not used and does not work
    here: the artwork is flat colour with thin rings, giving ~132 keypoints and a
    degenerate homography that collapses to a sliver.

    Returns `(H, correlation)`. Raises `cv2.error` if ECC fails to converge, which
    callers must treat as "this frame is no evidence" rather than as a position.
    """
    if init is None:
        init = box_seed(template_contour(template_mask), reference_contour)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    correlation, H = cv2.findTransformECC(
        _blurred(template_mask), _blurred(frame_mask),
        init.astype(np.float32), cv2.MOTION_HOMOGRAPHY, criteria, None, 5)
    return H, correlation


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
        x, y, w, h = cv2.boundingRect(mask | moved)
        mask = moved
        x0, y0 = max(0, x - ECC_CROP_MARGIN), max(0, y - ECC_CROP_MARGIN)
        x1 = min(ref.shape[1], x + w + ECC_CROP_MARGIN)
        y1 = min(ref.shape[0], y + h + ECC_CROP_MARGIN)
        ref, cur, mask = (im[y0:y1, x0:x1] for im in (ref, cur, mask))
        T[:2, 2] = x0, y0
    D = np.diag([ECC_SCALE, ECC_SCALE, 1.0]).astype(np.float32) @ np.linalg.inv(T)
    small = lambda im, how=cv2.INTER_AREA: cv2.resize(im, None, fx=ECC_SCALE, fy=ECC_SCALE,
                                                      interpolation=how)
    rows = 3 if motion == cv2.MOTION_HOMOGRAPHY else 2
    seed = (D @ init @ np.linalg.inv(D))[:rows].astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    correlation, w = cv2.findTransformECC(small(ref), small(cur), seed, motion, criteria,
                                          None if mask is None else small(mask, cv2.INTER_NEAREST), 5)
    w = w if rows == 3 else np.vstack([w, [0, 0, 1]])
    return (np.linalg.inv(D) @ w @ D).astype(np.float32), correlation


def texture_region(H, frame_size, template_span):
    """ECC mask in the frame `H` maps the template onto: the square within
    `REGION_SPANS` Target spans of the ring, so gravel and sky, which move
    differently from the Board, do not vote."""
    square = RING_CENTRE_TPL + REGION_SPANS * template_span * np.array(
        [[-1, -1], [1, -1], [1, 1], [-1, 1]])
    region = np.zeros(frame_size[::-1], np.uint8)
    cv2.fillConvexPoly(region, _apply(H, square).astype(np.int32), 255)
    return region


def _gray(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255


class Inner(NamedTuple):
    """The `BOARD_MARGIN` canvas inside a grown one (#46).

    The detector is shown this canvas exactly as it was before #46 — its own
    matrix and size, not a crop of the grown canvas — and only the Board the
    edge search exposes past it goes through a second inference. Growing the
    image the detector sees moves its borderline marks: a Bullet Hole's
    confidence moved 0.26 -> 0.41 for half a pixel of translation, and
    0.19 -> 0.04 for Board added a Target span away (#46)."""
    tpl_to_board: np.ndarray   # template -> margin canvas px
    size: tuple                # (width, height)
    offset: tuple              # its origin in the grown canvas, whole px


class Band(NamedTuple):
    """A strip of Board past the margin canvas, searched on its own (#46)."""
    crop: tuple   # (x0, y0, x1, y1) canvas px the detector is shown
    owns: tuple   # (x0, y0, x1, y1) canvas px, half-open, whose detections it reports


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
    """Board-space scale that puts a full-canvas inference at `wanted` net scale.

    Paired with `imgsz == the canvas's longest side`, so ultralytics' resize is
    ~1.0 and the warp alone carries the net scale.
    """
    return wanted * frame_span_px / template_span_px


class BoardView:
    """A rectified Board for one frame, with its Targets located inside it.

    Positions taken from this view are directly comparable with positions from
    any other frame's view, because both live in Board space.
    """

    def __init__(self, H, tpl_to_board, canvas_size, targets, anchor=None, edges=None,
                 inner=None):
        self.H = H                        # template -> frame
        self.tpl_to_board = tpl_to_board  # template -> Board space (scale + origin)
        self.canvas_size = canvas_size    # (width, height) of the rectified Board
        self.targets = targets            # Target polygons, Board-space coords
        self.anchor = anchor              # what `track_view` registers onto
        self.edges = edges or dict.fromkeys(SIDES)  # `find_board_edges`'s edges, Board space
        # The margin canvas inside this one; the whole canvas when nothing grew.
        self.inner = inner or Inner(tpl_to_board, canvas_size, (0, 0))

    @property
    def board_scale(self):
        return float(self.tpl_to_board[0, 0])

    def ring_centre(self, target_index=None):
        """A Target's 10-ring centre in Board space — SOW 2.3.2's origin.

        `target_index` None falls back to the registered reference position,
        which is only correct for the Target the homography was fitted to.
        Measuring a Bullet Hole on Target 2 against Target 1's centre is a
        silent, large error, so callers pass the Target the Bullet Hole is on.
        """
        if target_index is None or not self.targets:
            return _apply(self.tpl_to_board, [RING_CENTRE_TPL])[0]
        moments = cv2.moments(self.targets[target_index])
        if moments["m00"] == 0:
            return _apply(self.tpl_to_board, [RING_CENTRE_TPL])[0]
        centroid = np.array([moments["m10"] / moments["m00"],
                             moments["m01"] / moments["m00"]], np.float32)
        return centroid + RING_OFFSET_TPL.astype(np.float32) * self.board_scale

    @property
    def match_radius(self):
        """`MATCH_TPL_PX` expressed in Board-space pixels."""
        return MATCH_TPL_PX * self.board_scale

    def _frame_to_board(self):
        return self.tpl_to_board @ np.linalg.inv(self.H)

    def frame_to_board(self, points):
        return _apply(self._frame_to_board(), points)

    def board_to_frame(self, points):
        return _apply(self.H @ np.linalg.inv(self.tpl_to_board), points)

    def rectify(self, frame):
        """The Board viewed square-on, at the scale detection wants."""
        return cv2.warpPerspective(frame, self._frame_to_board(), self.canvas_size)

    def rectify_inner(self, frame):
        """The margin canvas, warped with its own matrix exactly as `rectify`
        warps a view that never grew (#46)."""
        return cv2.warpPerspective(frame, self.inner.tpl_to_board @ np.linalg.inv(self.H),
                                   self.inner.size)

    @property
    def grew(self):
        """Did the canvas grow past the margin canvas anywhere?"""
        return self.inner.offset != (0, 0) or tuple(self.inner.size) != tuple(self.canvas_size)

    def in_inner(self, points):
        """Which Board-space points lie on the margin canvas (edges included)."""
        p = np.asarray(points, np.float64).reshape(-1, 2)
        (dx, dy), (w, h) = self.inner.offset, self.inner.size
        return (p[:, 0] >= dx) & (p[:, 0] <= dx + w) & (p[:, 1] >= dy) & (p[:, 1] <= dy + h)

    def exposed_bands(self, context):
        """The Board past the margin canvas as `Band`s, one per side it grew.

        Each band's crop reaches `context` px back into the margin canvas and,
        for left and right, past its corners, so a mark near a boundary is
        seen whole. What a band reports is only the region it owns: above and
        below own the canvas's full width past the margin canvas, left and
        right only the margin canvas's height. The owned regions tile the
        canvas outside the margin canvas without overlap, so no mark is
        reported by two bands, and none by a band that cut it off.

        ponytail: a band is only as deep as the growth plus `context` (38 px
        on `_103223`'s top), less context than one grown image; nothing was
        lost to that on #46's recordings, and it is not validated beyond them."""
        (dx, dy), (w, h) = self.inner.offset, self.inner.size
        W, H = self.canvas_size
        x1, y1 = dx + w, dy + h
        bands = []
        if dy > 0:
            bands.append(Band((0, 0, W, min(H, dy + context)), (0, 0, W, dy)))
        if H > y1:
            bands.append(Band((0, max(0, y1 - context), W, H), (0, y1, W, H)))
        yb0, yb1 = max(0, dy - context), min(H, y1 + context)
        if dx > 0:
            bands.append(Band((0, yb0, min(W, dx + context), yb1), (0, dy, dx, y1)))
        if W > x1:
            bands.append(Band((max(0, x1 - context), yb0, W, yb1), (x1, dy, W, y1)))
        return bands

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
    H, correlation = register(template_mask, frame_mask, contours[0], init_H)

    if board_scale is None:
        board_scale = board_scale_for(contour_span(template_contour(template_mask)),
                                      contour_span(contours[0]))

    # Where the Targets land before the origin is chosen.
    unshifted = _as_matrix(board_scale) @ np.linalg.inv(H)
    placed = [_apply(unshifted, c.reshape(-1, 2)) for c in contours]
    allpts = np.vstack(placed)

    # The canvas spans every Target plus a margin, so Bullet Holes on the Board
    # around a Target — Misses — are still inside the rectified image, and on
    # out to the Board's edge where one is found (#46).
    tpl_span = contour_span(template_contour(template_mask))
    moved = lambda edges, f: {k: None if v is None else f(k, v) for k, v in edges.items()}
    edges = moved(find_board_edges(frame, H, tpl_span), lambda k, v: v * board_scale)
    layout = canvas_layout(allpts, edges, RING_CENTRE_TPL * board_scale,
                           tpl_span * board_scale)
    lo, size = layout.lo, layout.size
    tpl_to_board = _as_matrix(board_scale, (-lo[0], -lo[1]))
    inner = Inner(_as_matrix(board_scale, (-layout.inner_lo[0], -layout.inner_lo[1])),
                  layout.inner_size, layout.offset)
    edges = moved(edges, lambda k, v: v - lo[AXIS[k]])

    targets = [(_apply(_as_matrix(1.0, (-lo[0], -lo[1])), p)
                .reshape(-1, 1, 2).astype(np.float32)) for p in placed]
    anchor = Anchor(_gray(frame), texture_region(H, frame.shape[1::-1], tpl_span), H)
    return BoardView(H, tpl_to_board, size, targets, anchor, edges, inner), correlation


# Under half a canvas pixel is projection rounding, not a strip the canvas
# could have held; anything more is a real gap and is reported.
ROUNDING_PX = 0.5


def target_span(view):
    """The Target span of this view's Targets, in Board px — the unit
    `BOARD_MARGIN` and the off-canvas warnings are read in. A tracked view
    carries the baseline's Targets (#33), so any view gives the same span."""
    return spread(np.vstack([t.reshape(-1, 2) for t in view.targets]))


def uncovered_view(view, frame_size):
    """How much of the Board in the camera's view the canvas leaves out, and
    where.

    Returns `(fraction, reach)`: the fraction of the frame's pixels whose
    Board position lies outside the canvas and short of every Board edge
    found, and how far past each canvas edge that runs, in Board px, zero under `ROUNDING_PX` — Board px, not
    Target spans, so reaches from different frames compare. A Bullet Hole out
    there is never looked for (#41). The fraction is taken in the
    frame, not in Board space: a homography does not keep area ratios, and on
    a steep view the far rows fill most of the Board-space footprint.

    Past a side where `find_board_edges` found the Board's edge, the view is
    ground and does not count; the reach there is the Board past the canvas,
    which `REGION_SPANS` cut off. Where no edge was found it is still the camera's
    view, an upper bound on the Board left unsearched, gravel included (#46).

    Returns None when the view does not map onto the Board plane as a convex
    quadrilateral, or the canvas onto the frame — a corner past the other's
    horizon — since no fraction of it is then meaningful.
    """
    w, h = frame_size
    footprint = view.frame_to_board([[0, 0], [w, 0], [w, h], [0, h]])
    if not cv2.isContourConvex(footprint.reshape(-1, 1, 2)):
        return None
    cw, ch = view.canvas_size
    canvas = np.float32([[0, 0], [cw, 0], [cw, ch], [0, ch]])
    if not cv2.isContourConvex(view.board_to_frame(canvas).reshape(-1, 1, 2)):
        return None
    lo, hi = footprint.min(axis=0), footprint.max(axis=0)
    bound = lambda side, fallback: fallback if view.edges[side] is None else view.edges[side]
    x0, x1 = bound("left", lo[0]), bound("right", hi[0])
    y0, y1 = bound("above", lo[1]), bound("below", hi[1])
    in_frame = lambda poly: 0.0 if poly is None else cv2.contourArea(
        view.board_to_frame(poly.reshape(-1, 2)))
    _, seen = cv2.intersectConvexConvex(
        footprint, np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]))
    if seen is None:
        return 0.0, dict.fromkeys(SIDES, 0.0)
    _, searched = cv2.intersectConvexConvex(seen, canvas)
    fraction = (in_frame(seen) - in_frame(searched)) / float(w * h)

    lo, hi = seen.reshape(-1, 2).min(axis=0), seen.reshape(-1, 2).max(axis=0)
    reach = {"left": -lo[0], "right": hi[0] - cw, "above": -lo[1], "below": hi[1] - ch}
    return fraction, {k: float(v) if v >= ROUNDING_PX else 0.0
                      for k, v in reach.items()}


def track_view(frame, reference):
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
    `reference` may be the baseline view or any view tracked from it.

    ponytail: one fixed reference frame. New Bullet Holes, shadows and wind
    change the Board against it over a long session; re-anchor to a recent
    registered frame if lost frames climb.

    Returns `(None, None)` when no Target is visible, and raises `cv2.error` when
    registration fails to converge — both mean "no evidence from this frame".
    """
    if not find_targets(frame)[0]:
        return None, None
    a = reference.anchor
    W, correlation = ecc_warp(a.gray, _gray(frame), cv2.MOTION_HOMOGRAPHY,
                              reference.H @ np.linalg.inv(a.H), a.region)
    return BoardView(W @ a.H, reference.tpl_to_board, reference.canvas_size,
                     reference.targets, a, reference.edges, reference.inner), correlation


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
        own_centre = _apply(view.tpl_to_board @ np.linalg.inv(own_H),
                            [contour.reshape(-1, 2).mean(axis=0)])[0]
        out.append(float(np.linalg.norm(centre_board - own_centre)))
    return out


def changed_regions(baseline_canvas, current_canvas, sigma=ABSDIFF_SIGMA):
    """Mask of what differs between two rectified Boards.

    **Evidence only.** Change detection is deliberately not the gate: measured on
    real footage it covers at best 4 of 5 known new Bullet Holes at any
    threshold, so as the sole candidate source it would cap recall near 80%
    before the model is consulted. A detection that also changed is more likely
    real; one that did not is not thereby rejected.
    """
    a = cv2.cvtColor(baseline_canvas, cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(current_canvas, cv2.COLOR_BGR2GRAY).astype(np.float32)
    valid = (a > 0) & (b > 0)
    if valid.sum() < 100:
        return np.zeros(a.shape, np.uint8)
    for img in (a, b):
        img -= img[valid].mean()
        img /= max(float(img[valid].std()), 1e-6)
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
    scale nobody can trace is a guess.

    The whole file is checked, not just one setup's entry, so a caller can read
    it before the sealed-run gate: a malformed entry found after the gate has
    logged the look would spend the held-out recording for nothing.
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
    offset = (np.asarray(board_points, np.float32).reshape(-1, 2)
              - view.ring_centre(target_index)) * mm_per_board_px
    offset[:, 1] *= -1  # image y grows downward, physical y grows up
    return offset


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
