"""Propose each truth Bullet Hole's arrival frame, for a human to confirm (#273).

Hit-to-report (`regression.py`) runs from the frame a Bullet Hole arrived in,
and the truth photographs carry no time. This reads it off the footage, not
the detector: a change that made the detector see a hole sooner would show no
gain against the detector's own first sighting.

A hole counts as arrived in the first frame it is formed in, not the first
that shows a smear or dust: the detector could report nothing sooner. Per
truth line, the patch of frame around it is compared with the window's first
frame; the hole is the largest lasting step in that difference, and its
arrival the first frame past the step's midpoint that holds there.

    python -m tools.arrival                       # every recording with truth
    python -m tools.arrival --only CamB_20260915_102250

writes `board.arrival.txt` beside each truth, one line per truth line,
`<frame> proposed`, and a strip per recording into `docs/arrival/`: per truth
line, frames -3 to +3 around the proposal. A human looks at the strip and
rewrites the line `<frame> confirmed` or `<frame> corrected`. Frames are the
Recording's, from 0, at its manifest frame rate.
"""
import argparse
import os

import cv2
import numpy as np

from detection import board
from detection import new_bullet_holes as nbh
from tools import evaluate, manifest, position_error, regression

STEP = 25          # frames either side a step is judged over: one second at 25 fps
HOLD = 3           # frames the difference must stay past the midpoint
HOLE_TPL = 12.0    # a Bullet Hole's radius, template px (about 25 across)
DISK_HOLES = 2     # the difference is read over this many radii: placements land up to one off
CROP_HOLES = 4     # strip crop half-width, in hole radii
STRIP_PX = 160     # each strip cell, px
SHOWN = range(-3, 4)
STRIPS_DIR = os.path.join(manifest.BASE_DIR, "docs", "arrival")


def propose(d, step=STEP, hold=HOLD):
    """The frame index a Bullet Hole arrived in, from `d`, its patch's
    difference from a reference frame, per frame.

    The rise at a frame is how far the median of the next `step` frames
    exceeds the median of the `step` before; a passing flash moves neither
    median. The step is the first rise at least half the largest, at its peak:
    the hole forms before anything later changes it more (`_102250` truth #3
    formed at frame 41, and changed more at ~230). The arrival is the first
    frame within a step of it past the midpoint of the two medians that stays
    past it for `hold` frames: formed, not smeared."""
    d = np.asarray(d, np.float64)
    n = len(d)
    rise = np.array([np.median(d[f:f + step]) - np.median(d[max(0, f - step):f])
                     for f in range(hold, n - hold)])
    first = int(np.argmax(rise >= rise.max() / 2))
    at = hold + first + int(np.argmax(rise[first:first + step]))
    mid = (np.median(d[max(0, at - step):at]) + np.median(d[at:at + step])) / 2
    for f in range(max(0, at - step), min(n - hold, at + step)):
        if (d[f:f + hold] >= mid).all():
            return f
    return at


def write(truth_dir, frames):
    """`board.arrival.txt` in `truth_dir`, one `<frame> proposed` per truth line,
    `-` for none."""
    with open(os.path.join(truth_dir, regression.ARRIVAL_NAME), "w") as f:
        f.writelines(f"{'-' if a is None else a} proposed\n" for a in frames)


def place(entry):
    """Each truth Bullet Hole in the Recording's frame px, as a Run places it
    (Board space from the window's first frame), and a hole's radius there.

    The radius is taken at the 10-ring the homography was fitted to: a hole
    on a second Board lies near its horizon, where 12 template px came out
    163 frame px (`_101550`). Its position is a round trip and is exact."""
    _, template_mask = board.find_targets(cv2.imread(board.DEFAULT_TEMPLATE), min_area=1)
    video = os.path.join(position_error.VIDEO_DIR, entry["file"])
    source, base, view, _ = nbh.open_board_space(video, entry["window"][0], template_mask)
    source.close()
    truth, _ = evaluate.load_truth(None, position_error.truth_dir(entry), base, view)
    to_frame = lambda p: view.board_to_frame(view.template_to_board(np.float32(p).reshape(-1, 2)))
    ring = to_frame(board.RING_CENTRE_TPL)
    return to_frame(truth), float(np.linalg.norm(to_frame(board.RING_CENTRE_TPL + [HOLE_TPL, 0]) - ring))


def patches(video, points, half, first, last):
    """Grey patches of side `2 * half` around each point, per frame from
    `first` to `last`: `(frames, points, 2 * half, 2 * half)`."""
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    out = []
    for _ in range(first, last):
        ok, frame = cap.read()
        if not ok:
            break
        grey = cv2.copyMakeBorder(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                                  half, half, half, half, cv2.BORDER_REPLICATE)
        out.append([grey[int(y):int(y) + 2 * half, int(x):int(x) + 2 * half]
                    for x, y in np.round(points)])
    cap.release()
    return np.asarray(out, np.float32)


def differences(stack, radius):
    """Per frame and point, the mean absolute difference from the first frame
    over a disk of `radius` at the patch centre."""
    half = stack.shape[-1] // 2
    yy, xx = np.mgrid[-half:half, -half:half]
    disk = np.hypot(xx + 0.5, yy + 0.5) <= radius
    return np.abs(stack - stack[:1])[..., disk].mean(axis=-1)


def strip(stack, rows, first, labels):
    """One row per truth line: frames -3..+3 around its proposal, each labelled."""
    out = []
    for j, (at, label) in enumerate(zip(rows, labels)):
        cells = []
        for o in SHOWN:
            f = min(max(at + o - first, 0), len(stack) - 1)
            cell = cv2.resize(stack[f, j].astype(np.uint8), (STRIP_PX, STRIP_PX),
                              interpolation=cv2.INTER_NEAREST)
            cell = cv2.cvtColor(cell, cv2.COLOR_GRAY2BGR)
            colour = (0, 200, 0) if o == 0 else (255, 255, 255)
            cv2.putText(cell, f"{first + f}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 0, 0), 3)
            cv2.putText(cell, f"{first + f}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1)
            if o == 0:
                cv2.rectangle(cell, (0, 0), (STRIP_PX - 1, STRIP_PX - 1), colour, 2)
            cells.append(cell)
        head = np.zeros((STRIP_PX, 110, 3), np.uint8)
        cv2.putText(head, label, (4, STRIP_PX // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 255, 255), 1)
        out.append(np.hstack([head] + cells))
    return np.vstack(out)


def label(entry):
    """Propose, write the file and the strip for one Recording; print a line
    per truth line."""
    name = os.path.splitext(entry["file"])[0]
    video = os.path.join(position_error.VIDEO_DIR, entry["file"])
    points, radius = place(entry)
    half = max(16, int(round(CROP_HOLES * radius)))
    first = int(entry["window"][0] * entry["fps"])
    last = int(entry["window"][1] * entry["fps"])
    stack = patches(video, points, half, first, last)
    d = differences(stack, DISK_HOLES * radius)
    frames = [first + propose(d[:, j]) for j in range(len(points))]
    write(position_error.truth_dir(entry), frames)
    os.makedirs(STRIPS_DIR, exist_ok=True)
    path = os.path.join(STRIPS_DIR, f"{name}.png")
    cv2.imwrite(path, strip(stack, frames, first,
                            [f"truth #{j + 1}" for j in range(len(frames))]))
    for j, f in enumerate(frames):
        print(f"{name}  truth #{j + 1}  frame {f}  ({f / entry['fps']:.2f}s)")
    print(f"strip: {path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser("Propose each truth Bullet Hole's arrival frame (#273)")
    p.add_argument("--only", action="append",
                   help="a recording's file stem; repeat for several")
    a = p.parse_args()
    for entry in position_error.select(manifest.load()):
        if a.only and os.path.splitext(entry["file"])[0] not in a.only:
            continue
        label(entry)
