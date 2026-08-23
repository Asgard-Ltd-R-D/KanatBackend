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


def test_tight_group_collapses_KNOWN_DEFECT():
    """Two holes 20px apart are reported as one.

    Pins the defect tracked in issue #8 rather than the desired behaviour:
    the separation gate is ~4.5x a hole's diameter, wider than real shot
    groups. Change this to 2 when the gate is re-tuned against ground truth.
    """
    assert run(Box(300, 200, 7, 7, cls=1), Box(316, 212, 7, 7, cls=1)) == 1


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
