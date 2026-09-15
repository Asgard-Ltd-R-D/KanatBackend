"""Board geometry: find it, register it, rectify it, and place Targets in it.

Board space is the coordinate system everything downstream works in. It is the
Target artwork's own pixel grid, scaled so detection runs at the right apparent
size and shifted so the canvas corner is the origin. Two properties make it the
right frame of reference:

- It does not move. The camera drifts ~16px over 12s on real footage, and the
  Board itself moves in wind; Board space absorbs both.
- It is tied to printed artwork of known physical size, so every Board-space
  length converts to millimetres the moment one ruler reading exists — see
  `to_millimetres`.

**One homography for the whole Board**, with Targets located inside it. This
assumes the Board is a single plane. The sheets are stapled separately and
visibly curl, so the assumption is known to be imperfect; `residuals` exists to
measure what it costs if SOW 2.3.2's 5mm proves unreachable. The alternative is
one homography per Target, which absorbs curl a Board-level fit cannot.
"""
import os

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(BASE_DIR, "targets", "kanat_silhouette_a4.png")

# --- Target artwork landmarks, measured on the source PNG -------------------
# Exact readings off the artwork, not tuning knobs.
RING_CENTRE_TPL = np.array([695.4, 639.2])  # white 10-ring centre, template px
RING_DIAMETER_TPL = 227.0                   # white 10-ring diameter, template px

# Ring centre relative to the silhouette's centroid. Every Target on a Board is
# the same artwork, but only the reference Target is registered against the
# template; this offset places the ring centre on the others from their own
# outline, without a second registration. Assumes Targets are not rotated
# relative to one another — consistent with the single-plane Board.
RING_OFFSET_TPL = RING_CENTRE_TPL - np.array([696.8, 648.9])

# Outer radius of each scoring ring, template px, measured off the artwork by
# tracing rays out from the ring centre and recording where the printed white
# lines fall. Spacing is ~101 px and the values repeat within 3 px across 280
# rays, which is the width of the printed line itself.
RING_RADII_TPL = (113.5, 219.0, 318.0, 420.0, 522.0)
RING_SCORES = (10, 9, 8, 7, 6)
OUTSIDE_RINGS = 0          # on the Target, beyond the 6-ring

# --- Provisional working values --------------------------------------------
# NONE of these are validated. They were set by hand against a single clip
# (CamA_20260914_141546) and exist to be tuned against the held-out customer test
# set, which does not yet exist. Every number below is a starting point, not a
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
# So this value is inside a flat band, not on a measured peak. Settling it needs
# the held-out test set, not another sweep of one clip.
TARGET_NET_SCALE = 0.90    # PROVISIONAL

# Two detections are the same Bullet Hole within this many template px. Expressed
# in template px precisely so it survives a change of camera distance, unlike a
# frame-pixel value. 227 template px is the 10-ring diameter, so this converts to
# millimetres the moment `to_millimetres` is unblocked.
#
# Swept against operator-labelled ground truth (KanatV6, 6 Bullet Holes): 40
# scored 4 true / 2 false, 20 scored 5 true / 2 false. The radius also gates
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
# ponytail: the Board extent is inferred from where the Targets are, because
# nothing detects the plywood itself. That is the real fix; this constant buys
# time. Too small and Misses vanish; too large and imgsz grows with the canvas,
# costing inference time for empty ground.
BOARD_MARGIN = 0.50        # PROVISIONAL


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


def _blurred(mask):
    return cv2.GaussianBlur(mask.astype(np.float32) / 255, (21, 21), 0)


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
        tx, ty, tw, th = cv2.boundingRect(template_contour(template_mask))
        fx, fy, fw, fh = cv2.boundingRect(reference_contour)
        init = cv2.getPerspectiveTransform(
            np.float32([[tx, ty], [tx + tw, ty], [tx + tw, ty + th], [tx, ty + th]]),
            np.float32([[fx, fy], [fx + fw, fy], [fx + fw, fy + fh], [fx, fy + fh]]))
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    correlation, H = cv2.findTransformECC(
        _blurred(template_mask), _blurred(frame_mask),
        init.astype(np.float32), cv2.MOTION_HOMOGRAPHY, criteria, None, 5)
    return H, correlation


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

    def __init__(self, H, tpl_to_board, canvas_size, targets):
        self.H = H                        # template -> frame
        self.tpl_to_board = tpl_to_board  # template -> Board space (scale + origin)
        self.canvas_size = canvas_size    # (width, height) of the rectified Board
        self.targets = targets            # Target polygons, Board-space coords

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

    # The canvas spans every Target plus a margin, so Bullet Holes on the paper
    # around a Target — Misses — are still inside the rectified image.
    margin = BOARD_MARGIN * float(np.ptp(allpts, axis=0).max())
    lo = allpts.min(axis=0) - margin
    tpl_to_board = _as_matrix(board_scale, (-lo[0], -lo[1]))
    size = tuple(int(v) for v in np.ceil(allpts.max(axis=0) - lo + margin))

    targets = [(_apply(_as_matrix(1.0, (-lo[0], -lo[1])), p)
                .reshape(-1, 1, 2).astype(np.float32)) for p in placed]
    return BoardView(H, tpl_to_board, size, targets), correlation


def track_view(frame, template_mask, reference):
    """Re-register the reference view's Board space onto a later frame.

    Board space — scale, origin and canvas size — is fixed once, by the baseline
    view, and every subsequent frame reuses it. Only the homography is
    re-estimated. This is what makes a position from frame 300 comparable with a
    position from frame 1; rebuilding Board space per frame would silently move
    the origin under the history.

    The previous frame's homography seeds the search, so the ~16px camera drift
    is tracked incrementally rather than rediscovered.

    Returns `(None, None)` when no Target is visible, and raises `cv2.error` when
    registration fails to converge — both mean "no evidence from this frame".
    """
    contours, frame_mask = find_targets(frame)
    if not contours:
        return None, None
    H, correlation = register(template_mask, frame_mask, contours[0], reference.H)
    view = BoardView(H, reference.tpl_to_board, reference.canvas_size, [])
    view.targets = [_apply(view._frame_to_board(), c.reshape(-1, 2))
                    .reshape(-1, 1, 2).astype(np.float32) for c in contours]
    return view, correlation


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


def to_millimetres(board_points, view, ring_diameter_mm=None, target_index=None):
    """Board-space positions as millimetres from a Target's centre.

    `target_index` names the Target the Bullet Holes are on. A Miss has no
    Target and therefore no Shot Distance — do not call this for one.

    Deliberately refuses to guess. The printed 10-ring has never been measured
    with a ruler, and every millimetre figure scales linearly with it — an
    unchecked assumption here would silently corrupt SOW 2.3.2's 5mm budget and
    every Grouping Analytic derived from it.

    One ruler reading unblocks this, and scoring with it.
    """
    if ring_diameter_mm is None:
        raise NotCalibrated(
            "printed 10-ring diameter has not been measured. Measure the white "
            "centre circle on the printed Target and pass ring_diameter_mm. "
            "Everything downstream scales linearly with it, so it is not guessed.")
    mm_per_board_px = ring_diameter_mm / (RING_DIAMETER_TPL * view.board_scale)
    offset = (np.asarray(board_points, np.float32).reshape(-1, 2)
              - view.ring_centre(target_index)) * mm_per_board_px
    offset[:, 1] *= -1  # image y grows downward, physical y grows up
    return offset


def score(board_points, view, target_index=None):
    """Scoring ring for each Bullet Hole, from its distance to the ring centre.

    **Needs no calibration.** A score is which printed ring contains the Bullet
    Hole — a ratio between two lengths in the same picture, not a physical
    measurement. The ring radii and the Bullet Hole are both in template pixels,
    so the millimetre scale cancels and `to_millimetres`'s missing ruler reading
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
