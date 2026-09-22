"""Score a pipeline run against operator-labelled ground truth.

Every threshold in this pipeline was set by intuition and every one of them was
wrong: a 0.70 persistence bar rejected Bullet Holes at 0.50-0.62, and a 40px
match radius discarded a Bullet Hole 125px clear of its neighbour. Both survived
because nothing could measure them. This is that measurement.

Ground truth is a photograph of the Board with the Bullet Holes labelled —
typically a Roboflow YOLO-segmentation export. The photo is taken from a
different position than the camera, so positions are compared in **template
coordinates**: both the photo and the video frame are registered to the same
printed Target artwork, which puts them in one frame of reference.

    photo  --register-->  template coords  <--register--  video Board space

Usage:

    python evaluate.py CLIP.mkv --start 13 --end 25 \\
        --truth-image truth/board.jpeg --truth-labels truth/board.txt

The clip needs a `recordings.json` entry; sealed footage needs `--final-run`
on top of it. See manifest.py.
"""
import argparse
import glob
import os
import shutil

import cv2
import numpy as np

import board
import manifest
import new_bullet_holes as nbh

# A Bullet Hole is roughly 25 template px across, so this is about one hole's
# width of slack between a detection and the label it is credited to.
MATCH_TOLERANCE_TPL = 40.0


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


def load_labels(path):
    """Centroids of YOLO labels, normalised. Handles boxes and polygons.

    A mixed file — polygons with a box annotation among them — is read in full
    and the damaged count is returned for the caller to report. Only a line
    that cannot be read at all is dropped, and it is never dropped silently.
    """
    lines = [l for l in open(path).read().strip().splitlines() if l.strip()]
    rows = [[float(v) for v in l.split()[1:]] for l in lines]
    centroids = [_centroid(values) for values in rows if len(values) >= 4]
    return (np.array(centroids, np.float32).reshape(-1, 2),
            len(damaged_lines(lines)))


def truth_in_template(image_path, label_path, template_mask):
    """Ground-truth Bullet Hole positions in template coordinates."""
    image = cv2.imread(image_path)
    if image is None:
        raise SystemExit(f"cannot read ground-truth image {image_path}")
    height, width = image.shape[:2]
    contours, mask = board.find_targets(image)
    if not contours:
        raise SystemExit("no Target found in the ground-truth image; cannot register it")
    H, correlation = board.register(template_mask, mask, contours[0])

    normalised, damaged = load_labels(label_path)
    pixels = normalised * [width, height]
    return board._apply(np.linalg.inv(H), pixels), correlation, damaged


def _claim(i, within, owner, tried):
    """Let detection `i` take a label, re-routing whoever already holds it.

    One augmenting path (Kuhn's algorithm). The re-routing is the whole point:
    a detection that finds its options taken asks each holder to move aside,
    and the holder only does so if it can take another label itself.
    """
    for j in within[i]:
        if j in tried:
            continue
        tried.add(j)
        if j not in owner or _claim(owner[j], within, owner, tried):
            owner[j] = i
            return True
    return False


def match(truth, found, tolerance):
    """Maximum-cardinality one-to-one matching, nearest first.

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

    Detections are still seeded nearest-first, so where greedy was already
    optimal the pairing is unchanged; only the distances within a re-routed
    chain may be longer than a distance-optimal assignment would give. Every
    pair is within tolerance either way, so the counts — which is what scores —
    are exact.

    Returns `(pairs, missed)` where pairs is [(found_index, truth_index, distance)].
    """
    within, order = {}, []          # detection -> labels in reach, nearest first
    for i, p in enumerate(found):
        if not len(truth):
            break
        distances = np.linalg.norm(truth - p, axis=1)
        within[i] = [int(j) for j in np.argsort(distances)
                     if distances[j] <= tolerance]
        order.append((float(distances.min()), i))

    owner = {}                      # label -> the detection credited with it
    for _, i in sorted(order):
        _claim(i, within, owner, set())

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
    before = board._apply(
        H, before_normalised * [before_photo.shape[1], before_photo.shape[0]])

    pairs, only_before = match(before, after, reach)
    return {"lines": lines,
            "before_lines": before_lines,
            "new": _unmatched(pairs, len(after)),
            "pre_existing": sorted(i for i, _, _ in pairs),
            "only_before": only_before,
            "correlation": correlation,
            "tolerance_px": reach,
            "distances": sorted(d for _, _, d in pairs)}


SOURCE_NAME = "board.source.txt"
UNPAIRED_FIELD = "before-marks-without-a-counterpart"


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
            f"before-image: {before_image}\n"
            f"before-labels: {before_labels}\n"
            f"after-image: {after_image}\n"
            f"after-labels: {after_labels}\n"
            f"photograph-registration-correlation: {result['correlation']:.4f}\n"
            f"match-tolerance-photo-px: {result['tolerance_px']:.1f}\n"
            f"labelled-after: {len(result['lines'])}\n"
            f"pre-existing: {len(result['pre_existing'])}\n"
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
    source = os.path.join(os.path.dirname(label_path), SOURCE_NAME)
    if not os.path.exists(source):
        return 0
    for line in open(source):
        key, _, value = line.partition(": ")
        if key == UNPAIRED_FIELD:
            return int(value)
    return 0


def _one(path, pattern):
    """A file, or the single `pattern` match under a directory.

    Several matches are refused rather than resolved alphabetically.
    `truth/camb-25-36` holds four .txt files — the before labels, the raw
    export, the derived file and the corrected one — and taking the first
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


if __name__ == "__main__":
    p = argparse.ArgumentParser("Score a run against labelled ground truth")
    p.add_argument("video")
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--truth-image", required=True, help="photo of the Board, or a directory")
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
    p.add_argument("--tolerance", type=float, default=MATCH_TOLERANCE_TPL,
                   help="how close a detection must be to claim a label, template px")
    manifest.add_flag(p)
    a = p.parse_args()

    # Split membership before anything is opened: a sealed recording is refused
    # unless this run says it is the final one. See manifest.py and ADR-0005.
    manifest.gate(a.video, a.final_run, a.model, "evaluate.py")

    template = cv2.imread(a.template)
    _, template_mask = board.find_targets(template, min_area=1)

    labels = truth_labels(a.truth_labels)
    truth, correlation, damaged = truth_in_template(
        _one(a.truth_image, "*.jp*g"), labels, template_mask)
    print(f"[TRUTH] {len(truth)} labelled Bullet Holes from "
          f"{os.path.basename(labels)}, "
          f"ground-truth registration correlation {correlation:.4f}")
    if damaged:
        print(f"[WARN] {damaged} label(s) were malformed or truncated; "
              f"their positions are approximate")
    unpaired = unpaired_before_marks(labels)
    if unpaired:
        print(f"[WARN] the derivation left {unpaired} before-mark(s) unpaired, "
              f"so up to {unpaired} of these labels were already on the Board "
              f"before the recording. The run cannot find those, and recall is "
              f"understated by that much. See {SOURCE_NAME}.")

    holes = nbh.process(a.video, a.start, a.end, a.model, a.confidence,
                        template_path=a.template,
                        require_change_evidence=not a.no_change_filter,
                        merge_displaced=a.merge_displaced,
                        baseline_frames=a.baseline_frames)

    # The run's positions are in Board space; ground truth is in template space.
    # Board space is fixed by the BASELINE frame, so rebuild it from exactly that
    # frame — reading frame 0 instead would silently use a different origin.
    cap = cv2.VideoCapture(a.video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(a.start * cap.get(cv2.CAP_PROP_FPS)))
    ok, baseline_frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"cannot re-read {a.video} at {a.start}s")
    view, _ = board.build_view(baseline_frame, template_mask)
    found = board._apply(np.linalg.inv(view.tpl_to_board),
                         np.array([h["pos"] for h in holes], np.float32).reshape(-1, 2))

    result = score(truth, found, a.tolerance)
    print(f"\n[SCORE] TP {result['tp']}  FP {result['fp']}  FN {result['fn']}   "
          f"precision {result['precision']:.0%}  recall {result['recall']:.0%}  "
          f"F1 {result['f1']:.2f}")
    for i, j, d in sorted(result["pairs"], key=lambda t: t[1]):
        print(f"   found #{i + 1} -> truth #{j + 1}   {d:5.0f} template px")
    if result["missed"]:
        print(f"   missed: {', '.join(f'truth #{j + 1}' for j in result['missed'])}")
