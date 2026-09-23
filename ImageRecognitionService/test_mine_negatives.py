"""Checks for the background-negative miner.

Pure functions over synthetic canvases and a hand-built manifest: no video, no
model. The two rules that matter most are the ones a mistake here breaks
silently — a sealed recording's pixels reaching a checkpoint (ADR-0005), and a
real Bullet Hole reaching an image whose label file says there is none.
"""
import cv2
import numpy as np
import pytest

from manifest import NotInManifest, SEALED, SPENT, THRESHOLD_WORK
from mine_negatives import (ground_mask, near_duplicate, pad_to_tile, pick_tiles,
                            refuse_sealed, sample_step, thumbnail,
                            to_negative, usable_fit)

GRAVEL = (40, 80, 110)    # BGR: warm brown, hue ~17 as measured on CamA
PAPER = (170, 140, 120)   # BGR: bluish white, hue ~108 as measured on CamA

MANIFEST = {
    "a" * 64: {"file": "spent.mkv", "capture_setup": "cama", "role": SPENT},
    "b" * 64: {"file": "tw.mkv", "capture_setup": "camb", "role": THRESHOLD_WORK},
    "c" * 64: {"file": "sealed.mkv", "capture_setup": "camw", "role": SEALED},
}


def board_on_gravel():
    """400x400 canvas: gravel with dark specks, the Board on the left half
    carrying a Bullet Hole and a warm smudge, and black warp padding at the top."""
    canvas = np.full((400, 400, 3), GRAVEL, np.uint8)
    rng = np.random.default_rng(0)
    for x, y in rng.integers(210, 390, (40, 2)):
        cv2.circle(canvas, (int(x), int(y)), 3, (15, 20, 25), -1)   # gravel specks
    canvas[:, :200] = PAPER
    cv2.circle(canvas, (100, 200), 6, (10, 10, 10), -1)             # a Bullet Hole
    cv2.circle(canvas, (60, 300), 8, GRAVEL, -1)                    # splinter-brown smudge
    cv2.circle(canvas, (195, 120), 5, (10, 10, 10), -1)             # Bullet Hole at the Board's edge
    canvas[:40] = 0
    return canvas


def test_spent_and_threshold_work_footage_may_be_mined():
    assert refuse_sealed(MANIFEST, "a" * 64)["role"] == SPENT
    assert refuse_sealed(MANIFEST, "b" * 64)["role"] == THRESHOLD_WORK


def test_sealed_footage_is_refused_and_there_is_no_flag_to_allow_it():
    """A final run measures once; mining trains on it, and a checkpoint cannot
    un-see it. So unlike scoring, no `--final-run` opens it."""
    with pytest.raises(SystemExit) as why:
        refuse_sealed(MANIFEST, "c" * 64)
    assert "sealed" in str(why.value).lower()
    assert "--final-run" not in str(why.value)


def test_an_unallocated_recording_is_refused():
    with pytest.raises(NotInManifest):
        refuse_sealed(MANIFEST, "d" * 64)


def test_ground_is_gravel_and_never_paper_or_padding():
    ground = ground_mask(board_on_gravel())
    assert ground[200:, 300:].all(), "open gravel is ground"
    assert not ground[:, :200].any(), "the Board is not ground"
    assert not ground[:40].any(), "warp padding is not ground"


def test_dark_specks_on_gravel_stay_in_the_negative():
    """They are the whole point: what the detector mistakes for Bullet Holes."""
    canvas = board_on_gravel()
    ground = ground_mask(canvas)
    specks = canvas.max(axis=2) < 40
    specks[:200] = specks[:, :230] = False   # the gravel, clear of padding and Board
    assert specks.any() and ground[specks].all()


def test_no_board_pixel_survives_into_a_negative():
    """Both Bullet Holes — one at the Board's edge — and the brown smudge on
    the Board are all blacked out; an empty label file must be true of the image."""
    negative = to_negative(board_on_gravel())
    assert not negative[:, :200].any()
    assert not negative[110:131, 185:206].any()


def test_tiles_favour_the_most_ground():
    ground = np.zeros((1000, 1000), bool)
    ground[:, 700:] = True
    tiles = pick_tiles(ground, size=400, min_fraction=0.25)
    assert tiles[0][0] == 600, "the tile flush with the gravel strip comes first"
    assert all(fraction >= 0.25 for *_, fraction in tiles)
    assert tiles == sorted(tiles, key=lambda t: -t[2])


def test_tiles_do_not_mostly_overlap():
    ground = np.ones((1000, 1000), bool)
    tiles = pick_tiles(ground, size=400, min_fraction=0.25)
    for i, (xa, ya, _) in enumerate(tiles):
        for xb, yb, _ in tiles[i + 1:]:
            overlap = max(0, 400 - abs(xa - xb)) * max(0, 400 - abs(ya - yb))
            assert overlap <= 400 * 400 / 2


def test_a_canvas_with_no_ground_yields_no_tile():
    assert pick_tiles(np.zeros((300, 300), bool), size=960, min_fraction=0.25) == []


def test_a_canvas_smaller_than_a_tile_is_one_tile_of_its_own_size():
    tiles = pick_tiles(np.ones((300, 500), bool), size=960, min_fraction=0.25)
    assert tiles == [(0, 0, 1.0)]


def test_a_small_tile_is_padded_black_never_scaled():
    tile = np.full((300, 500, 3), GRAVEL, np.uint8)
    padded = pad_to_tile(tile, size=960)
    assert padded.shape == (960, 960, 3)
    assert (padded[:300, :500] == tile).all()
    assert not padded[300:].any() and not padded[:, 500:].any()


def test_a_static_camera_does_not_repeat_itself():
    tile = board_on_gravel()
    noisy = cv2.add(tile, np.full_like(tile, 2))
    kept = [thumbnail(tile)]
    assert near_duplicate(thumbnail(noisy), kept, max_mad=6.0)
    assert not near_duplicate(thumbnail(np.roll(tile, 60, axis=1)), kept, max_mad=6.0)
    assert not near_duplicate(thumbnail(tile), [], max_mad=6.0)


def test_sampling_is_sparse_and_covers_the_clip():
    assert sample_step(fps=25.0, step_s=1.0) == 25
    assert sample_step(fps=10.0, step_s=0.01) == 1


def test_a_rock_inside_the_gravel_is_not_mistaken_for_board():
    """A dark rock wider than the closing kernel is still gravel, and exactly
    the kind of thing the detector mistakes for a Bullet Hole."""
    canvas = board_on_gravel()
    cv2.circle(canvas, (300, 300), 20, (15, 20, 25), -1)
    assert ground_mask(canvas)[280:321, 280:321].all()


def test_a_board_surrounded_by_gravel_is_still_board():
    """Only small enclosures are filled; a Board ringed by gravel keeps its
    Bullet Holes out of the negative."""
    canvas = np.full((600, 600, 3), GRAVEL, np.uint8)
    canvas[150:450, 150:450] = PAPER
    cv2.circle(canvas, (300, 300), 6, (10, 10, 10), -1)
    assert not to_negative(canvas)[150:450, 150:450].any()


def test_a_fit_that_found_no_target_artwork_is_no_board():
    """The legacy clips carry no green Target; the hue gate latches onto
    dirt and ECC 'converges' at 0.28-0.47, against 0.95-0.99 on Kanat footage."""
    assert not usable_fit((313, 314), 0.47)
    assert usable_fit((313, 314), 0.95)
    assert not usable_fit((5000, 900), 0.99)
