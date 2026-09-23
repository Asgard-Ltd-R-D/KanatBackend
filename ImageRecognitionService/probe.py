"""How often the detector sees each ground-truth Bullet Hole, pipeline aside.

For every labelled Bullet Hole: the share of registered frames holding a raw
detection within a radius of it, at a confidence floor low enough that
thresholding is not part of the answer. Baseline, persistence and change
evidence play no part — this measures the model, on the image the runtime
shows it, and nothing else.

Recall only. Detector precision is already characterised (~86% of raw
detections land on gravel), and the false positives the customer feels are the
pipeline's, which `evaluate.py` scores against the same photograph.

The generalised form of the probe that found CamB's 0.04s mark lost at conf
0.02 while it sat in plain view. That earlier probe sampled ten timestamps, each
registered on its own, and got the onset wrong (HANDOVER.md, failure mode 3).
This one looks at every frame through the runtime loop. A rate hides a finding
like that, so each Bullet Hole also gets its longest blind run.

Frames come from `new_bullet_holes.RegisteredFrames`, never a loop of this
file's own — see the warning there. `--model` takes several checkpoints and
runs each over the same footage against the same ground truth.

    python probe.py CLIP.mkv --start 13 --end 25 \\
        --truth-image truth/kanatv6 --truth-labels truth/kanatv6 \\
        --model a/best.pt b/best.pt

The denominator is every registered frame from `--start`, so a Bullet Hole
that lands mid-clip reads below 1.0 by the frames before it existed; its
`first` time says where.

`--at X,Y` is a diagnostic apart from all that: it probes explicit
template-space positions instead of ground truth, for a mark no label holds.
CamB's 0.04s mark is one — pre-existing, so absent from every derived
`board.new.txt`, and in no label set this repo carries. Its rate is not recall.
"""
import argparse
import os
from typing import NamedTuple

import cv2
import numpy as np

import board
import evaluate
import manifest
import new_bullet_holes as nbh

# Low enough that no operating threshold is part of the answer: the pipeline
# runs at 0.40, and the CamB finding was a mark absent even at this floor.
PROBE_CONFIDENCE = 0.02


class BlindRun(NamedTuple):
    """Consecutive registered frames without a detection of one Bullet Hole."""
    first: int    # frame index
    last: int
    frames: int   # registered frames in it; lost frames inside neither break nor count


class Rate(NamedTuple):
    """How often the detector saw one Bullet Hole. Frame indices, not seconds."""
    rate: float | None   # None when no registered frame looked at it
    looked: int
    first: int | None    # first and last frame with a detection, None if never
    last: int | None
    blind: BlindRun | None   # the longest; None if it was never unseen


def detection_rates(looks, positions, radius):
    """Per position, how often a registered frame held a detection near it.

    `looks` are `new_bullet_holes.Look`s, `positions` Board-space (x, y), and
    `radius` Board px, inclusive. A frame that failed to register is left out
    of the denominator rather than scored as no detection — the rule
    persistence follows. Each position is measured on its own; a detection near
    one credits no other, and several on one Bullet Hole count its frame once.

    Returns one `Rate` per position.
    """
    positions = np.asarray(positions, np.float32).reshape(-1, 2)
    looked, hit = [], []   # hit[k][p]: did registered look k see position p
    for look in looks:
        if not look.registered:
            continue
        looked.append(look.index)
        centres = look.detections[:, :2]
        if len(centres):
            nearest = np.linalg.norm(centres[None] - positions[:, None], axis=2).min(axis=1)
            hit.append(nearest <= radius)
        else:
            hit.append(np.zeros(len(positions), bool))

    rates = []
    for p in range(len(positions)):
        seen = [i for i, h in zip(looked, hit) if h[p]]
        blind, run_first, run_frames = None, None, 0
        for i, h in zip(looked, hit):
            if h[p]:
                run_frames = 0
                continue
            run_first = i if run_frames == 0 else run_first
            run_frames += 1
            if blind is None or run_frames > blind.frames:
                blind = BlindRun(run_first, i, run_frames)
        rates.append(Rate(len(seen) / len(looked) if looked else None, len(looked),
                          seen[0] if seen else None, seen[-1] if seen else None,
                          blind))
    return rates


def parse_point(text):
    """`--at X,Y` as a template-space (x, y)."""
    try:
        x, y = (float(v) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected X,Y in template px, got {text!r}")
    return x, y


def probe(video, start, end, model_path, truth_tpl, radius_tpl,
          conf=PROBE_CONFIDENCE, template_path=board.DEFAULT_TEMPLATE,
          names=None):
    """Run one checkpoint over the clip and print a rate per position.

    `names` labels each line; by default the positions are ground truth and
    read `truth #n`.
    """
    names = names or [f"truth #{n}" for n in range(1, len(truth_tpl) + 1)]
    print(f"\n[PROBE] {os.path.relpath(model_path)} at conf {conf}")
    loop = nbh.RegisteredFrames.open(video, start, model_path, conf, template_path)
    view = loop.view
    radius = radius_tpl * view.board_scale
    rates = detection_rates(loop.looks(loop.frames_until(end)),
                            board._apply(view.tpl_to_board, truth_tpl), radius)
    # Net scale goes on every result: detection is zero by 1.81, so a rate is
    # only comparable with another taken at the same scale.
    print(f"[PROBE] {loop.processed - loop.lost} registered frame(s) of "
          f"{loop.processed} read; {loop.lost} lost and excluded. Radius "
          f"{radius_tpl:.0f} template px ({radius:.1f} Board px), net scale "
          f"{loop.net_scale:.2f}")

    def t(index):
        return f"{start + index / loop.fps:.2f}s"

    for name, r in zip(names, rates):
        if r.rate is None:
            print(f"   {name}  no registered frame looked at it")
            continue
        line = f"   {name}  rate {r.rate:.2f}  of {r.looked} frames"
        if r.first is not None:
            line += f"   first {t(r.first)}  last {t(r.last)}"
        if r.blind:
            line += (f"   longest blind {t(r.blind.first)}-{t(r.blind.last)} "
                     f"({r.blind.frames} frames)")
        print(line)
    return rates


if __name__ == "__main__":
    p = argparse.ArgumentParser("Per-Bullet-Hole detection rate, pipeline aside")
    p.add_argument("video")
    p.add_argument("--start", type=float, required=True,
                   help="the frame Board space is built from, seconds")
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--truth-image", help="photo of the Board, or a directory")
    p.add_argument("--truth-labels", help="YOLO .txt, or a directory")
    p.add_argument("--at", type=parse_point, action="append",
                   help="DIAGNOSTIC, instead of ground truth: probe this "
                        "template-space X,Y (repeatable). For a mark no label "
                        "holds; its rate is not a recall figure")
    p.add_argument("--model", nargs="+", default=[nbh.DEFAULT_MODEL],
                   help="one or more checkpoints, each run over the same footage")
    p.add_argument("--template", default=board.DEFAULT_TEMPLATE)
    p.add_argument("--confidence", type=float, default=PROBE_CONFIDENCE)
    p.add_argument("--radius", type=float, default=evaluate.MATCH_TOLERANCE_TPL,
                   help="template px; the same slack that credits a detection "
                        "with a label when a run is scored")
    manifest.add_flag(p)
    a = p.parse_args()
    if bool(a.at) == bool(a.truth_image or a.truth_labels):
        p.error("give either --truth-image with --truth-labels, or --at")
    if not a.at and not (a.truth_image and a.truth_labels):
        p.error("--truth-image and --truth-labels go together")

    for model in a.model:
        manifest.gate(a.video, a.final_run, model, "probe.py")

    if a.at:
        truth = np.array(a.at, np.float32)
        names = [f"at ({x:.1f}, {y:.1f})" for x, y in a.at]
        print(f"[DIAGNOSTIC] {len(truth)} explicit template-space position(s), "
              f"no ground truth: rates below are not recall")
    else:
        template = cv2.imread(a.template)
        _, template_mask = board.find_targets(template, min_area=1)
        truth = evaluate.load_truth(a.truth_image, a.truth_labels, template_mask)
        names = None

    for model in a.model:
        probe(a.video, a.start, a.end, model, truth, a.radius, a.confidence,
              a.template, names)
