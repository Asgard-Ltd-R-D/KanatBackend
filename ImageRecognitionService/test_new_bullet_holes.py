"""Checks for the new-Bullet-Hole tracker. No model, no video, no torch."""
import numpy as np
from new_bullet_holes import track_new_bullet_holes


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
                                 n_frames=40, window=20)
    assert len(got) == 1
    assert got[0]["first_frame"] == 10
    assert got[0]["persistence"] == 1.0


def test_flickering_detection_is_dropped():
    got = track_new_bullet_holes(_looked(range(10, 40), {10, 13, 19, 25}),
                                 n_frames=40, window=20)
    assert got == []


def test_verdict_does_not_depend_on_clip_length():
    """Solid for its window, so it confirms in a short clip and a long one."""
    frames, seen = range(10, 40), set(range(10, 30))
    short = track_new_bullet_holes(_looked(frames, seen), n_frames=40, window=20)
    long_ = track_new_bullet_holes(_looked(range(10, 300), seen), n_frames=300, window=20)
    assert len(short) == len(long_) == 1


def test_unelapsed_window_is_not_reported():
    """A clip ending inside the window must not confirm on the frames that remain.

    Seen in 8 of the 10 frames left — 80%, over the 70% bar — but the window
    needs 20. Shortening the denominator here is what made the verdict depend on
    where the operator stopped recording.
    """
    got = track_new_bullet_holes(_looked(range(30, 40), set(range(30, 38))),
                                 n_frames=40, window=20)
    assert got == []


def test_lost_registration_frames_do_not_count_against_a_bullet_hole():
    """Frames absent from per_frame never registered, so they are no evidence.

    Seen in all 10 frames that got a look, out of a 20-frame window where the
    other 10 were lost to registration failure. That is 100%, not 50%.
    """
    frames = list(range(10, 20))          # only these registered
    got = track_new_bullet_holes(_looked(frames, set(frames)), n_frames=40, window=20)
    assert len(got) == 1
    assert got[0]["persistence"] == 1.0


def test_nearby_detections_merge_into_one_bullet_hole():
    frames = [(i, np.array([[100 + (i % 3), 100 - (i % 2)]], np.float32))
              for i in range(10, 40)]
    assert len(track_new_bullet_holes(frames, n_frames=40, window=20)) == 1


def test_distinct_bullet_holes_stay_distinct():
    frames = [(i, np.array([[100, 100], [200, 200]], np.float32)) for i in range(10, 40)]
    assert len(track_new_bullet_holes(frames, n_frames=40, window=20)) == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok  {name}")
