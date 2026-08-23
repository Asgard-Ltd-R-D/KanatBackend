"""De-duplication checks for the bullet-hole pipeline.

Runs without the model weights or a torch install: `process_video` takes an
injected detector, so these drive the real pipeline (video decode, target
scaling, suppression, spreadsheet write) with synthetic detections.

Run: python test_dedup.py
"""
import numpy as np

from tagging_bullets import process_video

VIDEO = './videos/test_video.mp4'


class _Arr(np.ndarray):
    """Mimics the torch tensor surface the pipeline calls on ultralytics boxes."""
    def cpu(self):
        return self

    def numpy(self):
        return np.asarray(self)


def _arr(*vals):
    return np.asarray(vals, dtype=float).view(_Arr)


class Box:
    """Minimal stand-in for an ultralytics detection box."""
    def __init__(self, x, y, w, h, cls, conf=0.9):
        self.xyxy = [_arr(x - w / 2, y - h / 2, x + w / 2, y + h / 2)]
        self.xywh = [_arr(x, y, w, h)]
        self.cls  = [cls]
        self.conf = [conf]


TARGET = Box(500, 300, 120, 120, cls=2)


def run(*holes):
    """Feed the same detections on every frame, as a static camera would."""
    boxes = [TARGET, *holes]
    return len(process_video('00:00:00', '00:00:01',
                             detect=lambda frame: boxes, video_path=VIDEO))


def test_same_hole_across_frames_counted_once():
    assert run(Box(300, 200, 7, 7, cls=1)) == 1


def test_distinct_holes_counted_separately():
    assert run(Box(200, 200, 7, 7, cls=1), Box(600, 450, 7, 7, cls=1)) == 2


def test_low_confidence_detections_ignored():
    assert run(Box(300, 200, 7, 7, cls=1, conf=0.4)) == 0


def test_frames_without_a_target_produce_nothing():
    assert len(process_video('00:00:00', '00:00:01',
                             detect=lambda frame: [Box(300, 200, 7, 7, cls=1)],
                             video_path=VIDEO)) == 0


def test_tight_group_counted_as_separate_bullet_holes():
    """Two holes 20px apart — 2x their box diagonal — are two Bullet Holes."""
    assert run(Box(300, 200, 7, 7, cls=1), Box(316, 212, 7, 7, cls=1)) == 2


def test_close_centres_are_one_bullet_hole():
    """Two boxes on one hole, centres inside 0.5x the mean diagonal."""
    assert run(Box(300, 200, 7, 7, cls=1), Box(303, 202, 7, 7, cls=1)) == 1


def test_overlapping_boxes_are_one_bullet_hole():
    """A small box nested in a large one: overlap merges what distance would not.

    Centres are 19px apart against a 17px gate, so only the overlap arm fires.
    """
    assert run(Box(300, 200, 40, 40, cls=1), Box(317, 209, 8, 8, cls=1)) == 1


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith('test_'):
            continue
        try:
            fn()
            print(f'PASS {name}')
        except AssertionError as exc:
            failed += 1
            print(f'FAIL {name}: {exc}')
    raise SystemExit(failed)
