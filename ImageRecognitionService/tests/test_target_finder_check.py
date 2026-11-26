"""The outdoor and colour check's scoring (#413). No model, no footage."""
import cv2
import numpy as np

from tools.target_finder_check import score, versions

SQUARE = [[100, 100], [300, 100], [300, 300], [100, 300]]


def test_a_found_target_and_a_false_one_are_told_apart():
    near = [[110, 105], [305, 105], [305, 305], [110, 305]]
    elsewhere = [[500, 500], [600, 500], [600, 600], [500, 600]]

    s = score([near, elsewhere], [SQUARE], (800, 800))

    assert (s["hit5"], s["hit85"], s["truth"], s["fp"]) == (1, 1, 1, 1)


def test_every_colour_version_keeps_the_frame_and_moves_its_hue():
    frame = np.zeros((4, 4, 3), np.uint8)
    frame[:] = cv2.cvtColor(np.uint8([[[60, 200, 200]]]), cv2.COLOR_HSV2BGR)[0, 0]   # the print's green

    v = versions(frame)

    assert len(v) == 9 and all(img.shape == frame.shape for img in v.values())
    assert (v["grey"][..., 0] == v["grey"][..., 2]).all()
    hue = cv2.cvtColor(v["hue90"], cv2.COLOR_BGR2HSV)[0, 0, 0]
    assert abs(int(hue) - (60 + 45)) <= 2   # OpenCV hue is degrees / 2
