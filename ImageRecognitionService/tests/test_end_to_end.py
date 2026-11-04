"""Checks for #279's end-to-end replay: the frame stamp and the per-stage join. No video."""
import cv2
import numpy as np

from tools import end_to_end as e2e


def test_a_stamp_reads_back_through_an_h264_like_blur():
    for n in (0, 1, 777, 2 ** e2e.STAMP_BITS - 1):
        image = np.full((1080, 1920, 3), 90, np.uint8)
        e2e.stamp(image, n, 1_800_000_000.123)
        blurred = cv2.GaussianBlur(image, (5, 5), 1.5)
        assert e2e.read_stamp(blurred) == n


def test_an_unstamped_frame_reads_as_none():
    assert e2e.read_stamp(np.full((1080, 1920, 3), 128, np.uint8)) is None


def test_stages_join_sent_frames_looks_and_holes():
    sent = {10: 100.0, 14: 100.16}
    # index, stamp, taken, wait (s); the stream's frame 0 is file frame 10
    frames = [e2e.Taken(0, 10, 100.5, 0.0), e2e.Taken(4, 14, 100.9, 0.02)]
    looks = {4: 50.0}   # Look Time, ms
    holes = [e2e.Hole(first_frame=4, confirmed=103.0, posted=103.01, delivered=103.02)]
    s = e2e.stages(sent, frames, looks, holes)
    assert s["sent to decoded"] == [100.9 - 0.02 - 100.16]
    assert s["Frame Wait"] == [0.02]
    assert s["Look Time"] == [0.05]
    assert np.allclose(s["Persistence"], [103.0 - (100.9 + 0.05)])
    assert np.allclose(s["posted"], [0.01])
    assert np.allclose(s["delivered by SSE"], [0.02])
    assert np.allclose(s["first-seen frame sent to delivered"], [103.02 - 100.16])
    assert s["stamp mismatches"] == 0


def test_a_frame_whose_stamp_disagrees_with_its_index_is_counted_and_placed_by_its_stamp():
    sent = {10: 100.0, 13: 100.12, 14: 100.16}
    frames = [e2e.Taken(0, 10, 100.5, 0.0), e2e.Taken(4, 13, 100.9, 0.0)]
    s = e2e.stages(sent, frames, {4: 10.0}, [])
    assert s["stamp mismatches"] == 1
    assert np.allclose(s["sent to decoded"], [100.9 - 100.12])


def test_frame_0_unread_is_placed_by_the_first_stamp_that_reads():
    sent = {10: 100.0, 14: 100.16}
    frames = [e2e.Taken(0, None, 100.5, 0.0), e2e.Taken(4, 14, 100.9, 0.0)]
    s = e2e.stages(sent, frames, {4: 10.0}, [])
    assert s["stamp mismatches"] == 1
    assert np.allclose(s["sent to decoded"], [100.9 - 100.16])
