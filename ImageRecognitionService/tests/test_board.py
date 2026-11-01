"""Checks for Board geometry. No model, no video, no torch."""

import json
import math

import cv2
import numpy as np
import pytest

from detection import board
from tools import ring_landmarks, sheet_fit


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

def test_millimetres_refuses_to_guess_the_print_scale():
    """Everything downstream scales linearly with it, so it must not default."""
    with pytest.raises(board.NotCalibrated, match="no print scale"):
        board.to_millimetres([[0, 0]], _view([]))


def test_a_configured_print_scale_is_read_for_its_capture_setup(tmp_path):
    path = tmp_path / "print_scale.json"
    path.write_text('{"camb": {"mm_per_tpl_px": 0.1763, "source": "#62 fresh print"}}')
    assert board.print_scales(path) == {"camb": 0.1763}


def test_a_print_scale_without_a_source_is_refused(tmp_path):
    path = tmp_path / "print_scale.json"
    path.write_text('{"camb": {"mm_per_tpl_px": 0.1763}}')
    with pytest.raises(ValueError, match="no source"):
        board.print_scales(path)


@pytest.mark.parametrize("bad", ["0", "-0.1763", '"nan"', '"inf"'])
def test_a_print_scale_that_is_not_a_length_is_refused(tmp_path, bad):
    """Zero puts every Bullet Hole on the centre, a negative mirrors them."""
    path = tmp_path / "print_scale.json"
    path.write_text(f'{{"camb": {{"mm_per_tpl_px": {bad}, "source": "typo"}}}}')
    with pytest.raises(ValueError, match="not a finite length"):
        board.print_scales(path)


def test_every_shipped_print_scale_is_valid():
    board.print_scales()


def test_scoring_needs_no_calibration():
    """A score is a ratio inside one picture, so the missing print scale cannot block it."""
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


def test_configured_sheet_matches_the_photographs():
    """Every Capture Setup's sheet rectangle is #271's fit; re-fitting both
    #62 photographs must agree with it to 2 template px (0.35 mm)."""
    rects = [sheet_fit.measure(p)[1] for p in sheet_fit.PHOTOS]
    with open(board.PRINT_SCALE_PATH) as f:
        entries = json.load(f)
    for entry in entries.values():
        assert entry["sheet_source"]
        assert entry["sheet_tpl_px"] == pytest.approx(np.mean(rects, axis=0), abs=2)


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


def test_millimetres_work_once_the_print_scale_is_configured():
    """100 template px right of centre, at 0.2 mm per template px, is 20 mm right."""
    view = _view([], scale=1.0)
    centre = board.RING_CENTRE_TPL
    offset = centre + np.array([100.0, 0])
    mm = board.to_millimetres([centre, offset], view, mm_per_tpl_px=0.2)
    assert mm[0] == pytest.approx([0.0, 0.0])
    assert mm[1] == pytest.approx([20.0, 0.0])


def test_millimetres_are_independent_of_board_scale():
    """Rectifying larger must not change a physical measurement."""
    centre = board.RING_CENTRE_TPL
    offset = centre + np.array([100.0, 0])
    at_one = board.to_millimetres([offset], _view([], scale=1.0), mm_per_tpl_px=0.2)
    at_three = board.to_millimetres([offset * 3], _view([], scale=3.0), mm_per_tpl_px=0.2)
    # abs, not relative: one component is zero, and float32 leaves ~1e-5 mm of
    # noise there. A micron is five thousand times under SOW 2.3.2's budget.
    assert at_one[0] == pytest.approx(at_three[0], abs=1e-3)


def test_physical_y_grows_upward():
    """Image y grows down; a Bullet Hole above centre must read positive."""
    view = _view([])
    above = board.RING_CENTRE_TPL - np.array([0, 100.0])
    assert board.to_millimetres([above], view, mm_per_tpl_px=0.2)[0][1] == pytest.approx(20.0)


def test_a_template_position_survives_template_to_board_and_back():
    """The two conversions are inverses, on a Board space that is neither
    unit-scale nor at the template's origin."""
    view = board.BoardView(H=np.eye(3, dtype=np.float32),
                           tpl_to_board=board._as_matrix(2.5, (40, -30)),
                           canvas_size=(1000, 1000), targets=[])
    position = [[412.0, 287.0]]
    on_board = view.template_to_board(position)
    assert on_board[0] == pytest.approx([1070.0, 687.5])
    assert view.board_to_template(on_board)[0] == pytest.approx(position[0], abs=1e-3)


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
    on_first = board.to_millimetres(point, view, mm_per_tpl_px=0.18, target_index=0)
    on_second = board.to_millimetres(point, view, mm_per_tpl_px=0.18, target_index=1)
    assert np.linalg.norm(on_first[0] - on_second[0]) > 50  # mm


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
    moved = board.apply(W, [[100, 100]])[0]
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
    assert board.apply(W, [[100, 100]])[0] == pytest.approx([105, 97], abs=0.3)


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
    assert board.apply(W, [[225, 120]])[0] == pytest.approx([265, 120], abs=0.05)
    assert correlation > 0.99


def test_track_view_registers_onto_the_baseline_frame_and_chains(monkeypatch):
    """H = W @ H0 against the baseline frame; a tracked view seeds the next."""
    H0 = np.float32([[1, 0, 20], [0, 1, 10], [0, 0, 1]])
    anchor = board.Anchor(_scene() / 255, np.full((240, 320), 255, np.uint8), H0)
    reference = board.BoardView(H0, board._as_matrix(1.0), (300, 300), [], anchor)
    colour = lambda img: cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_GRAY2BGR)

    first, _ = board.track_view(colour(_scene((2.0, 1.0))), reference)
    second, _ = board.track_view(colour(_scene((5.0, -3.0))), first)
    assert board.apply(second.H, [[80, 90]])[0] == pytest.approx([105, 97], abs=0.4)
    assert second.anchor is anchor and second.targets is reference.targets


def test_track_view_follows_a_board_move_past_ecc_s_reach_from_the_last_fit(monkeypatch):
    """#171: a 40, 20 px Board Move since the frame the last fit was registered on.
    Started from that fit, ECC does not converge on this scene; started from it
    plus the shift phase correlation reads between the two frames, it lands."""
    H0 = np.float32([[1, 0, 20], [0, 1, 10], [0, 0, 1]])
    anchor = board.Anchor(_scene() / 255, np.full((240, 320), 255, np.uint8), H0)
    reference = board.BoardView(H0, board._as_matrix(1.0), (300, 300), [], anchor)
    colour = lambda img: cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_GRAY2BGR)

    view, _ = board.track_view(colour(_scene((40.0, 20.0))), reference,
                               previous=colour(_scene()))
    assert board.apply(view.H, [[80, 90]])[0] == pytest.approx([140, 120], abs=0.4)


def _gravel_and_board(board_at, size=(480, 360)):
    """Dense gravel that never moves, and a 200x160 px Board at (140, 100)
    moved by `board_at`, painted over it with a few dark blobs."""
    img = np.full(size[::-1], 200, np.uint8)
    for x, y in np.random.default_rng(0).integers(0, size, (900, 2)):
        cv2.circle(img, (int(x), int(y)), 4, 0, -1)
    x0, y0 = 140 + board_at[0], 100 + board_at[1]
    img[y0:y0 + 160, x0:x0 + 200] = 220
    for x, y in [(30, 30), (150, 40), (60, 120), (170, 130), (100, 80)]:
        cv2.circle(img, (x0 + x, y0 + y), 10, 40, -1)
    return cv2.cvtColor(cv2.GaussianBlur(img, (0, 0), 3), cv2.COLOR_GRAY2BGR)


def test_track_view_reads_the_board_move_on_the_board_not_the_gravel(monkeypatch):
    """#171: when only the Board moves, the shift is read inside the texture
    region where the last fit puts it, 60, 40 px from the baseline frame's.
    The whole frame, or the region left where the baseline frame had it, is
    mostly gravel that stays put, and reads no move: ECC does not converge.
    1 px: this scene's five blobs leave ECC ~0.5 px of play."""
    region = np.zeros((360, 480), np.uint8)
    region[110:250, 150:330] = 255   # inside the Board, clear of the gravel blurred over its edge
    anchor = board.Anchor(board._gray(_gravel_and_board((0, 0))), region, np.eye(3, dtype=np.float32))
    last = np.float32([[1, 0, 60], [0, 1, 40], [0, 0, 1]])
    reference = board.BoardView(last, board._as_matrix(1.0), (300, 300), [], anchor)

    view, _ = board.track_view(_gravel_and_board((100, 60)), reference,
                               previous=_gravel_and_board((60, 40)))
    assert board.apply(view.H, [[0, 0]])[0] == pytest.approx([100, 60], abs=1.0)


def test_re_anchoring_refines_a_silhouette_seed_in_the_same_board_space(monkeypatch):
    """#80: the silhouette fit is only the seed; texture ECC against the baseline
    frame moves it onto the Board, and Board space, the Targets and the anchor
    are the reference's."""
    target = _square(80, 60, 40)
    monkeypatch.setattr(board, "find_targets", lambda frame: ([target], None))
    H0 = np.float32([[1, 0, -600], [0, 1, -560], [0, 0, 1]])   # ring at (95, 79)
    monkeypatch.setattr(board, "register", lambda template_mask, frame_mask, contour:
                        (H0 + np.float32([[0, 0, 10], [0, 0, -5], [0, 0, 0]]), 0.9))
    anchor = board.Anchor(_scene() / 255, np.full((240, 320), 255, np.uint8), H0)
    reference = board.BoardView(H0, board._as_matrix(2.0), (300, 300), [target], anchor)
    colour = lambda img: cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_GRAY2BGR)

    view, _ = board.reanchor_view(colour(_scene((12.0, -7.0))), None, reference)
    assert board.apply(view.H, [[700, 650]])[0] == pytest.approx([112, 83], abs=0.4)
    assert view.anchor is anchor and view.targets is reference.targets
    assert view.tpl_to_board is reference.tpl_to_board
    assert view.canvas_size == reference.canvas_size
    assert view.sheets == reference.sheets and view.crops == reference.crops


def _seeded_fits(monkeypatch, correlations):
    """Contour i seeds a fit converging at `correlations[i]`; None fails to converge."""
    contours = [_square(100 * i, 0, 40) for i in range(len(correlations))]
    monkeypatch.setattr(board, "find_targets", lambda frame: (contours, None))
    monkeypatch.setattr(board, "register", lambda template_mask, frame_mask, contour:
                        (contour, 0.9))
    def track_view(frame, reference, seed):
        corr = correlations[[c is seed for c in contours].index(True)]
        if corr is None:
            raise cv2.error("did not converge")
        return seed, corr
    monkeypatch.setattr(board, "track_view", track_view)
    return contours


def test_re_anchoring_keeps_the_seed_the_board_texture_agrees_with(monkeypatch):
    """The Targets share one artwork: whichever is nearest or largest, the fit
    that matches the baseline frame's texture best is the right one (#80)."""
    contours = _seeded_fits(monkeypatch, [0.55, None, 0.99, 0.20])
    assert board.reanchor_view(None, None, None) == (contours[2], 0.99)


def test_re_anchoring_refuses_a_best_fit_below_the_floor(monkeypatch):
    """Only neighbours in view: the best fit is one Target over, not a re-anchor."""
    _seeded_fits(monkeypatch, [0.55, 0.20])
    assert board.reanchor_view(None, None, None) == (None, None)


def test_re_anchoring_with_no_target_in_view_finds_nothing(monkeypatch):
    monkeypatch.setattr(board, "find_targets", lambda frame: ([], None))
    assert board.reanchor_view(None, None, _view([])) == (None, None)


def _tracked(monkeypatch, reference):
    """`reference` tracked onto a frame, whichever Targets it shows: tracking
    does not look (#276). Sets `reference.anchor` to an identity registration."""
    monkeypatch.setattr(board, "ecc_warp", lambda *a: (np.eye(3, dtype=np.float32), 1.0))
    reference.anchor = board.Anchor(None, None, reference.H)
    return board.track_view(np.zeros((10, 10, 3), np.uint8), reference)[0]


def test_a_bullet_hole_on_a_target_the_frame_lost_is_still_on_that_target(monkeypatch):
    """#33: a shadow hiding Target 2 from the last frame is not a Miss."""
    baseline = _view([_square(0, 0, 100), _square(500, 500, 90)])
    tracked = _tracked(monkeypatch, baseline)
    assert tracked.assign((550, 550)) == 1


def test_target_numbers_are_the_baselines_when_target_1_drops_out(monkeypatch):
    """#33: losing Target 1 does not renumber Target 2 as Target 1."""
    baseline = _view([_square(0, 0, 100), _square(500, 500, 90)])
    tracked = _tracked(monkeypatch, baseline)
    assert tracked.assign((550, 550)) == 1 and tracked.assign((50, 50)) == 0


def test_target_numbers_are_the_baselines_when_two_swap_area_order(monkeypatch):
    """#33: drift that makes Target 2 look the larger does not renumber them."""
    baseline = _view([_square(0, 0, 100), _square(500, 500, 90)])
    tracked = _tracked(monkeypatch, baseline)
    assert tracked.assign((50, 50)) == 0 and tracked.assign((550, 550)) == 1
    assert tracked.ring_centre(1) == pytest.approx(baseline.ring_centre(1))


def test_a_bullet_hole_on_no_target_is_still_a_miss_on_a_tracked_view(monkeypatch):
    """#33 keeps Misses Misses: the baseline's polygons are not widened."""
    baseline = _view([_square(0, 0, 100), _square(500, 500, 90)])
    assert _tracked(monkeypatch, baseline).assign((300, 300)) is None


# --- the Target Sheets (ADR-0011) --------------------------------------------

def test_the_sheet_bound_is_the_configured_sheet_grown_by_5_mm(tmp_path):
    path = tmp_path / "print_scale.json"
    entry = {"mm_per_tpl_px": 0.2, "source": "s", "sheet_tpl_px": [-10, 0, 100, 50]}
    path.write_text(json.dumps({"a": entry, "b": entry}))
    assert board.sheet_bound_tpl(str(path)) == pytest.approx((-35, -25, 125, 75))


def test_setups_on_different_sheets_are_refused(tmp_path):
    """A stream has no Capture Setup to pick a sheet by (ADR-0011)."""
    path = tmp_path / "print_scale.json"
    a = {"mm_per_tpl_px": 0.2, "source": "s", "sheet_tpl_px": [-10, 0, 100, 50]}
    path.write_text(json.dumps({"a": a, "b": {**a, "sheet_tpl_px": [-10, 0, 100, 60]}}))
    with pytest.raises(ValueError, match="2 different sheets"):
        board.sheet_bound_tpl(str(path))


def test_each_target_s_sheet_is_the_reference_s_moved_by_its_centroid():
    """The reference Target, `targets[0]`, through Board space; another the
    same, moved by where its centroid sits against the reference's (#271)."""
    targets = [_square(10, 20, 40), _square(110, 25, 40)]
    sheets = board.sheet_bounds(targets, board._as_matrix(0.5, (3, 4)),
                                bound_tpl=(-20, -10, 120, 100))
    assert sheets[0] == pytest.approx((-7, -1, 63, 54))
    assert sheets[1] == pytest.approx((93, 4, 163, 59))


def test_sheet_canvases_are_one_size_in_multiples_of_32_and_hold_bound_and_context():
    sheets = [(10.4, 20.6, 110.9, 70.2), (200.4, 20.6, 300.9, 70.2)]
    crops = board.sheet_crops(sheets, context=8)
    assert [c[2:] for c in crops] == [(128, 96)] * 2
    for (x0, y0, x1, y1), (x, y, w, h) in zip(sheets, crops):
        assert x <= x0 - 8 and y <= y0 - 8 and x + w >= x1 + 8 - 1 and y + h >= y1 + 8 - 1


def test_a_sheet_canvas_is_the_board_canvas_s_own_pixels():
    """Warped straight from the frame, a sheet canvas is what `rectify` puts
    there, on one Board grid, to the warp's sub-pixel rounding."""
    rng = np.random.default_rng(2)
    frame = (rng.random((120, 160, 3)) * 255).astype(np.uint8)
    H = np.float32([[1.1, 0.02, 3], [-0.01, 0.95, 4], [1e-4, 0, 1]])
    view = board.BoardView(H, board._as_matrix(0.8, (8.7, 3.3)), (150, 110), [],
                           sheets=[(0, 0, 1, 1)] * 2, crops=[(11, 5, 64, 32), (40, 60, 64, 32)])
    whole = view.rectify(frame)
    for canvas, (x, y, w, h) in zip(view.sheet_canvases(frame), view.crops):
        diff = np.abs(canvas.astype(int) - whole[y:y + h, x:x + w])
        assert diff.max() <= 8 and (diff > 0).mean() < 0.01


def test_a_point_is_on_the_first_sheet_whose_bound_holds_it():
    view = board.BoardView(np.eye(3), board._as_matrix(1.0), (100, 100), [],
                           sheets=[(0, 0, 10, 10), (5, 0, 20, 10)])
    got = view.sheet_of([[0, 0], [7, 5], [20, 10], [20.1, 5], [-1, 5]])
    assert got.tolist() == [0, 0, 1, -1, -1]


def test_the_canvas_shift_moves_the_sheets_not_their_canvases():
    """The control moves the Board on fixed canvases (#272): moving both
    would show the detector the same pixels."""
    view = board.BoardView(np.eye(3), board._as_matrix(1.0), (100, 100), [_square(0, 0, 4)],
                           sheets=[(10, 10, 50, 50)], crops=[(0, 0, 64, 64)])
    moved = board.shifted(view, 8)
    assert moved.sheets == [(2, 2, 42, 42)] and moved.crops == view.crops


# --- gross-failure check on a converged fit (#110) ---------------------------

def test_silhouette_disagreement_is_the_reference_target_centres_offset(monkeypatch):
    """An independent silhouette fit 10 frame px right of the tracked one puts
    the reference Target's centre 20 Board px off at board scale 2 (#110)."""
    target = _square(100, 100, 40)
    monkeypatch.setattr(board, "find_targets", lambda frame: ([target], None))
    shifted = np.float32([[1, 0, 10], [0, 1, 0], [0, 0, 1]])
    monkeypatch.setattr(board, "register", lambda template_mask, frame_mask, contour:
                        (shifted, 0.9))
    view = _view([_square(10, 10, 40)], scale=2.0)
    assert board.silhouette_disagreement(None, None, view) == pytest.approx(20.0)


def test_silhouette_disagreement_is_unknown_without_a_silhouette_fit(monkeypatch):
    """A fit that does not converge is no verdict."""
    monkeypatch.setattr(board, "find_targets", lambda frame: ([_square(0, 0, 40)], None))
    def fails(*args):
        raise cv2.error("did not converge")
    monkeypatch.setattr(board, "register", fails)
    assert board.silhouette_disagreement(None, None, _view([_square(0, 0, 40)])) is None


def test_a_fit_on_a_frame_with_no_target_visible_is_grossly_wrong(monkeypatch):
    """`track_view` no longer looks for a Target (#276): with none in view,
    the check calls the fit wrong, so the Look is Lost."""
    monkeypatch.setattr(board, "find_targets", lambda frame: ([], None))
    assert board.silhouette_disagreement(None, None, _view([_square(0, 0, 40)])) == math.inf
