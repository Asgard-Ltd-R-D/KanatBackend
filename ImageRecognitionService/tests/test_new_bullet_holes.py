"""Checks for the new-Bullet-Hole tracker. No model, no video, no torch."""
import numpy as np
from detection import board
from detection.new_bullet_holes import (LIVE_STRIDE, PERSIST_FRAMES, Persistence,
                              _overlap_fraction,
                              change_evidence,
                              merge_displaced_tracks, same_bullet_hole)

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


def _persisted(per_frame, n_frames, match_px, window=PERSIST_FRAMES, lost=()):
    """What persisted over a run: `per_frame` the registered Looks as
    (index, Detections), `lost` the Lost ones, fed to `Persistence` in frame
    order, then `n_frames` passed."""
    persistence = Persistence(match_px, window=window)
    for index, pts in sorted([*per_frame, *((i, None) for i in lost)], key=lambda l: l[0]):
        persistence.add(index, pts)
    return persistence.end(n_frames)


def test_persistent_bullet_hole_is_reported():
    got = _persisted(_looked(range(10, 40), set(range(10, 40))),
                     n_frames=40, match_px=MATCH, window=20)
    assert len(got) == 1
    assert got[0]["first_frame"] == 10
    assert got[0]["persistence"] == 1.0


def test_flickering_detection_is_dropped():
    got = _persisted(_looked(range(10, 40), {10, 13, 19, 25}),
                     n_frames=40, match_px=MATCH, window=20)
    assert got == []


def test_verdict_does_not_depend_on_clip_length():
    """Solid for its window, so it confirms in a short clip and a long one."""
    frames, seen = range(10, 40), set(range(10, 30))
    short = _persisted(_looked(frames, seen), n_frames=40, match_px=MATCH, window=20)
    long_ = _persisted(_looked(range(10, 300), seen), n_frames=300, match_px=MATCH, window=20)
    assert len(short) == len(long_) == 1


def test_unelapsed_window_is_not_reported():
    """A clip ending inside the window must not confirm on the frames that remain.

    Seen in 8 of the 10 frames left — 80%, over the 70% bar — but the window
    needs 20. Shortening the denominator here is what made the verdict depend on
    where the operator stopped recording.
    """
    got = _persisted(_looked(range(30, 40), set(range(30, 38))),
                     n_frames=40, match_px=MATCH, window=20)
    assert got == []


def test_lost_registration_frames_do_not_count_against_a_bullet_hole():
    """Frames absent from per_frame never registered, so they are no evidence.

    Seen in all 10 frames that got a look, out of a 20-frame window where the
    other 10 were lost to registration failure. That is 100%, not 50%.
    """
    frames = list(range(10, 20))          # only these registered
    got = _persisted(_looked(frames, set(frames)), n_frames=40, match_px=MATCH, window=20)
    assert len(got) == 1
    assert got[0]["persistence"] == 1.0


def test_a_window_mostly_lost_to_registration_confirms_nothing():
    """Seen in the only frame of its window that registered: 100% of one look
    is no persistence. Measured on CamA_20260914_150248 once #110 rejected its
    pan frames: two surviving wrong fits confirmed 9 false Bullet Holes on 1-2
    looks each. Under PERSIST of the frames the loop tried to register is
    unconfirmable, not rejected, like a window that has not elapsed. Exactly
    PERSIST still confirms."""
    lone = _persisted(_looked([10], {10}), n_frames=40, match_px=MATCH,
                      window=20, lost=range(11, 30))
    short = list(range(10, 19))           # 9 of 20 registered, all seeing it
    sparse = _persisted(_looked(short, set(short)), n_frames=40,
                        match_px=MATCH, window=20, lost=range(19, 30))
    half = list(range(10, 20))            # 10 of 20
    edge = _persisted(_looked(half, set(half)), n_frames=40,
                      match_px=MATCH, window=20, lost=range(20, 30))
    assert lone == sparse == [] and len(edge) == 1


STRIDE_7 = range(7, 300, 7)   # #81: every 7th frame looked at, the rest never read


def test_stride_gaps_are_not_lost_frames():
    """#81/#82 look at every Nth frame on purpose: 4 looks a 25-frame window
    at stride 7. Frames never read are gaps, not registration failures, so
    the #110 floor does not count them and a persistent Bullet Hole confirms."""
    got = _persisted(_looked(STRIDE_7, set(STRIDE_7)), n_frames=300,
                     match_px=MATCH)
    assert len(got) == 1 and got[0]["persistence"] == 1.0


def test_stride_still_drops_a_flickering_detection():
    seen = set(STRIDE_7[::4])            # 1 look in 4
    assert _persisted(_looked(STRIDE_7, seen), n_frames=300,
                      match_px=MATCH) == []


def test_a_lost_sampled_frame_counts_against_the_floor():
    """At stride 7 a window holds frames 7..31: 4 tries. Three of them lost
    to registration leaves 1 look of 4, under the floor."""
    looked = [7] + list(range(35, 300, 7))
    got = _persisted(_looked(looked, set(looked)), n_frames=300,
                     match_px=MATCH, lost=[14, 21, 28])
    assert all(h["first_frame"] != 7 for h in got)


def test_the_frame_past_the_window_does_not_count():
    """A 50-frame window is [first, first + 50): seen in 25 of frames 0-49 is exactly
    PERSIST, and a look at frame 50 must not join the denominator."""
    frames = [(i, np.array([[100, 100]], np.float32) if i < 25 else np.zeros((0, 2), np.float32))
              for i in range(51)]
    assert len(_persisted(frames, n_frames=51, match_px=MATCH, window=50)) == 1


def test_nearby_detections_merge_into_one_bullet_hole():
    frames = [(i, np.array([[100 + (i % 3), 100 - (i % 2)]], np.float32))
              for i in range(10, 40)]
    assert len(_persisted(frames, n_frames=40, match_px=MATCH, window=20)) == 1


def test_distinct_bullet_holes_stay_distinct():
    frames = [(i, np.array([[100, 100], [200, 200]], np.float32)) for i in range(10, 40)]
    assert len(_persisted(frames, n_frames=40, match_px=MATCH, window=20)) == 2


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
    assert len(_persisted(frames, n_frames=40, match_px=FLOOR, window=20)) == 2


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
    from detection import new_bullet_holes
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
    assert _persisted(looked, n_frames=40, match_px=MATCH, window=20) == []
    # ... and the same evidence against the requested count wrongly confirms it.
    assert len(_persisted(looked, n_frames=300, match_px=MATCH, window=20)) == 1


def test_two_boxes_on_one_mark_in_one_frame_count_as_one_frame():
    """Persistence counts frames the Bullet Hole was seen in, not sightings.

    Two detections close enough to be one Bullet Hole both fold into the same
    candidate, so the frame was counted twice. Seen in 6 of the window's 20
    frames — 30%, under the 50% bar — but with two boxes in each, the old count
    made 12 and confirmed it.

    The two centres here are well inside the gate, which is the minimal shape of
    the bug rather than CamB's geometry: CamB's halves sit 6.2 px apart against a
    5.25 px gate and fold together only once the running mean drifts them into
    range, which is why CamB's scored window did not move when this was fixed.
    See `test_camb_split_is_not_merged_by_the_gate_alone`.
    """
    split = np.array([[100.0, 100.0], [100.5, 100.0]], np.float32)
    per_frame = [(i, split if i < 16 else np.zeros((0, 2), np.float32))
                 for i in range(10, 40)]
    assert _persisted(per_frame, n_frames=40, match_px=MATCH, window=20) == []


def test_every_frame_is_recorded_once_however_many_boxes_it_held():
    split = np.array([[100.0, 100.0], [100.5, 100.0]], np.float32)
    got = _persisted([(i, split) for i in range(10, 40)],
                     n_frames=40, match_px=MATCH, window=20)
    assert len(got) == 1
    assert got[0]["seen"] == list(range(10, 40))
    assert got[0]["persistence"] == 1.0


def _judged_at(persistence, looks):
    """The Looks of `looks`, (index, Detections), whose `add` returned a Candidate."""
    return [index for index, pts in looks if persistence.add(index, pts)]


def test_a_clean_candidate_persists_before_its_window_ends():
    """Stride 5, window [10, 30): Looks 10, 15, 20, 25. Seen at 10 and 15,
    it has 2 of 4 whatever 20 and 25 bring, so it persists at 15 (ADR-0003,
    amended 2026-10-28)."""
    persistence = Persistence(MATCH, window=20, stride=5)
    looks = _looked(range(10, 50, 5), set(range(10, 50, 5)))
    assert _judged_at(persistence, looks) == [15]


def test_a_clean_live_candidate_is_fixed_on_its_4th_look():
    """The production window at LIVE_STRIDE: 25 frames hold 7 Looks, 4
    needed, so a Candidate seen on every Look is fixed on the 4th, 12 frames
    (480 ms) after the first (#314, ADR-0003 amended 2026-11-08). Written
    out, not derived: a change to the window, the stride or the 50% bar
    fails here instead of moving latency silently. At 40 frames it is the
    5th; at 50, the 7th."""
    persistence = Persistence(MATCH, stride=LIVE_STRIDE)
    looks = _looked(range(100, 200, 4), set(range(100, 200, 4)))
    assert _judged_at(persistence, looks) == [112]


def test_a_marginal_candidate_persists_only_at_its_windows_last_look():
    """Seen at 10 and 25 of 10, 15, 20, 25: 50%, and not certain of it until
    25, the window's last due Look."""
    persistence = Persistence(MATCH, window=20, stride=5)
    assert _judged_at(persistence, _looked(range(10, 50, 5), {10, 25})) == [25]


def test_a_candidate_on_three_of_five_persists_only_once_the_third_is_in():
    """Stride 4, window [12, 32): Looks 12-28. Seen at 12, 20 and 28, 60%:
    two of five are never enough, so nothing is certain before 28."""
    persistence = Persistence(MATCH, window=20, stride=4)
    assert _judged_at(persistence, _looked(range(12, 48, 4), {12, 20, 28})) == [28]


def test_without_the_stride_every_frame_counts_as_due_and_end_judges():
    """Not told the stride, `Persistence` takes frames 26-29 as due Looks
    still to come, so it errs late: nothing is certain at the last Look, 25,
    and `end` judges it once they have passed."""
    persistence = Persistence(MATCH, window=20)
    assert _judged_at(persistence, _looked(range(10, 30, 5), {10, 25})) == []
    assert [h["first_frame"] for h in persistence.end(30)] == [10]


def test_an_early_verdict_whose_window_never_passes_is_not_reported():
    """Persisted at 39 on 10 of 20, but the clip ends at 40: on a recording
    it is unconfirmable as before, so `end` leaves it out."""
    persistence = Persistence(MATCH, window=20)
    assert _judged_at(persistence, _looked(range(30, 40), set(range(30, 40)))) == [39]
    assert persistence.end(40) == []


def test_rejection_still_waits_for_the_window_and_unjudged_counts_the_open():
    """A flicker opened at 10 and a clean mark at 12: the clean one persists
    at 21 and leaves the other open, out of order, until its window has
    passed at 29. Rejected then, never before."""
    persistence = Persistence(MATCH, window=20)
    flicker, clean = np.float32([[100, 100]]), np.float32([[300, 300]])
    open_after = {}
    for index in range(10, 40):
        pts = np.concatenate([flicker if index == 10 else flicker[:0],
                              clean if index >= 12 else clean[:0]])
        if persistence.add(index, pts):
            assert index == 21
        open_after[index] = persistence.unjudged
    assert open_after[10] == 1 and open_after[20] == 2 and open_after[21] == 1
    assert open_after[28] == 1 and open_after[29] == 0
    assert [h["first_frame"] for h in persistence.end(40)] == [12]


def test_a_known_gap_ahead_is_not_also_counted_as_a_look_to_come():
    """Seen 10-19 of window [10, 30), and the stream reports 20-29 unseen
    before the Look at 19 is judged: 10 of 20 tried, decided at 19. Counted
    as Looks to come as well, they kept it open past its last Look."""
    unseen = []
    persistence = Persistence(MATCH, window=20, unseen=unseen)
    looks = _looked(range(10, 20), set(range(10, 20)))
    assert _judged_at(persistence, looks[:-1]) == []
    unseen += range(20, 30)
    assert _judged_at(persistence, looks[-1:]) == [19]


class _GapWhileJudging(list):
    """`unseen` that the stream extends with 20-29 at its first read, as its
    thread can while a Look is judged."""
    armed = False

    def __getitem__(self, i):
        if self.armed:
            self.armed = False
            self.extend(range(20, 30))
        return super().__getitem__(i)


def test_a_gap_reported_while_judging_is_counted_once():
    """The test above with the gap landing mid-judgement: both counts see it
    or neither does, so it is still decided at 19, not left open."""
    unseen = _GapWhileJudging([5])
    persistence = Persistence(MATCH, window=20, unseen=unseen)
    looks = _looked(range(10, 20), set(range(10, 20)))
    assert _judged_at(persistence, looks[:-1]) == []
    unseen.armed = True
    assert _judged_at(persistence, looks[-1:]) == [19]


def test_a_stream_jump_past_the_window_charges_nothing_beyond_it():
    """Window [10, 30), Looked at 10-20 and seen 10-15, then the stream
    reports 21-39 unseen and resumes at 40: 6 of 11 Looks, so it persists at
    40. The gap past 30 once counted as Looks still to come and rejected it."""
    unseen = []
    persistence = Persistence(MATCH, window=20, unseen=unseen)
    assert _judged_at(persistence, _looked(range(10, 21), set(range(10, 16)))) == []
    unseen += range(21, 40)
    assert _judged_at(persistence, _looked([40], set())) == [40]


def _end_of_window_verdict(outcomes, persist=0.5):
    """Today's rule, written out on its own: `outcomes` is the window's due
    frames, each seen, empty, lost, unseen or late_drop (#84, counting for
    nothing)."""
    span = sum(o in ("seen", "empty") for o in outcomes)
    tried = span + sum(o in ("lost", "unseen") for o in outcomes)
    hits = outcomes.count("seen")
    return span > 0 and span >= persist * tried and hits / span >= persist


def test_the_early_verdict_is_the_end_of_window_verdict():
    """Over generated windows of Lost Looks, stream gaps, late drops and
    strides: what persists early is what the window's end persists, it is
    never reported twice, and `unjudged` is 1 exactly until it is decided."""
    rng = np.random.default_rng(278)
    kinds = ("seen", "empty", "lost", "unseen", "late_drop")
    early = 0
    for _ in range(3000):
        stride, window = int(rng.integers(1, 8)), int(rng.integers(5, 51))
        baseline_frames = int(rng.integers(0, 6))
        first = stride * int(rng.integers(2, 6))
        due = [i for i in range(first, first + window) if i % stride == 0]
        outcomes = ["seen"] + list(rng.choice(kinds, len(due) - 1,
                                              p=rng.dirichlet(np.ones(5))))
        unseen = []
        persistence = Persistence(MATCH, window=window, unseen=unseen, stride=stride,
                                  baseline_frames=baseline_frames)
        reported = []
        for index, outcome in zip(due, outcomes):
            if outcome == "unseen":
                unseen.append(index)   # the stream extends it before the next Look
                continue
            if outcome == "late_drop":
                continue
            pts = (None if outcome == "lost" else
                   _looked([index], {index} if outcome == "seen" else set())[0][1])
            got = persistence.add(index, pts)
            reported += got
            assert persistence.unjudged == (not reported and index + 1 < first + window)
        # A Look past the window judges what the last due ones left open.
        reported += persistence.add(first + window + stride * 3, np.zeros((0, 2), np.float32))
        final = persistence.end(first + window + stride * 4)
        expected = _end_of_window_verdict(outcomes)
        assert len(reported) == expected and len(final) == expected
        assert persistence.unjudged == 0
        early += bool(reported) and reported[0]["judged_frame"] < due[-1]
    assert early > 100   # the rule did report early, not only at the end


def test_end_gives_the_final_position_and_sightings_not_those_at_judgement():
    """Judged at the Look at 19, then seen 2 px over for 20 more Looks: `end`
    and `position` give where the running mean ended, and every sighting."""
    persistence = Persistence(MATCH, window=20)
    judged = []
    for index in range(10, 40):
        x = 100.0 if index < 20 else 102.0
        judged += persistence.add(index, np.array([[x, 100.0]], np.float32))
    (at_judgement,) = judged
    pos, seen = at_judgement["pos"].copy(), list(at_judgement["seen"])
    (final,) = persistence.end(40)
    assert seen == list(range(10, 20)) and final["seen"] == list(range(10, 40))
    assert pos[0] == 100.0 and final["pos"][0] > 100.0
    assert np.array_equal(persistence.position(final)[:2], final["pos"])


def test_a_place_whose_candidate_was_rejected_is_judged_again_from_its_next_detection():
    """A blip at 10 is rejected over [10, 30); the Bullet Hole seen on every
    Look from 40 then opens a Candidate of its own and persists. Folded into
    the rejected one, as before #259, it was never reported."""
    got = _persisted(_looked(range(10, 70), {10, *range(40, 70)}),
                     n_frames=70, match_px=MATCH, window=20)
    assert [h["first_frame"] for h in got] == [40]


def test_a_place_whose_candidate_was_unconfirmable_is_judged_again_from_its_next_detection():
    """Seen at 10, then Lost to 29: 1 of 20 frames tried registered, under the
    floor, so [10, 30) is unconfirmable (#110). No evidence either way, so the
    Bullet Hole seen on every Look from 40 opens a Candidate and persists."""
    got = _persisted(_looked([10, *range(30, 70)], {10, *range(40, 70)}),
                     n_frames=70, match_px=MATCH, window=20, lost=range(11, 30))
    assert [h["first_frame"] for h in got] == [40]


def test_the_first_look_past_a_window_that_did_not_persist_opens_the_next_candidate():
    """Looks every 5 frames: the blip at 10 is seen on 1 of the 4 Looks in
    [10, 30), and the Bullet Hole on every Look from 30. The window has ended
    by the Look at 30, so that Look's Detection starts the next Candidate
    rather than folding into the one about to be rejected (#259)."""
    got = _persisted(_looked(range(10, 70, 5), {10, *range(30, 70, 5)}),
                     n_frames=70, match_px=MATCH, window=20)
    assert [h["first_frame"] for h in got] == [30]


def test_a_window_judged_ahead_of_a_look_is_judged_at_that_look():
    """Looks every 5 frames, every frame due: seen at 10, 15 and 20, not 25,
    so at 25 the 4 due frames still to come could undo it. [10, 30) has ended
    by the Look at 30, which judges it before folding: it is reported at that
    Look, not at 29, a frame never looked at."""
    got = _persisted(_looked(range(10, 70, 5), {10, 15, 20}),
                     n_frames=70, match_px=MATCH, window=20)
    assert [h["judged_frame"] for h in got] == [30]


def test_a_persisted_candidate_still_absorbs_its_place_s_later_detections():
    """Persisted over [10, 30), then unseen, then seen again from 40: the
    later sightings fold into the reported Bullet Hole, not a second one."""
    got = _persisted(_looked(range(10, 70), {*range(10, 30), *range(40, 70)}),
                     n_frames=70, match_px=MATCH, window=20)
    assert [h["first_frame"] for h in got] == [10]
    assert got[0]["seen"][-1] == 69


# --- Change Evidence on the sheet canvases (ADR-0011) ------------------------

def test_a_point_is_judged_on_the_change_mask_of_its_own_sheet_canvas(monkeypatch):
    """Each sheet canvas has its own mask, read at the point's px on it."""
    view = board.BoardView(np.eye(3), board._as_matrix(1.0), (300, 100), [],
                           sheets=[(10, 10, 90, 90), (110, 10, 190, 90)],
                           crops=[(0, 0, 100, 100), (100, 0, 100, 100)])
    marked = lambda x, y: (lambda m: (m.__setitem__((y, x), 255), m)[1])(
        np.zeros((100, 100), np.uint8))
    masks = {"a": marked(40, 40), "b": marked(20, 60)}
    monkeypatch.setattr(board, "changed_regions", lambda before, now: masks[now])
    pts = np.array([[40.0, 40.0], [120.0, 60.0], [140.0, 40.0]])
    assert change_evidence(pts, view, ["-", "-"], ["a", "b"], radius=1.0) == [True, True, False]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok  {name}")

