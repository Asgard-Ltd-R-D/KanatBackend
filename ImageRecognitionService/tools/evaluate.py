"""Score a pipeline run against operator-labelled ground truth.

Every threshold in this pipeline was set by intuition and every one of them was
wrong: a 0.70 persistence bar rejected Bullet Holes at 0.50-0.62, and a 40px
match radius discarded a Bullet Hole 125px clear of its neighbour. Both survived
because nothing could measure them. This is that measurement.

Ground truth is a photograph of the Board with the Bullet Holes labelled —
typically a Roboflow YOLO-segmentation export. The photo is taken from a
different position than the camera, so positions are compared in **template
coordinates**. The photograph is registered to the recording's baseline frame,
and reaches the template through that frame's own homography — the one the
run's detections are placed with — so both sides share one frame of reference:

    photo  --register-->  baseline frame  --H-->  template coords  <--  Board space

Usage:

    python -m tools.evaluate CLIP.mkv --start 13 --end 25 \\
        --truth-image data/truth/board.jpeg --truth-labels data/truth/board.txt

Truth derived from a photograph pair (derive_truth.py) names its own
photograph in `board.source.txt`, so `--truth-image` can be left off:

    python -m tools.evaluate CLIP.mkv --start 13 --end 25 \\
        --truth-labels data/truth/camb-20260915-103223

A clip `config/recordings.json` lists takes its print scale from its Capture
Setup; any other clip needs `--mm-per-px`, or its Position Errors stay in
template px (ADR-0010).

`--move` moves the Board synthetically (SOW 2.1.6, #164): from 25 s to the end
of the run, every frame shifted 80, 40 frame px as it is read:

    python -m tools.evaluate CLIP.mkv --start 20 --end 46 --move 25:80,40 \\
        --truth-labels data/truth/camb-20260915-102250
"""
import argparse
import functools
import glob
import itertools
import math
import os
import shutil
from typing import NamedTuple

import cv2
import networkx
import numpy as np

from detection import board
from detection import new_bullet_holes as nbh
from tools import manifest

# A Bullet Hole is roughly 25 template px across, so this is about one hole's
# width of slack between a detection and the label it is credited to. It is also
# the near attribution band — see `attribute` — and provisional in both roles:
# it is a physical scale reused, never a value swept against a score.
MATCH_TOLERANCE_TPL = 40.0   # PROVISIONAL: one Bullet Hole's width, not a fit


def damaged_lines(lines):
    """Line numbers (1-based) an export cannot be read exactly.

    A line is damaged when it carries fewer than four values, or an odd number
    of them — one export was seen cut off mid-number. Anything else is a label:
    four values is a box, six or more is a polygon. Nothing else is guessed at.

    The one place that decides what damage is, so the scoring (which warns and
    carries on) and the derivation (which refuses) cannot drift apart on what
    counts as a readable line.
    """
    rows = [l.split()[1:] for l in lines]
    return [n for n, r in enumerate(rows, 1) if len(r) < 4 or len(r) % 2]


def box_lines(lines):
    """Line numbers (1-based) that carry a box rather than a polygon."""
    return [n for n, l in enumerate(lines, 1) if len(l.split()) - 1 == 4]


def _centroid(values):
    """A label's centre, whichever way it was drawn.

    `class cx cy w h` for a box, `class x1 y1 x2 y2 ...` for a polygon. The
    rule is per LINE, and a four-value line is always a box — Roboflow never
    emits a two-point polygon, so the only thing four values can be is an
    annotation somebody drew as a box. Reading it as one keeps the label; the
    earlier per-file rule dropped it whenever the rest of the file was
    polygons, which understates ground truth and flatters recall.
    """
    if len(values) == 4:
        return np.array(values[:2], np.float32)
    points = np.array(values[:len(values) - len(values) % 2], np.float32)
    return points.reshape(-1, 2).mean(axis=0)


def _centroids(lines):
    rows = [[float(v) for v in l.split()[1:]] for l in lines]
    return np.array([_centroid(values) for values in rows if len(values) >= 4],
                    np.float32).reshape(-1, 2)


def load_labels(path):
    """Centroids of YOLO labels, normalised. Handles boxes and polygons.

    A mixed file — polygons with a box annotation among them — is read in full
    and the damaged count is returned for the caller to report. Only a line
    that cannot be read at all is dropped, and it is never dropped silently.
    """
    lines = [l for l in open(path).read().strip().splitlines() if l.strip()]
    return _centroids(lines), len(damaged_lines(lines))


# The grey-image ECC's own smoothing, in px. From the artwork's seed it needs
# the pictures blurred well past the masks' 5 before it converges: at 5 it
# settled on CamB_20260915_103223 at correlation 0.66 with every pre-existing
# mark 34-70 template px out; 11 and 21 both put them 5-12 px out, on both
# threshold-work recordings. A convergence setting, not a scoring value.
PHOTO_ECC_BLUR = 21   # PROVISIONAL: picked on the two recordings it is judged on


def register_photograph(photo, frame):
    """Homography from a photograph's pixels to a video frame's, and its ECC
    correlation.

    Fitted to the whole picture, not the artwork. On the CamB photographs the
    green artwork is a small fraction of the image, so a fit to its hue mask
    is extrapolating everywhere a label sits: straight to the template it
    correlated 0.69-0.74 and threw labels up to 58 000 template px out (#40). The
    Board around the artwork — plywood, staples, the other Targets, the marks
    themselves — is the same plane and is everywhere the labels are, so a
    grey-image ECC over all of it holds where the artwork cannot. The artwork
    still seeds it: that fit is coarse but in the right place.

    Correlation is convergence, not geometry: the artwork fit scores 0.9999 on
    a disk and misses by 18 px a Board-width away (test_evaluate). The check
    that bears on geometry is the pre-existing marks, which `evaluate.py`
    prints after the run.
    """
    contours, mask = board.find_targets(photo)
    frame_contours, frame_mask = board.find_targets(frame)
    if not contours or not frame_contours:
        raise SystemExit("no Target found in the ground-truth photograph or the "
                         "baseline frame; cannot register one to the other")
    # Which photograph Target is which frame Target is unknown: a change of
    # viewpoint reorders them by size or crops one out of either picture, and a
    # seed one Target-spacing out converges on the repeated artwork there. Seed
    # from every pair; over the whole picture the wrong correspondence cannot
    # correlate as well as the right one.
    grey = [cv2.cvtColor(i, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
            for i in (photo, frame)]
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    best, errors = None, []
    # ponytail: pairs x ECC runs, fine for the few Targets a Board holds
    for source, reference in itertools.product(contours, frame_contours):
        try:
            seed, _ = board.register(mask, frame_mask, reference,
                                     board.box_seed(source, reference))
            fit = cv2.findTransformECC(
                grey[0], grey[1], seed, cv2.MOTION_HOMOGRAPHY, criteria, None,
                PHOTO_ECC_BLUR)
        except cv2.error as e:
            errors.append(e.err)
            continue
        if best is None or fit[0] > best[0]:
            best = fit
    if best is None:
        raise SystemExit(f"the ground-truth photograph did not register to the "
                         f"baseline frame ({errors[0]}); no position from it is "
                         f"evidence")
    correlation, H = best
    return H, correlation


def truth_in_template(image_path, label_path, frame, view):
    """Ground-truth positions in template coordinates, through the baseline
    frame: `(truth, photo px -> template matrix, correlation, damaged)`."""
    image = cv2.imread(image_path)
    if image is None:
        raise SystemExit(f"cannot read ground-truth image {image_path}")
    height, width = image.shape[:2]
    H, correlation = register_photograph(image, frame)
    to_template = np.linalg.inv(view.H) @ H @ np.diag([width, height, 1.0])

    normalised, damaged = load_labels(label_path)
    return board.apply(to_template, normalised), to_template, correlation, damaged


def off_canvas(truth, view):
    """Indices of template positions outside the rectified Board the detector
    is shown — positions no run can find, whatever the reason."""
    width, height = view.canvas_size
    placed = view.template_to_board(truth)
    return [i for i, (x, y) in enumerate(placed)
            if not (0 <= x < width and 0 <= y < height)]


def match(truth, found, tolerance):
    """Minimum-distance maximum-cardinality one-to-one matching.

    One-to-one matters: without it a cluster of false positives all credit
    themselves to the same label and precision looks far better than it is.

    Maximum cardinality matters for the same reason, in the other direction.
    Taking the nearest free label each time is not enough — with labels at 0 and
    10, detections at 4 and -5 and a tolerance of 7, the detection at 4 takes
    label 0 because it is nearest, and the one at -5 is then left with nothing
    within reach. That pairing scores one true positive; pairing -5 with 0 and 4
    with 10 scores two. Greedy manufactures a false positive AND a false
    negative out of nothing but the order it happened to consider things in,
    and these numbers are what thresholds get set from.

    Minimum distance among those maximum-cardinality pairings matters for
    *which* things paired, which the counts cannot show. With before-marks at 0
    and 6, after-marks at 0, 1 and 4 and a tolerance of 6, two pairings both
    score two: {0-0, 6-4} leaves the mark at 1 over, {0-1, 6-0} leaves the mark
    at 4. `derive_new_holes` writes that leftover into the ground truth and
    seeds the refit with the pairs, so the nearer reading has to win.

    Weighting every in-reach edge `tolerance + 1 - distance` and taking the
    maximum-weight maximum-cardinality matching gives exactly that: cardinality
    first, total distance second, no dependence on the order marks arrive in.

    Returns `(pairs, missed)` where pairs is [(found_index, truth_index, distance)].
    """
    graph = networkx.Graph()
    for i, p in enumerate(found):
        if not len(truth):
            break
        for j, d in enumerate(np.linalg.norm(truth - p, axis=1)):
            if d <= tolerance:
                graph.add_edge(("found", i), ("truth", j),
                               weight=tolerance + 1 - float(d))

    owner = {}                      # label -> the detection credited with it
    for a, b in networkx.max_weight_matching(graph, maxcardinality=True):
        (_, i), (_, j) = (a, b) if a[0] == "found" else (b, a)
        owner[j] = i

    pairs = sorted((i, j, float(np.linalg.norm(truth[j] - found[i])))
                   for j, i in owner.items())
    missed = [j for j in range(len(truth)) if j not in owner]
    return pairs, missed


def score(truth, found, tolerance=MATCH_TOLERANCE_TPL):
    pairs, missed = match(truth, found, tolerance)
    tp = len(pairs)
    fp = len(found) - tp
    fn = len(missed)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision,
            "recall": recall, "f1": f1, "pairs": pairs, "missed": missed}


def position_errors(truth, found, pairs, mm_per_tpl_px):
    """Each matched pair's Position Error in mm, as rows of `(dX, dY, radial)`
    in the order of `pairs` (`score`'s).

    dX is right and dY up along the Target's printed axes, as
    `board.to_millimetres` gives a Position, system minus truth. Both sides are
    already template px, so the Target centre is not needed: it cancels. So does
    any error in it, in the print scale or in the baseline frame's mapping to
    the artwork — this truth was carried through all three (CONTEXT.md,
    Position Error).
    """
    d = board.to_printed_axes(np.array([found[i] - truth[j] for i, j, _ in pairs],
                                       np.float64).reshape(-1, 2), mm_per_tpl_px)
    return np.column_stack([d, np.hypot(d[:, 0], d[:, 1])])


# --- attributing a false positive ------------------------------------------
#
# Registration displacement is the one OPEN failure mode in HANDOVER.md, and a
# displaced pre-existing mark is a perfectly persistent false positive that
# persistence is structurally unable to filter. Unattributed, a precision drop
# on new footage reads as a model problem and sends the work to the wrong place
# — which HANDOVER records as having already happened to two of three
# investigated failures.
#
# BOTH BANDS ARE PROVISIONAL DIAGNOSTIC BOUNDARIES. Neither is a validated
# threshold, and neither was derived from the two clips it is reported on: the
# near band is `MATCH_TOLERANCE_TPL`, which comes from a Bullet Hole's own width
# and was already the scoring's slack before any of this, and the far band is a
# judgement (see `UNKNOWN_FACTOR`). Nothing was fitted to the clips: the
# measured distances are 827 template px (CamA) and 29 (CamB's 25.60s report
# over 25-36s) against bands at 80 and 40, so only CamB's sits near an edge at
# all, and it is the case HANDOVER had already traced by hand.
#
# The near band is the scoring's own slack, not a new constant: a false positive
# within `tolerance` of a mark that was already on the Board is ON that mark, by
# exactly the standard that credits a detection with a label. `UNKNOWN_FACTOR x
# tolerance` out, nothing pre-existing is near enough for registration to have
# put a detection there, so what is left is the detector.
#
# In between is `unknown`, and unknown is an outcome rather than a rounding of
# the evidence. The one measurement that could bound displacement — the
# registration residual — is censored at the match radius on both labelled
# clips, so nothing in this project bounds it. `UNKNOWN_FACTOR` is therefore a
# judgement about how wide to leave that band, deliberately generous, and NOT a
# validated threshold: calling a detector error registration hides a model
# problem, calling registration a detector error is the misdirection this whole
# attribution exists to stop, and `unknown` costs neither.
#
# The registration residual is NOT an input here, though it is the other thing
# the suppression step already computes. It cannot be one: it is censored at the
# match radius, so it carries no information about the marks that escaped
# suppression, which are exactly the ones being attributed.
#
# Nothing here refuses a run or marks one unscoreable. The headline counts come
# from `score` and this reads them; it cannot change them. See
# docs/adr/0006-every-false-positive-is-attributed.md.
UNKNOWN_FACTOR = 2.0   # PROVISIONAL: a judgement, fixed before the sealed run (ADR-0006)

DISPLACEMENT = "displacement"
DETECTOR = "detector"
UNKNOWN = "unknown"
CAUSES = (DISPLACEMENT, DETECTOR, UNKNOWN)


def attribute(found, pairs, baseline, tolerance=MATCH_TOLERANCE_TPL):
    """A likely cause per false positive, as `(found index, cause, distance)`.

    `found` and `baseline` are both in template coordinates — the run's
    detections and the marks that were already on the Board at its baseline
    frame, as `(cx, cy)` or the baseline's own `(cx, cy, w, h)`. `pairs` is
    `score`'s, so the false positives are exactly the detections it credited
    with no label, and there is one entry per false positive: this is a
    breakdown of the headline, never an adjustment to it.

    An empty baseline gives every false positive to the detector, and says so
    with an infinite distance: no mark was on the Board for registration to
    have moved.

    **The baseline is the detector's own output**, not ground truth — nothing
    else says what was on the Board at frame one. So a pre-existing mark the
    detector missed at baseline leaves its displaced sighting looking like a
    detector error, and a baseline phantom lends a genuine detector error the
    look of displacement. Both are bounded by how good the baseline is, which
    `[INFO] baseline: N Baseline Marks` prints on every run.
    """
    credited = {i for i, _, _ in pairs}
    marks = (np.asarray(baseline, np.float32)[:, :2] if len(baseline)
             else np.zeros((0, 2), np.float32))
    out = []
    for i in range(len(found)):
        if i in credited:
            continue
        distance = (float(np.min(np.linalg.norm(marks - found[i], axis=1)))
                    if len(marks) else float("inf"))
        cause = (DISPLACEMENT if distance <= tolerance else
                 DETECTOR if distance > UNKNOWN_FACTOR * tolerance else UNKNOWN)
        out.append((i, cause, distance))
    return out


def in_the_baseline(truth, missed, baseline, tolerance=MATCH_TOLERANCE_TPL):
    """Each missed truth within `tolerance` of a Baseline Mark, as `(truth
    index, mark index, distance)` with the nearest mark (#163).

    Such a truth is a Bullet Hole on the Board at `--start`, from an earlier
    Range, which this one rightly never reports as new. The mark index plus one
    is the report's P number: `baseline` is in the run's order. Template
    coordinates, `(cx, cy)` or the baseline's own `(cx, cy, w, h)`, as
    `attribute` reads them, and the same tolerance that credits a detection
    with a label.
    """
    if not len(baseline):
        return []
    marks = np.asarray(baseline, np.float32)[:, :2]
    out = []
    for j in missed:
        distances = np.linalg.norm(marks - truth[j], axis=1)
        k = int(np.argmin(distances))
        if distances[k] <= tolerance:
            out.append((j, k, float(distances[k])))
    return out


# --- ground truth from a before/after photograph pair ----------------------
#
# The new Bullet Holes are the after photograph's labels minus the before
# photograph's, which replaces adjudicating pre-existing marks by hand. A
# single after-photograph cannot show when a mark arrived: CamB was scored
# against all four of its labels, one of which sat on a mark already on the
# Board at the baseline frame, and an earlier HANDOVER revision reported F1
# 1.00 on that basis.
#
# The comparison happens in the AFTER photograph's own pixels. Registering each
# photograph to the template separately was tried first and does not work: on
# the customer photographs that registration correlates 0.69-0.76, the two
# errors compound, and every pre-existing mark came out unmatched — 41 marks
# that are plainly the same holes in both photographs, 0.001 apart in
# normalised photo coordinates, landing 60 to 4000 template px apart. Marks far
# outside the printed artwork fared worst, which is the homography
# extrapolating.
#
# One ECC between the two photographs replaces both. The tolerance stays the
# scoring's 40 template px, converted into photograph px by the Target span
# ratio — the same isotropic approximation `board_scale_for` makes — so the
# slack is the same physical distance, one Bullet Hole's width, measured where
# the marks actually are.

DERIVED_NAME = "board.new.txt"
RAW_NAMES = {"before": "board.before.export.txt",
             "after": "board.after.export.txt"}


def read_export(path):
    """`(lines, normalised centroids)`, one centroid per line, or refuse.

    A mixed file is read, not refused: every label is kept, boxes as boxes and
    polygons as polygons, and the caller reports the mix. A *damaged* line is
    another matter — it is a number cut short, so its position is wrong rather
    than merely differently drawn, and it breaks the line-for-line
    correspondence the derived file is built from. The derivation refuses it
    where the scoring only warns, because a ground-truth file is written once
    and read for months.
    """
    lines = [l for l in open(path).read().strip().splitlines() if l.strip()]
    bad = damaged_lines(lines)
    if bad:
        raise SystemExit(
            f"[REFUSED] {path} is damaged: "
            f"{', '.join(f'line {n}' for n in bad)} carries too few values or "
            "an odd number of them, so a coordinate was cut short. Re-export "
            "that file; keep the raw bytes and correct a derived copy. "
            "Deriving from it would put a mark in the wrong place.")
    return lines, load_labels(path)[0]


def _unmatched(pairs, count):
    """The after-labels no before-label was matched to."""
    pre_existing = {i for i, _, _ in pairs}
    return [i for i in range(count) if i not in pre_existing]


def new_label_indices(before, after, tolerance=MATCH_TOLERANCE_TPL):
    """Indices into `after` of the marks that are not in `before`.

    Both arrays are template coordinates. A before-mark with no counterpart in
    the after photograph simply goes unmatched: it subtracts nothing, and the
    caller reports it, because it more often means the registration slipped
    than that a mark left the Board.
    """
    return _unmatched(match(before, after, tolerance)[0], len(after))


# A similarity has 4 degrees of freedom, so 4 correspondences already
# over-determine it. Fewer than that and the fit reproduces its own input and
# says nothing about whether the two photographs agree.
MIN_REFIT_PAIRS = 4


def refit_on_matched_marks(before_photo_px, after, pairs):
    """The before-marks re-registered on the marks the artwork already matched.

    ECC aligns the printed Target, which spans about a sixth of these
    photographs, so the homography is at its best on the artwork and
    extrapolating everywhere else. On CamB_20260915_103223 the residual runs
    1.4 px on the Target and 6-7 px a Target-span away from it, which left two
    marks that are plainly the same hole in both photographs looking like two
    different ones — and each of those becomes a pre-existing mark counted as a
    new Bullet Hole.

    The marks the first registration did agree on are correspondences for a
    second one, and unlike the artwork they are spread over the whole Board. A
    similarity is deliberate: 4 degrees of freedom against 8 or more
    correspondences cannot bend to fit noise the way a homography can, and the
    residual left over is a real disagreement rather than a curve through it.

    `before_photo_px` is the before photograph's own pixels, NOT the registered
    ones: the fit replaces the artwork homography rather than correcting it.
    Two photographs of one Board from nearly the same place are related by
    something close to a similarity, and the perspective the homography adds
    only holds where it was fitted. Correcting H with a similarity instead of
    replacing it was tried and is worse — on CamB_20260915_103223 it leaves
    residuals of 0.2-4.7 px and one mark still unpaired, against 0.1-1.5 px and
    none.

    Returns the moved before-marks, or None when there are too few pairs for
    the fit to carry evidence. The caller re-matches at the same tolerance, so
    a refit can only pull the same mark together — never widen what counts as
    one mark.

    `MIN_REFIT_PAIRS` is checked twice, because RANSAC can throw the
    overdetermination away: handed pairs it cannot reconcile it is free to
    return the similarity its two-point sample supports and mark the rest
    outliers, which is the two-point fit `MIN_REFIT_PAIRS` exists to refuse,
    reached the long way round. The inliers have to carry it, not the seeds.
    """
    if len(pairs) < MIN_REFIT_PAIRS:
        return None
    src = np.float32([before_photo_px[j] for _, j, _ in pairs]).reshape(-1, 1, 2)
    dst = np.float32([after[i] for i, _, _ in pairs]).reshape(-1, 1, 2)
    M, inliers = cv2.estimateAffinePartial2D(src, dst)
    if M is None or inliers is None or int(inliers.sum()) < MIN_REFIT_PAIRS:
        return None
    return cv2.transform(
        np.float32(before_photo_px).reshape(-1, 1, 2), M).reshape(-1, 2)


def keep_refit(pairs, refit_pairs):
    """Is the second registration worth adopting over the first?

    Only if it pulls in marks the first one left out, or pairs exactly the
    same marks it did. A refit that loses a pair has found a worse frame of
    reference, not a better one — and one that merely re-deals the same number
    of pairs among different marks has changed which after-label is written
    down as a new Bullet Hole while gaining nothing to justify it.
    """
    return (len(refit_pairs) > len(pairs)
            or {(i, j) for i, j, _ in refit_pairs} == {(i, j) for i, j, _ in pairs})


def photo_tolerance(tolerance, target_span_px, template_span_px):
    """A template-px tolerance expressed in photograph px.

    Isotropic: one span ratio for the whole photograph, as `board_scale_for`
    already assumes. Perspective makes the true scale vary across the Board,
    but the marks sit on and around one Target and the slack is a whole Bullet
    Hole wide, so the variation is well inside it.
    """
    return tolerance * target_span_px / template_span_px


def _photograph(path):
    """A photograph's pixels, its Target mask and its largest Target."""
    image = cv2.imread(path)
    if image is None:
        raise SystemExit(f"cannot read photograph {path}")
    contours, mask = board.find_targets(image)
    if not contours:
        raise SystemExit(f"no Target found in {path}; cannot register it")
    return image, mask, contours[0]


def derive_new_holes(before_image, before_labels, after_image, after_labels,
                     template_path=board.DEFAULT_TEMPLATE,
                     tolerance=MATCH_TOLERANCE_TPL):
    """The new Bullet Holes, as indices into the after export's lines.

    `before_image` is the photograph of the Board before firing, or — where the
    recording was already shot and nobody can return to the Board — the frame
    an operator hand-labelled. That is explicitly not the detector's own
    baseline output; independence from the model is what makes it evidence.
    """
    lines, after_normalised = read_export(after_labels)
    before_lines, before_normalised = read_export(before_labels)

    template = cv2.imread(template_path)
    if template is None:
        raise SystemExit(f"cannot read template {template_path}")
    _, template_mask = board.find_targets(template, min_area=1)

    before_photo, before_mask, _ = _photograph(before_image)
    after_photo, after_mask, after_target = _photograph(after_image)

    # One homography between the two photographs, not one each to the template.
    H, correlation = board.register(before_mask, after_mask, after_target)
    reach = photo_tolerance(
        tolerance, board.contour_span(after_target),
        board.contour_span(board.template_contour(template_mask)))

    height, width = after_photo.shape[:2]
    after = after_normalised * [width, height]
    before_px = before_normalised * [before_photo.shape[1], before_photo.shape[0]]
    before = board.apply(H, before_px)

    pairs, only_before = match(before, after, reach)

    # A second registration, fitted to the marks the first one agreed on.
    refit = refit_on_matched_marks(before_px, after, pairs)
    refitted = False
    if refit is not None:
        refit_pairs, refit_only_before = match(refit, after, reach)
        if keep_refit(pairs, refit_pairs):
            pairs, only_before, refitted = refit_pairs, refit_only_before, True

    return {"lines": lines,
            "before_lines": before_lines,
            "new": _unmatched(pairs, len(after)),
            "pre_existing": sorted(i for i, _, _ in pairs),
            "only_before": only_before,
            "correlation": correlation,
            "tolerance_px": reach,
            "refitted": refitted,
            "distances": sorted(d for _, _, d in pairs)}


SOURCE_NAME = "board.source.txt"
UNPAIRED_FIELD = "before-marks-without-a-counterpart"
# 1-based lines of the after export, counting only non-blank ones.
PRE_EXISTING_FIELD = "pre-existing-export-lines"


def write_derived(out_dir, result, before_image, before_labels,
                  after_image, after_labels):
    """The derived file, the raw exports byte-for-byte, and where they came from.

    The derived file is a correction; the exports are the evidence it was
    derived from, so they are kept unchanged rather than overwritten. The
    photographs are not copied — they are large, and like the recordings they
    are not version-controlled — so their paths are written down instead.
    Without that, a derived label file is anonymous: nothing says which
    photograph its coordinates are normalised against, and `evaluate.py` needs
    exactly that image.
    """
    os.makedirs(out_dir, exist_ok=True)
    derived = os.path.join(out_dir, DERIVED_NAME)
    with open(derived, "w") as f:
        f.write("".join(result["lines"][i] + "\n" for i in result["new"]))

    written = {"derived": derived}
    for which, source in (("before", before_labels), ("after", after_labels)):
        raw = os.path.join(out_dir, RAW_NAMES[which])
        if os.path.abspath(source) != os.path.abspath(raw):
            shutil.copyfile(source, raw)
        written[f"{which}_raw"] = raw

    written["source"] = os.path.join(out_dir, SOURCE_NAME)
    with open(written["source"], "w") as f:
        f.write(
            f"# {DERIVED_NAME} is the after photograph's labels minus the "
            f"before photograph's.\n"
            f"# Its coordinates are normalised against the after photograph.\n"
            f"before-image: {os.path.abspath(before_image)}\n"
            f"before-labels: {before_labels}\n"
            f"after-image: {os.path.abspath(after_image)}\n"
            f"after-labels: {after_labels}\n"
            f"photograph-registration-correlation: {result['correlation']:.4f}\n"
            f"refitted-on-matched-marks: "
            f"{'yes' if result.get('refitted') else 'no'}\n"
            f"match-tolerance-photo-px: {result['tolerance_px']:.1f}\n"
            f"labelled-after: {len(result['lines'])}\n"
            f"pre-existing: {len(result['pre_existing'])}\n"
            f"{PRE_EXISTING_FIELD}: "
            f"{','.join(str(i + 1) for i in result['pre_existing'])}\n"
            f"new-bullet-holes: {len(result['new'])}\n"
            f"{UNPAIRED_FIELD}: {len(result['only_before'])}\n")
    return written


def unpaired_before_marks(label_path):
    """Before-marks the derivation could not pair, per the sibling source file.

    Each one is a mark that was on the Board and whose counterpart in the after
    photograph was therefore counted as new — so the truth being scored against
    holds a mark the run cannot legitimately find. The derivation prints this
    when it writes the file; a run scoring against that file months later
    prints nothing, which is how a flag stops being a flag. Zero for truth that
    was not derived from a photograph pair at all.
    """
    value = _source_field(label_path, UNPAIRED_FIELD)
    return int(value) if value else 0


def _source_field(label_path, field):
    """One field of the sibling source file, or None — including when there is
    no source file, i.e. truth not derived from a photograph pair."""
    source = os.path.join(os.path.dirname(label_path), SOURCE_NAME)
    if not os.path.exists(source):
        return None
    for line in open(source):
        key, _, value = line.partition(":")
        if key == field:
            return value.strip()
    return None


def truth_photograph(image_path, label_path):
    """The photograph `label_path` is normalised against.

    Derived truth names it in `after-image:`, so it need not be passed — and
    passing one that disagrees used to register cleanly and score silently
    wrong. The recorded path points outside the repo and is wrong on another
    machine, so an explicit one still wins; the mismatch is printed instead.
    Truth with no source file has nothing to check it against. The raw before
    export, named explicitly, is normalised against the before photograph.
    """
    which = "before" if os.path.basename(label_path) == RAW_NAMES["before"] else "after"
    recorded = _source_field(label_path, f"{which}-image")
    if image_path is None:
        if recorded is None:
            raise SystemExit(
                f"--truth-image is required: {label_path} has no {SOURCE_NAME} "
                "beside it to name the photograph it was labelled on")
        if not os.path.isfile(recorded):
            raise SystemExit(
                f"{SOURCE_NAME} names {recorded} as the {which} photograph, but "
                "it is not there — moved or deleted? Pass --truth-image")
        return recorded
    image = _one(image_path, "*.jp*g")
    if recorded is not None and os.path.realpath(image) != os.path.realpath(recorded):
        print(f"[WARN] --truth-image {image} is not the {which} photograph "
              f"{SOURCE_NAME} names ({recorded}); the labels are normalised "
              f"against that one, so this scores wrong unless it is the same "
              f"photograph moved")
    return image


def _one(path, pattern):
    """A file, or the single `pattern` match under a directory.

    Several matches are refused rather than resolved alphabetically.
    A frame-labelled truth directory once held four .txt files — the before
    labels, the raw export, the derived file and the corrected one — and taking the first
    scored the run against `board.before.txt`, the marks that were on the Board
    before it started. Silence is what made that possible, so it says which
    files it found and makes the caller name one.
    """
    if os.path.isfile(path):
        return path
    hits = sorted(glob.glob(os.path.join(path, pattern)))
    if not hits:
        raise SystemExit(f"no {pattern} under {path}")
    if len(hits) > 1:
        raise SystemExit(
            f"{path} holds {len(hits)} files matching {pattern} "
            f"({', '.join(os.path.basename(h) for h in hits)}); name the one "
            "to use. Scoring against the wrong one is silent.")
    return hits[0]


def truth_labels(path):
    """The labels to score against, given a file or a truth directory.

    A derived truth directory holds the raw after export beside the derived
    file, and `board.after.export.txt` sorts first. Taking it would score the
    run against every mark on the Board, pre-existing ones included — the exact
    error the derivation exists to prevent, reached by nothing but alphabetical
    order. So the derived file wins whenever it is there.
    """
    derived = os.path.join(path, DERIVED_NAME)
    return derived if os.path.exists(derived) else _one(path, "*.txt")


def pre_existing_labels(label_path):
    """Normalised centroids of the after photograph's pre-existing marks, or
    None for truth not derived from a photograph pair.

    They are the after export's lines the derivation recorded as pre-existing,
    by line number in the source file. Not the export minus the derived file:
    a corrected label no longer equals its export line, and that subtraction
    would then count the new Bullet Hole as pre-existing. These marks need no
    ground truth to check — the run's baseline holds them — which makes them
    the one measurement of where the truth placement puts labels. None, too,
    for a derivation that predates the field.
    """
    export = os.path.join(os.path.dirname(label_path), RAW_NAMES["after"])
    recorded = _source_field(label_path, PRE_EXISTING_FIELD)
    if (os.path.basename(label_path) != DERIVED_NAME or recorded is None
            or not os.path.exists(export)):
        return None
    lines = [l for l in open(export).read().strip().splitlines() if l.strip()]
    return _centroids([lines[int(n) - 1] for n in recorded.split(",") if n])


def load_truth(image_path, label_path, frame, view):
    """Ground truth in template coordinates, with every caveat printed, and the
    derived truth's pre-existing marks placed the same way (None otherwise).

    `frame` and `view` are the baseline frame and its Board space
    (`nbh.open_board_space`): the Run's own when scoring (`base` and `view`
    on `nbh.RegisteredFrames`, #185). Shared by the scoring and the detector
    probe: both report recall, and a label the recording could never have
    found understates it in either.
    """
    labels = truth_labels(label_path)
    photograph = truth_photograph(image_path, labels)
    truth, to_template, correlation, damaged = truth_in_template(
        photograph, labels, frame, view)
    print(f"[TRUTH] {len(truth)} labelled Bullet Holes from "
          f"{os.path.basename(labels)}, registered to the baseline frame at "
          f"correlation {correlation:.4f} (convergence, not geometry)")
    if damaged:
        print(f"[WARN] {damaged} label(s) were malformed or truncated; "
              f"their positions are approximate")
    unpaired = unpaired_before_marks(labels)
    if unpaired:
        print(f"[WARN] the derivation left {unpaired} before-mark(s) unpaired, "
              f"so up to {unpaired} of these labels were already on the Board "
              f"before the recording. The run cannot find those, and recall is "
              f"understated by that much. See {SOURCE_NAME}.")
    outside = off_canvas(truth, view)
    if outside:
        print(f"[WARN] {', '.join(f'truth #{j + 1}' for j in outside)} land(s) "
              f"outside the rectified Board the detector is shown: the placement "
              f"is wrong, or the Board runs past the canvas (#41). Scored all the "
              f"same, and no run can find them.")
    pre = pre_existing_labels(labels)
    if pre is not None:
        pre = board.apply(to_template, pre)
    return truth, pre


def placement_note(pre_existing_truth, baseline_tpl, tolerance, mm_per_tpl_px,
                   off_canvas_count=0):
    """How far the photograph's pre-existing marks land from the baseline's.

    They are the same Bullet Holes, so the distance is the truth placement's
    own error — reported on every derived score, because a placement that
    throws labels somewhere plausible-looking otherwise scores as silently as
    one that throws them 58 000 px out. The baseline is the detector's output,
    so an unpaired mark is a misplaced label or a mark the baseline missed.

    `off_canvas_count` counts pre-existing marks left out because they land
    off the rectified Board, where no baseline can hold them (#41). They stay
    a doubt: the Board running past the canvas and a wrong placement throwing
    them there look the same from here, and only the placement under test
    puts them off the canvas at all.
    """
    if not len(pre_existing_truth):
        return (f"[WARN] placement unverified: all {off_canvas_count} "
                f"pre-existing mark(s) are off the canvas, so nothing is left "
                f"to check it against — and a wrong placement is one way to put "
                f"them there (#41). A wrong placement would change this score "
                f"silently.")
    pairs, missed = match(pre_existing_truth, baseline_tpl, tolerance)
    note = (f"[PLACEMENT] {len(pairs)} of {len(pre_existing_truth)} "
            f"pre-existing mark(s) in the photograph land within {tolerance:.0f} "
            f"template px of a mark the baseline holds")
    if pairs:
        d = sorted(d for _, _, d in pairs)
        note += f", {d[0]:.0f}-{d[-1]:.0f} px"
        if mm_per_tpl_px is not None:
            note += f" ({d[0] * mm_per_tpl_px:.1f}-{d[-1] * mm_per_tpl_px:.1f} mm)"
        note += ": that is the placement's error"
    if off_canvas_count:
        note += (f"\n[WARN] {off_canvas_count} more pre-existing mark(s) land off "
                 f"the canvas, where no baseline can hold them: the Board runs "
                 f"past the canvas (#41), or the placement threw them there. "
                 f"Not checked; scores below carry that doubt.")
    if missed:
        note += (f"\n[WARN] {len(missed)} pre-existing mark(s) land on nothing "
                 f"the baseline holds: the truth placement is off, or the "
                 f"baseline missed them. Scores below carry that doubt.")
    return note


# --- moving the Board (#164) ------------------------------------------------
#
# No Recording holds a Board move, so the scoring tool makes one: every frame
# from a chosen time to the end of the run warped by one whole-frame transform,
# as it is read. Tooling, not product: the delivered entrypoint cannot move the
# Board.

class Move(NamedTuple):
    """`--move AT:DX,DY[,DEG]`: from `at` seconds into the Recording, on the
    clock of `--start` and `--end`, every frame shifted `dx`, `dy` frame px,
    then turned `deg` degrees counter-clockwise, as the frame is viewed, about
    the centroid of the Targets in the baseline frame."""
    at: float
    dx: float
    dy: float
    deg: float = 0.0


def parse_move(text):
    """`--move`'s value as a `Move`, for argparse."""
    try:
        at, shift = text.split(":")
        move = Move(float(at), *map(float, shift.split(",")))
        if not all(map(math.isfinite, move)):
            raise ValueError
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            f"a move is AT:DX,DY[,DEG] (seconds into the Recording, frame px, "
            f"degrees), not {text!r}") from None
    return move


def first_moved_index(at, start, fps):
    """The first frame index a move at `at` seconds reaches: the first whose
    printed time (`Recording.when`, two decimals) is `at` or later, so a time
    read off the log moves the frame printed with it. Stepped up from 0.01 s
    before `at`, below any frame the rounding can print at `at`."""
    index = max(0, math.floor((at - start - 0.01) * fps))
    while float(f"{start + index / fps:.2f}") < at:
        index += 1
    return index


def refuse_move(move, start, end, fps, baseline_frames, stride):
    """Refuse a move that would move no pixel, move the baseline it is measured
    against, or move no frame the run looks at. Counted in frames as `process`
    reads them: a move between two frames lands on the next."""
    if not move.dx and not move.dy and not move.deg % 360:
        raise SystemExit(f"[REFUSED] --move {move.dx:g},{move.dy:g},{move.deg:g} moves "
                         f"no pixel: a case that moves nothing must not read as a pass")
    baseline_frames = max(1, baseline_frames)   # as `process` counts them
    first = first_moved_index(move.at, start, fps)
    if first < baseline_frames:
        raise SystemExit(f"[REFUSED] --move at {move.at}s is inside the baseline window: "
                         f"a move must come after its last frame, "
                         f"t={start + (baseline_frames - 1) / fps:.2f}s")
    looked = -(-first // stride) * stride   # the first Look moved, past the baseline
    if looked >= int((end - start) * fps):   # as `RegisteredFrames.frames_until` counts
        raise SystemExit(f"[REFUSED] --move at {move.at}s moves no frame the run looks "
                         f"at before --end {end}s (stride {stride}): a case that moves "
                         f"nothing must not read as a pass")


def move_matrix(move, base):
    """`move`'s 2x3 warp: the shift, then the turn about the centroid of the
    Targets found in `base`, the baseline frame, each Target counted once.
    About any other point a turn adds a hidden shift."""
    shift = np.float64([[1, 0, move.dx], [0, 1, move.dy], [0, 0, 1]])
    if not move.deg:
        return shift[:2]
    moments = [cv2.moments(c) for c in board.find_targets(base)[0]]
    cx, cy = np.mean([[m["m10"] / m["m00"], m["m01"] / m["m00"]] for m in moments], axis=0)
    return cv2.getRotationMatrix2D((float(cx), float(cy)), move.deg, 1.0) @ shift


class MovedRecording:
    """A Recording with the Board moved (#164): every frame from index `first` to
    the end of the run warped by the 2x3 `matrix`, the vacated border filled by
    replicating the edge. Frame 0 and every frame before `first` are handed over
    untouched, so Board space, the baseline and the truth placement are the
    unmoved run's. Everything else the frame-source interface answers (#148) is
    the Recording's: indices, gaps under a stride, times. Warped as each frame
    is read, nothing re-encoded, so an integer shift is pixel-exact."""

    def __init__(self, recording, first, matrix):
        self._recording, self._first, self._matrix = recording, first, matrix

    def __getattr__(self, name):
        return getattr(self._recording, name)

    def read(self):
        frame = self._recording.read()
        if frame is None or frame.index < self._first:
            return frame
        height, width = frame.image.shape[:2]
        return frame._replace(image=cv2.warpAffine(
            frame.image, self._matrix, (width, height), borderMode=cv2.BORDER_REPLICATE))


def open_moved(move, video, start, ref_time=None):
    """The source opener for a run with `move` (the Run's open's `opener`):
    the Recording at `start`, moved, and its frame 0, untouched."""
    recording, base = nbh.Recording.open(video, start, ref_time)
    first = first_moved_index(move.at, start, recording.fps)
    turn = (f", then turned {move.deg:g} degrees about the baseline frame's Targets' "
            f"centroid" if move.deg else "")
    print(f"[MOVE] from t={recording.when(first)} (frame {first}) to the end of the run, every "
          f"frame shifted {move.dx:g}, {move.dy:g} frame px{turn}; the vacated border "
          f"replicates the edge. Synthetic (#164)")
    return MovedRecording(recording, first, move_matrix(move, base)), base


def score_recording(video, start, end, truth_labels, truth_image=None,
                    model=nbh.DEFAULT_MODEL, template=board.DEFAULT_TEMPLATE,
                    confidence=nbh.DEFAULT_CONFIDENCE, change_filter=True,
                    merge_displaced=False, baseline_frames=nbh.BASELINE_FRAMES,
                    stride=None, tolerance=MATCH_TOLERANCE_TPL, mm_per_px=None,
                    move=None):
    """Score one run of `video` against its truth, printing every line as it
    goes, and return what a pooled report reads (position_error.py, #126).
    With a `Move`, the run reads a `MovedRecording` (#164). It returns:

    - `rows`: per matched pair, `(found #, truth #, Target or "MISS", dX, dY,
      radial)`, 1-based, mm, in truth order;
    - `unmatched` and `missed`: the detections no truth claimed and the truth
      no detection found;
    - `placement`: the placement-check note as printed;
    - `entry`: the manifest entry found by content hash, None for a
      recording it does not list (ADR-0010);

    and what the Board-move table reads (board_move.py, #165):

    - `truths`: how many truth Bullet Holes there are;
    - `times`: per found #, in order, the seconds into the Recording it was
      first seen at;
    - `false_positives`: per detection no truth claimed, `(found #, (x, y)
      template px, cause, distance to the nearest Baseline Mark)`, as
      `attribute` gives them;
    - `in_baseline`: `(truth #, P #)` per missed truth on a Baseline Mark;
    - `lost` and `reanchors`: the run's Lost Looks past the baseline and its
      re-anchor attempts.
    """
    # The print scale before anything is opened, looked up as the pipeline
    # looks it up: `mm_per_px`, else the listed Capture Setup's. A listed one
    # without a scale is refused where the pipeline runs on without
    # millimetres; an unlisted recording runs, its errors in template px.
    scales = board.print_scales()
    entry = manifest.lookup(video)
    mm_per_tpl_px = mm_per_px
    if mm_per_tpl_px is None and entry is not None:
        mm_per_tpl_px = scales.get(entry["capture_setup"])
        if mm_per_tpl_px is None:
            raise SystemExit(
                f"[REFUSED] Capture Setup {entry['capture_setup']!r} has no print "
                f"scale in config/print_scale.json, so no Position Error can be put "
                f"in mm. docs/ring_measurement.md has how it is measured; every mm "
                f"figure scales linearly with it, so it is not guessed.")
    if mm_per_tpl_px is None:
        print(f"[WARN] {video} is in no config/recordings.json entry, so it has no "
              f"Capture Setup and no print scale: Position Errors are reported in "
              f"template px, not mm. Give one with --mm-per-px")
    if entry is not None:
        fps = entry["fps"]
    else:
        cap = cv2.VideoCapture(video)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
    if move is not None:
        refuse_move(move, start, end, fps, baseline_frames, stride or 1)

    # The run's positions are in Board space; ground truth is in template space.
    # The truth is placed through the Run's own baseline frame and Board space,
    # so a scored Run builds Board space once, and before its first Look, so a
    # truth that cannot be placed fails before any (#185).
    loop = nbh.RegisteredFrames.open(
        video, start, nbh.load_model(model), confidence, template,
        opener=None if move is None else functools.partial(open_moved, move))
    view = loop.view
    truth, pre_labels = load_truth(truth_image, truth_labels, loop.base, view)

    run = nbh.process(loop, end, require_change_evidence=change_filter,
                      merge_displaced=merge_displaced,
                      baseline_frames=baseline_frames, stride=stride)

    found = view.board_to_template(
        np.array([h["pos"] for h in run.holes], np.float32).reshape(-1, 2))
    # The marks that were already on the Board, in the same frame of reference —
    # what tells a displaced one of those from a detector false positive.
    pre_existing = view.board_to_template(np.asarray(run.baseline, np.float32)[:, :2])
    if pre_labels is not None and len(pre_labels):
        outside = off_canvas(pre_labels, view)
        placement = placement_note(np.delete(pre_labels, outside, axis=0),
                                   pre_existing, tolerance, mm_per_tpl_px,
                                   off_canvas_count=len(outside))
    else:
        placement = ("[WARN] placement unverified: the truth names no "
                     "pre-existing mark to check it against, and the "
                     "registration correlation is not a geometry check. A wrong "
                     "placement would change this score silently.")
    print(placement)

    result = score(truth, found, tolerance)
    print(f"\n[SCORE] TP {result['tp']}  FP {result['fp']}  FN {result['fn']}   "
          f"precision {result['precision']:.0%}  recall {result['recall']:.0%}  "
          f"F1 {result['f1']:.2f}")
    for i, j, d in sorted(result["pairs"], key=lambda t: t[1]):
        print(f"   found #{i + 1} -> truth #{j + 1}   {d:5.0f} template px")
    if result["missed"]:
        print(f"   missed: {', '.join(f'truth #{j + 1}' for j in result['missed'])}")
    in_baseline = in_the_baseline(truth, result["missed"], pre_existing, tolerance)
    for j, k, d in in_baseline:
        print(f"   truth #{j + 1} in the baseline at --start, P{k + 1}   {d:5.0f} template px")

    # SOW 2.3.2 (#123). Internal: this truth shares the footage's print scale
    # and mapping to the artwork, so errors in those cancel out of it.
    errors = position_errors(truth, found, result["pairs"], mm_per_tpl_px or 1.0)
    rows = []
    for (i, j, _), (dx, dy, radial) in sorted(zip(result["pairs"], errors),
                                              key=lambda t: t[0][1]):
        target = run.holes[i]["target"]
        where = "MISS" if target is None else f"Target {target + 1}"
        rows.append((i + 1, j + 1, where, dx, dy, radial))
    unit = "mm" if mm_per_tpl_px else "template px"
    scale = (f"{mm_per_tpl_px} mm per template px "
             f"({entry['capture_setup'] if entry else '--mm-per-px'})" if mm_per_tpl_px
             else "no print scale")
    print(f"\n[POSITION ERROR] {len(errors)} matched pair(s), {unit} along the "
          f"Target's printed axes (X right, Y up), system minus truth, at {scale}. "
          f"Internal: against truth in this footage's own frame of reference")
    for i, j, where, dx, dy, radial in rows:
        print(f"   found #{i} -> truth #{j}   {where:<9} dX {dx:+6.1f}  "
              f"dY {dy:+6.1f}  radial {radial:5.1f} {unit}")

    # Under the headline, never in it.
    attribution = attribute(found, result["pairs"], pre_existing, tolerance)
    if attribution:
        counted = {c: sum(1 for _, cause, _ in attribution if cause == c)
                   for c in CAUSES}
        print(f"\n[ATTRIBUTION] {len(attribution)} false positive(s): "
              + ", ".join(f"{n} {c}" for c, n in counted.items())
              + f" (displacement within {tolerance:.0f} template px of a "
                f"Baseline Mark, detector beyond "
                f"{UNKNOWN_FACTOR * tolerance:.0f})")
        for i, cause, distance in attribution:
            near = "none" if distance == float("inf") else f"{distance:.0f} px"
            print(f"   found #{i + 1}  {cause:<12} nearest Baseline Mark {near}")

    # On every score, in the template px a score is read in, and a bar on
    # nothing: no registration-failure threshold has been validated — not
    # against Bullet Hole scale, not against SOW 2.3.2's 5 mm — and inventing
    # one from a single clip is the error this project keeps finding in its own
    # constants. So a run is never refused or marked unscoreable on this line.
    print(nbh.registration_note(
        np.asarray(run.residual, np.float32) / view.board_scale,
        board.MATCH_TPL_PX, "template px"))

    return {"rows": rows, "unmatched": result["fp"], "missed": result["fn"],
            "placement": placement, "entry": entry, "truths": len(truth),
            "times": [start + h["first_frame"] / fps for h in run.holes],
            "false_positives": [(i + 1, tuple(found[i]), cause, distance)
                                for i, cause, distance in attribution],
            "in_baseline": [(j + 1, k + 1) for j, k, _ in in_baseline],
            "lost": run.lost, "reanchors": run.reanchors}


if __name__ == "__main__":
    p = argparse.ArgumentParser("Score a run against labelled ground truth")
    p.add_argument("video")
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--truth-image",
                   help="photo of the Board, or a directory; derived truth "
                        "names its own in board.source.txt")
    p.add_argument("--truth-labels", required=True, help="YOLO-seg .txt, or a directory")
    p.add_argument("--model", default=nbh.DEFAULT_MODEL)
    p.add_argument("--template", default=board.DEFAULT_TEMPLATE)
    p.add_argument("--confidence", type=float, default=nbh.DEFAULT_CONFIDENCE)
    p.add_argument("--no-change-filter", action="store_true")
    p.add_argument("--merge-displaced", action="store_true",
                   help="PROVISIONAL: fold displaced sightings, see new_bullet_holes")
    p.add_argument("--baseline-frames", type=int, default=nbh.BASELINE_FRAMES,
                   help="PROVISIONAL: frames the baseline is built from, see "
                        "new_bullet_holes")
    nbh.add_stride_flag(p)
    p.add_argument("--tolerance", type=float, default=MATCH_TOLERANCE_TPL,
                   help="how close a detection must be to claim a label, template px")
    p.add_argument("--move", type=parse_move, metavar="AT:DX,DY[,DEG]",
                   help="move the Board, synthetically (#164): from AT seconds into "
                        "the Recording to the end of the run, every frame shifted DX, "
                        "DY frame px, then turned DEG degrees counter-clockwise about "
                        "the baseline frame's Targets' centroid; the vacated border "
                        "replicates the edge. AT is on the log's two-decimal clock. "
                        "Refused when it moves nothing, inside the baseline window, "
                        "past the last frame looked at")
    p.add_argument("--mm-per-px", type=board.checked_scale, default=None,
                   help="print scale, mm per template px. Overrides the listed "
                        "Capture Setup's; a recording config/recordings.json does "
                        "not list takes it from here only, or reports in template px")
    a = p.parse_args()
    score_recording(a.video, a.start, a.end, a.truth_labels, a.truth_image,
                    model=a.model, template=a.template,
                    confidence=a.confidence,
                    change_filter=not a.no_change_filter,
                    merge_displaced=a.merge_displaced,
                    baseline_frames=a.baseline_frames, stride=a.stride,
                    tolerance=a.tolerance, mm_per_px=a.mm_per_px, move=a.move)
