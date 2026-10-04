"""Checks for Board geometry. No model, no video, no torch."""
import cv2
import numpy as np
import pytest

from detection import board
from tools import ring_landmarks


def _square(x0, y0, side):
    return np.float32([[x0, y0], [x0 + side, y0], [x0 + side, y0 + side],
                       [x0, y0 + side]]).reshape(-1, 1, 2)


def _view(targets, scale=1.0):
    """A BoardView with Board space already fixed — no registration needed."""
    return board.BoardView(H=np.eye(3, dtype=np.float32),
                           tpl_to_board=board._as_matrix(scale),
                           canvas_size=(1000, 1000),
                           targets=targets)


# --- net scale: the rule that decides whether the detector sees anything ----

def test_net_scale_is_the_product_of_both_scalings():
    """imgsz alone says nothing; the warp has already moved the scale."""
    assert board.net_scale(board_scale=2.0, template_span_px=100,
                           frame_span_px=200, imgsz=500,
                           canvas_long_side=1000) == pytest.approx(0.5)


def test_net_scale_measures_against_the_longest_side():
    """ultralytics fits the longest side, so a portrait canvas must not use width.

    A 709x1063 Board at imgsz 704 is a 0.66 letterbox, not 0.99. Reading it off
    the width overstates net scale by half and quietly starves the detector.
    """
    portrait = board.net_scale(1.0, 100, 100, imgsz=704, canvas_long_side=1063)
    assert portrait == pytest.approx(704 / 1063, abs=1e-6)


def test_measured_zero_detection_configurations_share_one_net_scale():
    """The three canvas sizes that measured zero detections are all net ~1.81.

    An octave apart in resolution, identical in net scale, identical in outcome.
    This is the evidence that net scale governs and resolution does not, so it is
    pinned rather than left in prose.
    """
    foot, tpl = 564.0, 1049.0
    # these canvases are landscape, so width is also the longest side
    got = [board.net_scale(size / tpl, tpl, foot, 1280, width)
           for size, width in ((1120, 1405), (1600, 2007), (2400, 3010))]
    assert got == pytest.approx([1.81, 1.81, 1.81], abs=0.02)


def test_board_scale_lands_on_the_requested_net_scale():
    """Round-trip: ask for 0.9, and a full-canvas inference gets 0.9."""
    tpl_span, frame_span = 1049.0, 564.0
    k = board.board_scale_for(tpl_span, frame_span, wanted=0.90)
    canvas_long = k * tpl_span
    assert board.net_scale(k, tpl_span, frame_span, imgsz=canvas_long,
                           canvas_long_side=canvas_long) == pytest.approx(0.90)


# --- Target assignment and Miss ---------------------------------------------

def test_bullet_hole_inside_a_target_is_assigned_to_it():
    view = _view([_square(0, 0, 100), _square(500, 500, 100)])
    assert view.assign((50, 50)) == 0
    assert view.assign((550, 550)) == 1


def test_bullet_hole_outside_every_target_is_a_miss():
    """A real Hit on the Board, counted, but carrying no score."""
    view = _view([_square(0, 0, 100), _square(500, 500, 100)])
    assert view.assign((300, 300)) is None


def test_miss_is_not_claimed_by_the_nearest_target():
    """Just outside a Target is still a Miss — proximity does not score."""
    view = _view([_square(0, 0, 100)])
    assert view.assign((101, 50)) is None


def test_board_with_no_targets_assigns_nothing():
    assert _view([]).assign((10, 10)) is None


# --- calibration is blocked, and says so ------------------------------------

def test_millimetres_refuses_to_guess_the_ring_diameter():
    """Everything downstream scales linearly with it, so it must not default."""
    with pytest.raises(board.NotCalibrated, match="has not been measured"):
        board.to_millimetres([[0, 0]], _view([]))


def test_scoring_needs_no_calibration():
    """A score is a ratio inside one picture, so the missing ruler cannot block it."""
    view = _view([_square(0, 0, 100)])
    centre = view.ring_centre(0)
    assert board.score([centre], view, 0) == [10]


def test_each_ring_scores_its_own_value():
    view = _view([_square(0, 0, 100)])
    centre = view.ring_centre(0)
    just_inside = [centre + [r - 1, 0] for r in board.RING_RADII_TPL]
    assert board.score(just_inside, view, 0) == list(board.RING_SCORES)


def test_just_outside_the_white_disk_scores_9():
    """112.5 px is past the disk's 111.5 edge; the old 113.5 boundary scored it 10 (#70)."""
    view = _view([_square(0, 0, 100)])
    assert board.score([view.ring_centre(0) + [112.5, 0]], view, 0) == [9]


def test_ring_landmarks_match_the_artwork():
    """The constants are readings off the PNG; re-reading it must agree."""
    edge, line_radii = ring_landmarks.measure()
    assert 2 * edge == pytest.approx(board.RING_DIAMETER_TPL, abs=0.1)
    assert line_radii == pytest.approx(board.RING_RADII_TPL[1:], abs=0.1)


def test_beyond_the_outer_ring_scores_outside():
    view = _view([_square(0, 0, 100)])
    far = view.ring_centre(0) + [board.RING_RADII_TPL[-1] + 10, 0]
    assert board.score([far], view, 0) == [board.OUTSIDE_RINGS]


def test_score_is_unaffected_by_board_scale():
    """Rectifying larger must not change which ring a Bullet Hole is in."""
    for scale in (1.0, 2.5):
        view = _view([_square(0, 0, 100 * scale)], scale=scale)
        point = view.ring_centre(0) + np.float32([250 * scale, 0])
        assert board.score([point], view, 0) == [8]


def test_millimetres_work_once_the_ring_is_measured():
    """A Bullet Hole one ring-radius right of centre is half a diameter right."""
    view = _view([], scale=1.0)
    centre = board.RING_CENTRE_TPL
    offset = centre + np.array([board.RING_DIAMETER_TPL / 2, 0])
    mm = board.to_millimetres([centre, offset], view, ring_diameter_mm=40.0)
    assert mm[0] == pytest.approx([0.0, 0.0])
    assert mm[1] == pytest.approx([20.0, 0.0])


def test_millimetres_are_independent_of_board_scale():
    """Rectifying larger must not change a physical measurement."""
    centre = board.RING_CENTRE_TPL
    offset = centre + np.array([board.RING_DIAMETER_TPL / 2, 0])
    at_one = board.to_millimetres([offset], _view([], scale=1.0), ring_diameter_mm=40.0)
    at_three = board.to_millimetres([offset * 3], _view([], scale=3.0), ring_diameter_mm=40.0)
    # abs, not relative: one component is zero, and float32 leaves ~1e-5 mm of
    # noise there. A micron is five thousand times under SOW 2.3.2's budget.
    assert at_one[0] == pytest.approx(at_three[0], abs=1e-3)


def test_physical_y_grows_upward():
    """Image y grows down; a Bullet Hole above centre must read positive."""
    view = _view([])
    above = board.RING_CENTRE_TPL - np.array([0, board.RING_DIAMETER_TPL / 2])
    assert board.to_millimetres([above], view, ring_diameter_mm=40.0)[0][1] == pytest.approx(20.0)


def test_each_target_has_its_own_ring_centre():
    """Measuring a Bullet Hole on Target 2 against Target 1's centre is a big,
    silent error — the Targets are hundreds of Board px apart."""
    view = _view([_square(0, 0, 100), _square(500, 500, 100)])
    first, second = view.ring_centre(0), view.ring_centre(1)
    assert np.linalg.norm(second - first) > 400
    # each sits near its own Target's centroid, offset by the artwork constant
    assert first == pytest.approx(np.float32([50, 50]) + board.RING_OFFSET_TPL, abs=1.0)
    assert second == pytest.approx(np.float32([550, 550]) + board.RING_OFFSET_TPL, abs=1.0)


def test_same_bullet_hole_measures_differently_against_different_targets():
    """The Target index is load-bearing, not cosmetic."""
    view = _view([_square(0, 0, 100), _square(500, 500, 100)])
    point = [[60.0, 60.0]]
    on_first = board.to_millimetres(point, view, ring_diameter_mm=40.0, target_index=0)
    on_second = board.to_millimetres(point, view, ring_diameter_mm=40.0, target_index=1)
    assert np.linalg.norm(on_first[0] - on_second[0]) > 50  # mm


# --- what the camera sees that the canvas does not (#41) --------------------

def test_camera_view_beyond_the_canvas_is_measured_in_board_px():
    """A 300x100 view over a 100x100 canvas: two thirds of it unsearched,
    all of it to the right, 200 Board px — two Target spans — out."""
    view = board.BoardView(H=np.eye(3, dtype=np.float32),
                           tpl_to_board=board._as_matrix(1.0),
                           canvas_size=(100, 100),
                           targets=[_square(0, 0, 100)])
    outside, reach = board.uncovered_view(view, frame_size=(300, 100))
    assert outside == pytest.approx(2 / 3, abs=1e-3)
    assert reach == pytest.approx({"left": 0, "right": 200, "above": 0, "below": 0})
    assert board.target_span(view) == 100


def test_canvas_covering_the_whole_view_leaves_nothing_uncovered():
    """CamA's canvas runs past its frame top and bottom; that is not a gap."""
    view = board.BoardView(H=np.eye(3, dtype=np.float32),
                           tpl_to_board=board._as_matrix(1.0, (0, 50)),
                           canvas_size=(100, 200),
                           targets=[_square(0, 50, 100)])
    outside, reach = board.uncovered_view(view, frame_size=(100, 100))
    assert outside == pytest.approx(0, abs=1e-3)
    assert set(reach.values()) == {0}


def test_a_one_pixel_strip_off_the_canvas_is_still_reported():
    """A 101x100 view over a 100x100 canvas: a real strip, however thin, is a
    Bullet Hole no run can find, so it is not rounded away."""
    view = board.BoardView(H=np.eye(3, dtype=np.float32),
                           tpl_to_board=board._as_matrix(1.0),
                           canvas_size=(100, 100),
                           targets=[_square(0, 0, 100)])
    outside, reach = board.uncovered_view(view, frame_size=(101, 100))
    assert outside == pytest.approx(1 / 101, abs=1e-4)
    assert reach == pytest.approx({"left": 0, "right": 1, "above": 0, "below": 0})


def test_uncovered_fraction_is_of_the_frame_not_of_the_board_plane():
    """A tilted view: the far rows fill most of the Board-space footprint, so
    the fraction must be counted in frame pixels, not Board-space area."""
    H = np.array([[1, 0, 0], [0, 1, 0], [0, 0.005, 1]], np.float32)
    view = board.BoardView(H=H, tpl_to_board=board._as_matrix(1.0),
                           canvas_size=(60, 60), targets=[_square(0, 0, 60)])
    outside, _ = board.uncovered_view(view, frame_size=(100, 100))
    ys, xs = np.mgrid[0:100, 0:100] + 0.5
    placed = view.frame_to_board(np.stack([xs.ravel(), ys.ravel()], axis=1))
    counted = np.mean((placed[:, 0] >= 60) | (placed[:, 1] >= 60))
    assert outside == pytest.approx(counted, abs=0.01)


def test_once_the_boards_edge_is_known_only_the_board_counts():
    """A 300x100 view over a 100x100 canvas, the Board ending 50 px past it
    on the right: the view beyond the edge is ground, not unsearched Board.
    A side with no edge found still counts the camera's view (#46)."""
    view = board.BoardView(H=np.eye(3, dtype=np.float32),
                           tpl_to_board=board._as_matrix(1.0, (0, 50)),
                           canvas_size=(100, 100), targets=[_square(0, 50, 100)],
                           edges={"left": None, "right": 150.0, "above": None,
                                  "below": None})
    outside, reach = board.uncovered_view(view, frame_size=(300, 200))
    # the view to x=150 is Board (150x200 frame px), the canvas holds 100x50 of it
    assert outside == pytest.approx((150 * 200 - 100 * 50) / (300 * 200), abs=1e-3)
    assert reach == pytest.approx({"left": 0, "right": 50, "above": 0, "below": 150})


def test_view_past_the_board_planes_horizon_is_not_measured():
    """A frame corner behind the plane flips the footprint; no fraction then."""
    H = np.array([[1, 0, 0], [0, 1, 0], [0, -0.02, 1]], np.float32)  # y=50 at infinity
    view = board.BoardView(H=np.linalg.inv(H), tpl_to_board=board._as_matrix(1.0),
                           canvas_size=(100, 100), targets=[_square(0, 0, 100)])
    assert board.uncovered_view(view, frame_size=(100, 100)) is None


# --- registration after the baseline frame (#50) ---------------------------

def _scene(shift=(0.0, 0.0), size=(320, 240)):
    """Paper with a few dark blobs, the whole scene moved by `shift` px."""
    img = np.full(size[::-1], 200, np.float32)
    for x, y in [(60, 50), (250, 70), (120, 180), (200, 150), (40, 200)]:
        cv2.circle(img, (int(x * 4 + shift[0] * 4), int(y * 4 + shift[1] * 4)), 40, 40, -1,
                   shift=2)
    return cv2.GaussianBlur(img, (0, 0), 3)


@pytest.mark.parametrize("motion", [cv2.MOTION_AFFINE, cv2.MOTION_HOMOGRAPHY])
def test_the_anchoring_warp_takes_baseline_coordinates_onto_the_frame(motion):
    W, _ = board.ecc_warp(_scene(), _scene((5.0, -3.0)), motion, np.eye(3, dtype=np.float32))
    moved = board._apply(W, [[100, 100]])[0]
    assert moved == pytest.approx([105, 97], abs=0.3)


@pytest.mark.parametrize("box", [(20, 220, 20, 300),     # crop is the whole image
                                 (40, 230, 90, 300)])    # three blobs; crop at (82, 32)
def test_a_masked_warp_follows_the_scene_not_the_mask(box, monkeypatch):
    """The region goes in as ECC's mask, not multiplied into both images,
    where its fixed edge would pull the warp towards no motion; and cropping
    to it does not move the answer."""
    monkeypatch.setattr(board, "ECC_CROP_MARGIN", 8)
    y0, y1, x0, x1 = box
    mask = np.zeros((240, 320), np.uint8)
    mask[y0:y1, x0:x1] = 255
    W, _ = board.ecc_warp(_scene(), _scene((5.0, -3.0)), cv2.MOTION_HOMOGRAPHY,
                          np.eye(3, dtype=np.float32), mask)
    assert board._apply(W, [[100, 100]])[0] == pytest.approx([105, 97], abs=0.3)


def test_the_mask_follows_the_board_into_the_frame():
    """ECC reads its mask in the moved frame's coordinates. Left at the
    baseline's, the static background the Board slid off votes in the fit."""
    rng = np.random.default_rng(0)
    tex = lambda: cv2.GaussianBlur(rng.random((240, 400)).astype(np.float32), (0, 0), 2)
    back, face = tex(), tex()
    moved = back.copy()
    moved[30:210, 190:340] = face[30:210, 150:300]      # the Board, 40 px right
    ref = back.copy()
    ref[30:210, 150:300] = face[30:210, 150:300]
    mask = np.zeros((240, 400), np.uint8)
    mask[30:210, 150:300] = 255
    seed = np.float32([[1, 0, 40], [0, 1, 0], [0, 0, 1]])
    W, correlation = board.ecc_warp(ref, moved, cv2.MOTION_HOMOGRAPHY, seed, mask)
    assert board._apply(W, [[225, 120]])[0] == pytest.approx([265, 120], abs=0.05)
    assert correlation > 0.99


def test_track_view_registers_onto_the_baseline_frame_and_chains(monkeypatch):
    """H = W @ H0 against the baseline frame; a tracked view seeds the next."""
    target = _square(100, 100, 50)
    monkeypatch.setattr(board, "find_targets", lambda frame: ([target], None))
    H0 = np.float32([[1, 0, 20], [0, 1, 10], [0, 0, 1]])
    anchor = board.Anchor(_scene() / 255, np.full((240, 320), 255, np.uint8), H0)
    reference = board.BoardView(H0, board._as_matrix(1.0), (300, 300), [], anchor)
    colour = lambda img: cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_GRAY2BGR)

    first, _ = board.track_view(colour(_scene((2.0, 1.0))), reference)
    second, _ = board.track_view(colour(_scene((5.0, -3.0))), first)
    assert board._apply(second.H, [[80, 90]])[0] == pytest.approx([105, 97], abs=0.4)
    assert second.anchor is anchor and second.targets is reference.targets


def _tracked(monkeypatch, reference, seen):
    """`reference` tracked onto a frame whose hue threshold finds `seen`.
    Sets `reference.anchor` to an identity registration."""
    monkeypatch.setattr(board, "find_targets", lambda frame: (seen, None))
    monkeypatch.setattr(board, "ecc_warp", lambda *a: (np.eye(3, dtype=np.float32), 1.0))
    reference.anchor = board.Anchor(None, None, reference.H)
    return board.track_view(np.zeros((10, 10, 3), np.uint8), reference)[0]


def test_a_bullet_hole_on_a_target_the_frame_lost_is_still_on_that_target(monkeypatch):
    """#33: a shadow hiding Target 2 from the last frame is not a Miss."""
    baseline = _view([_square(0, 0, 100), _square(500, 500, 90)])
    tracked = _tracked(monkeypatch, baseline, [_square(0, 0, 100)])
    assert tracked.assign((550, 550)) == 1


def test_target_numbers_are_the_baselines_when_target_1_drops_out(monkeypatch):
    """#33: losing Target 1 does not renumber Target 2 as Target 1."""
    baseline = _view([_square(0, 0, 100), _square(500, 500, 90)])
    tracked = _tracked(monkeypatch, baseline, [_square(500, 500, 90)])
    assert tracked.assign((550, 550)) == 1 and tracked.assign((50, 50)) == 0


def test_target_numbers_are_the_baselines_when_two_swap_area_order(monkeypatch):
    """#33: drift that makes Target 2 look the larger does not renumber them."""
    baseline = _view([_square(0, 0, 100), _square(500, 500, 90)])
    tracked = _tracked(monkeypatch, baseline, [_square(500, 500, 110), _square(0, 0, 100)])
    assert tracked.assign((50, 50)) == 0 and tracked.assign((550, 550)) == 1
    assert tracked.ring_centre(1) == pytest.approx(baseline.ring_centre(1))


def test_a_bullet_hole_on_no_target_is_still_a_miss_on_a_tracked_view(monkeypatch):
    """#33 keeps Misses Misses: the baseline's polygons are not widened."""
    baseline = _view([_square(0, 0, 100), _square(500, 500, 90)])
    assert _tracked(monkeypatch, baseline, [_square(0, 0, 100)]).assign((300, 300)) is None


def test_a_frame_with_no_target_visible_is_still_lost(monkeypatch):
    """The frame's own contours still gate it: none seen, no evidence from it."""
    assert _tracked(monkeypatch, _view([_square(0, 0, 100)]), []) is None


# --- the Board's edge (#46) ------------------------------------------------

SPAN = 1000.0   # template px a Target span, in these scenes


def _board_scene(edges, frame_size=(800, 600)):
    """A frame 100 px a Target span, ring at (400, 300): textured ground, a
    white Board ending `edges` = (left, right, above, below) spans from the ring,
    the Target print's white border on it and a green Target on that. Returns (frame, H)."""
    rng = np.random.default_rng(1)
    w, h = frame_size
    grey = cv2.GaussianBlur(rng.uniform(40, 140, (h, w)).astype(np.float32), (0, 0), 1.5)
    frame = cv2.cvtColor(grey.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    box = lambda l, r, a, b: ((400 - int(l * 100), 300 - int(a * 100)),
                              (400 + int(r * 100), 300 + int(b * 100)))
    cv2.rectangle(frame, *box(*edges), (215, 215, 215), -1)
    cv2.rectangle(frame, *box(.45, .45, .45, .45), (240, 240, 240), -1)  # the print's border
    cv2.rectangle(frame, *box(.35, .35, .35, .35), (60, 160, 40), -1)    # the Target
    H = board._as_matrix(0.1, np.array([400, 300]) - 0.1 * board.RING_CENTRE_TPL)
    return cv2.GaussianBlur(frame, (0, 0), 1), H


def test_the_board_ends_at_its_first_straight_edge_past_the_targets_print():
    frame, H = _board_scene((1.2, 0.9, 0.8, 1.3))
    edges = board.find_board_edges(frame, H, SPAN)
    ring = board.RING_CENTRE_TPL
    assert edges["left"] == pytest.approx(ring[0] - 1.2 * SPAN, abs=15)
    assert edges["right"] == pytest.approx(ring[0] + 0.9 * SPAN, abs=15)
    assert edges["above"] == pytest.approx(ring[1] - 0.8 * SPAN, abs=15)
    assert edges["below"] == pytest.approx(ring[1] + 1.3 * SPAN, abs=15)


def test_a_board_running_out_of_view_has_no_edge_that_side():
    """The frame's own border is not the Board's edge."""
    frame, H = _board_scene((1.2, 0.9, 0.8, 2.5), frame_size=(800, 420))
    assert board.find_board_edges(frame, H, SPAN)["below"] is None


def test_a_board_past_the_search_has_no_edge_that_side():
    frame, H = _board_scene((1.2, 0.9, 0.8, 2.5), frame_size=(800, 600))
    assert board.find_board_edges(frame, H, SPAN)["below"] is None


def test_the_canvas_grows_to_the_board_edge_within_registration_and_never_shrinks():
    """Past the margin canvas to the Board's edge, cut at `REGION_SPANS` of
    the ring where registration holds; an edge inside the margin, or none,
    leaves the margin canvas as it was."""
    targets = np.float32([[0, 0], [100, 100]])          # ring at (50, 50), span 100
    edges = {"left": -80.0, "right": 120.0, "above": None,
             "below": 50 + 2 * board.REGION_SPANS * 100}   # past the cut
    lo, hi = board.canvas_bounds(targets, edges, ring=(50, 50), span=100)
    margin = board.BOARD_MARGIN * 100
    assert lo == pytest.approx([-80, -margin])
    assert hi == pytest.approx([100 + margin, 50 + board.REGION_SPANS * 100])


# --- dual inference: the margin canvas inside the grown one (#46) ------------

def _margin_formula(targets):
    """The margin canvas, written as `build_view` wrote it before #46."""
    margin = board.BOARD_MARGIN * board.spread(targets)
    lo = targets.min(axis=0) - margin
    return lo, tuple(int(v) for v in np.ceil(targets.max(axis=0) - lo + margin))


def test_with_no_board_edge_the_canvas_is_the_margin_canvas_exactly():
    targets = np.float32([[3.3, 7.7], [140.2, 96.1]])
    layout = board.canvas_layout(targets, dict.fromkeys(board.SIDES), ring=(70, 50), span=137)
    lo, size = _margin_formula(targets)
    assert np.array_equal(layout.lo, lo) and layout.size == size
    assert np.array_equal(layout.inner_lo, lo) and layout.inner_size == size
    assert layout.offset == (0, 0)


def test_growth_up_and_left_is_whole_pixels_so_the_margin_canvas_keeps_its_grid():
    """The margin canvas sits at an integer offset inside the grown one, and
    keeps its exact origin and size; the grown one covers the edges."""
    targets = np.float32([[0, 0], [100, 100]])          # margin canvas -50..150
    edges = {"left": -60.3, "right": None, "above": -55.0, "below": 190.0}
    layout = board.canvas_layout(targets, edges, ring=(50, 50), span=100)
    lo, size = _margin_formula(targets)
    assert np.array_equal(layout.inner_lo, lo) and layout.inner_size == size
    assert layout.offset == (11, 5)
    assert np.allclose(layout.lo, lo - (11, 5))
    assert layout.lo[0] <= -60.3 and layout.lo[1] <= -55.0
    assert layout.lo[1] + layout.size[1] >= 190.0
    assert layout.size[0] == 11 + size[0]                # nothing grew on the right


def _dual_view(offset, inner_size, canvas_size):
    inner_T = board._as_matrix(1.0, (-float(offset[0]), -float(offset[1])))
    return board.BoardView(np.eye(3, dtype=np.float32), board._as_matrix(1.0), canvas_size, [],
                           inner=board.Inner(inner_T, inner_size, offset))


def test_exposed_bands_are_the_growth_plus_their_context():
    view = _dual_view((11, 5), (100, 80), (130, 100))     # margin canvas x 11-111, y 5-85
    assert [b.crop for b in view.exposed_bands(32)] == [(0, 0, 130, 37),     # above
                                                        (0, 53, 130, 100),   # below
                                                        (0, 0, 43, 100),     # left
                                                        (79, 0, 130, 100)]   # right


def test_the_bands_own_the_board_past_the_margin_canvas_once_each():
    """A mark in a corner is in two crops, but reported by one band only."""
    view = _dual_view((11, 5), (100, 80), (130, 100))
    owned = np.zeros((100, 130), int)
    for band in view.exposed_bands(32):
        x0, y0, x1, y1 = band.owns
        owned[y0:y1, x0:x1] += 1
    inner = np.zeros_like(owned, bool); inner[5:85, 11:111] = True
    assert (owned[~inner] == 1).all() and (owned[inner] == 0).all()


def test_a_canvas_that_did_not_grow_has_no_bands():
    assert _dual_view((0, 0), (100, 80), (100, 80)).exposed_bands(32) == []


def test_the_inner_rectification_is_the_margin_canvas_warp_itself():
    """A sees exactly what main saw: the margin canvas's own matrix and size,
    not a crop of the grown canvas."""
    rng = np.random.default_rng(2)
    frame = (rng.random((120, 160, 3)) * 255).astype(np.uint8)
    H = np.float32([[1.1, 0.02, 3], [-0.01, 0.95, 4], [1e-4, 0, 1]])
    inner_T = board._as_matrix(0.8, (-2.3, -1.7))
    view = board.BoardView(H, board._as_matrix(0.8, (8.7, 3.3)), (150, 110), [],
                           inner=board.Inner(inner_T, (120, 90), (11, 5)))
    alone = board.BoardView(H, inner_T, (120, 90), [])
    assert np.array_equal(view.rectify_inner(frame), alone.rectify(frame))
