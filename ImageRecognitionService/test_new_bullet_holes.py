"""Checks for the new-Bullet-Hole tracker. No model, no video, no torch."""
import numpy as np
from new_bullet_holes import (_overlap_fraction, merge_displaced_tracks,
                              same_bullet_hole, track_new_bullet_holes)

MATCH = 22.0  # Board-space px; the tracker takes it from BoardView.match_radius

# Measured off the two labelled clips, Board-space px, as (cx, cy, w, h).
#
# CAMB_SPLIT is ONE torn mark that the detector boxes as two halves — operator
# ground truth labels it once. CAMA_PAIR is the closest pair of genuinely
# distinct Bullet Holes in the CamA clip. They sit 0.59x and 0.74x of the mean
# box diagonal apart, which is the whole difficulty: the gap between "one mark
# split" and "two real marks" is narrow, and these are the numbers that define
# it.
CAMB_SPLIT = ((148.1, 210.2, 7.3, 7.5), (154.2, 209.1, 7.1, 7.8))   # 0.59x
CAMA_PAIR = ((100.0, 100.0, 17.4, 17.4), (118.1, 100.0, 17.4, 17.4))  # 0.74x
FLOOR = 2.96  # CamB's BoardView.match_radius: a constant in template px, and
              # smaller than the 13.4 px mark it was being asked to merge


def _looked(frames, seen):
    """Frames that registered, with a detection on those in `seen`.

    Every registered frame must appear, empty or not — that is what the
    persistence denominator counts.
    """
    return [(i, np.array([[100.0, 100.0]], np.float32) if i in seen
                else np.zeros((0, 2), np.float32))
            for i in frames]


def test_persistent_bullet_hole_is_reported():
    got = track_new_bullet_holes(_looked(range(10, 40), set(range(10, 40))),
                                 n_frames=40, match_px=MATCH, window=20)
    assert len(got) == 1
    assert got[0]["first_frame"] == 10
    assert got[0]["persistence"] == 1.0


def test_flickering_detection_is_dropped():
    got = track_new_bullet_holes(_looked(range(10, 40), {10, 13, 19, 25}),
                                 n_frames=40, match_px=MATCH, window=20)
    assert got == []


def test_verdict_does_not_depend_on_clip_length():
    """Solid for its window, so it confirms in a short clip and a long one."""
    frames, seen = range(10, 40), set(range(10, 30))
    short = track_new_bullet_holes(_looked(frames, seen), n_frames=40, match_px=MATCH, window=20)
    long_ = track_new_bullet_holes(_looked(range(10, 300), seen), n_frames=300, match_px=MATCH, window=20)
    assert len(short) == len(long_) == 1


def test_unelapsed_window_is_not_reported():
    """A clip ending inside the window must not confirm on the frames that remain.

    Seen in 8 of the 10 frames left — 80%, over the 70% bar — but the window
    needs 20. Shortening the denominator here is what made the verdict depend on
    where the operator stopped recording.
    """
    got = track_new_bullet_holes(_looked(range(30, 40), set(range(30, 38))),
                                 n_frames=40, match_px=MATCH, window=20)
    assert got == []


def test_lost_registration_frames_do_not_count_against_a_bullet_hole():
    """Frames absent from per_frame never registered, so they are no evidence.

    Seen in all 10 frames that got a look, out of a 20-frame window where the
    other 10 were lost to registration failure. That is 100%, not 50%.
    """
    frames = list(range(10, 20))          # only these registered
    got = track_new_bullet_holes(_looked(frames, set(frames)), n_frames=40, match_px=MATCH, window=20)
    assert len(got) == 1
    assert got[0]["persistence"] == 1.0


def test_nearby_detections_merge_into_one_bullet_hole():
    frames = [(i, np.array([[100 + (i % 3), 100 - (i % 2)]], np.float32))
              for i in range(10, 40)]
    assert len(track_new_bullet_holes(frames, n_frames=40, match_px=MATCH, window=20)) == 1


def test_distinct_bullet_holes_stay_distinct():
    frames = [(i, np.array([[100, 100], [200, 200]], np.float32)) for i in range(10, 40)]
    assert len(track_new_bullet_holes(frames, n_frames=40, match_px=MATCH, window=20)) == 2


def test_centres_inside_the_floor_are_one_bullet_hole():
    """The template-px floor still decides on its own, boxes or no boxes."""
    assert same_bullet_hole((100.0, 100.0, 7.0, 7.0), (101.0, 100.5, 7.0, 7.0), FLOOR)


def test_centres_only_input_keeps_the_old_floor_only_behaviour():
    """Callers without a box — and the tracker's own tests — must be unaffected."""
    assert same_bullet_hole((100.0, 100.0), (101.0, 100.5), FLOOR)
    assert not same_bullet_hole((100.0, 100.0), (104.0, 100.0), FLOOR)


def test_nested_boxes_are_one_bullet_hole():
    """A small box inside a large one: overlap merges what distance would not.

    Centres are 9 px apart against a 2.96 px floor and a centre gate of
    0.5 x mean diagonal, so only the overlap arm can fire.
    """
    big, small = (100.0, 100.0, 40.0, 40.0), (109.0, 100.0, 8.0, 8.0)
    assert _overlap_fraction(big, small) > 0.5
    assert same_bullet_hole(big, small, FLOOR)


def test_boxes_that_do_not_touch_are_two_bullet_holes():
    a, b = (100.0, 100.0, 7.0, 7.0), (140.0, 100.0, 7.0, 7.0)
    assert _overlap_fraction(a, b) == 0.0
    assert not same_bullet_hole(a, b, FLOOR)


def test_real_bullet_holes_a_diagonal_apart_stay_distinct():
    """CamA's closest genuinely distinct pair, 0.74x diagonal.

    Merging these is a false negative, and ADR-0003 is explicit that whatever
    gates sameness bounds recall. Raising DUP_CENTER_FACTOR to 0.6 regressed
    this clip from F1 0.92 to 0.83, which is why 0.5 was left alone.
    """
    a, b = CAMA_PAIR
    assert not same_bullet_hole(a, b, FLOOR)
    frames = [(i, np.array([a, b], np.float32)) for i in range(10, 40)]
    assert len(track_new_bullet_holes(frames, n_frames=40, match_px=FLOOR, window=20)) == 2


def test_camb_split_is_not_merged_by_the_gate_alone():
    """Characterisation, not an endorsement. READ THIS BEFORE RETUNING.

    These two boxes are one torn Bullet Hole, and the full-clip run does report
    them as one — but NOT because this gate fires. At 0.5 the gate wants 5.25 px
    and the centres are 6.2 px apart. The clip-level merge comes from the
    candidate's running mean drifting into range over 275 frames, which is luck,
    not a property.

    Closing it honestly needs a factor of 0.59, and 0.6 regresses CamA (above).
    The two windows do not overlap on the data that exists. That is a finding
    for the held-out test set, not something to paper over by nudging a constant.
    """
    a, b = CAMB_SPLIT
    assert not same_bullet_hole(a, b, FLOOR)


class _Reference:
    """Just the one attribute merge_displaced_tracks reads off a BoardView."""
    def __init__(self, centre):
        self.targets = [np.array([centre], np.float32).reshape(-1, 1, 2)]


# CamB's Target 1 centroid, and the two positions one mark was reported at.
CAMB_REF = _Reference((170.0, 158.0))
DISPLACED_A = np.array([158.1, 53.9], np.float32)   # seen in 306 of 363 frames
DISPLACED_B = np.array([152.3, 27.5], np.float32)   # seen in 49, never alongside


def _hole(pos, seen):
    return {"pos": np.asarray(pos, np.float32), "box": np.asarray(pos, np.float32),
            "first_frame": min(seen), "seen": sorted(seen), "persistence": 1.0}


def test_displaced_sighting_is_folded_into_the_earlier_bullet_hole():
    """CamB #5/#6: 0 co-occurrences in 363 frames, 27 Board px apart.

    The excursion sits inside the real track's lifetime — A, then B while A is
    absent, then A again — which is what registration displacement looks like.
    """
    a = _hole(DISPLACED_A, list(range(780, 950)) + list(range(1000, 1150)))
    b = _hole(DISPLACED_B, list(range(950, 999)))
    kept, merged = merge_displaced_tracks([a, b], CAMB_REF)
    assert len(kept) == 1 and kept[0] is a
    assert merged == [(a, b)]


def test_bullet_holes_that_co_occur_are_never_merged():
    """Two genuine Bullet Holes are detected together. That alone settles it."""
    a = _hole(DISPLACED_A, list(range(780, 1150)))
    b = _hole(DISPLACED_B, list(range(950, 1150)))
    kept, merged = merge_displaced_tracks([a, b], CAMB_REF)
    assert len(kept) == 2 and merged == []


def test_a_later_mark_after_the_first_is_gone_is_not_merged():
    """Never co-occurring is not enough: a mark covered up, and a later
    unrelated one, never co-occur either. The spans must overlap."""
    a = _hole(DISPLACED_A, list(range(100, 300)))
    b = _hole(DISPLACED_B, list(range(800, 1000)))
    kept, merged = merge_displaced_tracks([a, b], CAMB_REF)
    assert len(kept) == 2 and merged == []


def test_displacement_too_large_for_its_distance_is_not_merged():
    """The bound scales with distance from the Target, because that is how
    registration error grows. A jump far beyond it is two marks, not one."""
    a = _hole((158.1, 53.9), list(range(780, 950)) + list(range(1000, 1150)))
    b = _hole((158.1, 153.9), list(range(950, 999)))   # 100 px, way past 0.35x
    kept, merged = merge_displaced_tracks([a, b], CAMB_REF)
    assert len(kept) == 2 and merged == []


def test_merge_is_off_unless_asked_for():
    """It is a candidate mitigation, not production behaviour."""
    import new_bullet_holes
    assert new_bullet_holes.NON_COOCCURRENCE_MERGE is False

def test_a_truncated_run_does_not_confirm_on_frames_it_never_read():
    """A short read shortens the timeline, not just the evidence.

    The clip was asked for 300 frames and delivered 40. A candidate first seen
    at frame 30 has 10 frames of the window inside what was actually read, and
    confirming it on those would be the clip-length dependence the fixed window
    exists to remove — except manufactured by a truncated read rather than by
    where the operator stopped recording. `process` therefore passes the frames
    it actually read, not the frames it asked for.
    """
    looked = _looked(range(30, 40), set(range(30, 40)))
    assert track_new_bullet_holes(looked, n_frames=40, match_px=MATCH, window=20) == []
    # ... and the same evidence against the requested count wrongly confirms it.
    assert len(track_new_bullet_holes(looked, n_frames=300, match_px=MATCH, window=20)) == 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok  {name}")
