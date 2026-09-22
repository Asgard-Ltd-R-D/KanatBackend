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
    """Line numbers (1-based) an export cannot be read cleanly from.

    The one place that decides what damage is, so the evaluation (which warns
    and carries on) and the derivation (which refuses) cannot drift apart on
    what counts as a readable line. See `load_labels` for the rule.
    """
    rows = [l.split()[1:] for l in lines]
    if rows and all(len(r) == 4 for r in rows):
        return []
    return [n for n, r in enumerate(rows, 1) if len(r) < 6 or len(r) % 2]


def load_labels(path):
    """Centroids of YOLO labels, normalised. Handles boxes and polygons.

    Roboflow exports the same annotations either way — `class cx cy w h` for
    detection, `class x1 y1 x2 y2 ...` for segmentation — and a bare line of
    five fields is ambiguous between a box and a (meaningless) two-point
    polygon. The format is therefore decided per FILE, not per line: if every
    line carries exactly four values it is a box file.

    That distinction matters. In a polygon file a five-field line is a
    truncated instance, and one export was seen cut off mid-number. Dropping it
    silently would understate ground truth and flatter recall, so it is counted
    as damaged and reported.
    """
    lines = [l for l in open(path).read().strip().splitlines() if l.strip()]
    rows = [[float(v) for v in l.split()[1:]] for l in lines]
    if rows and all(len(r) == 4 for r in rows):
        return np.array([r[:2] for r in rows], np.float32).reshape(-1, 2), 0

    centroids = []
    for values in rows:
        if len(values) < 6:            # fewer than 3 points is not a polygon
            continue
        pts = np.array(values[:len(values) - len(values) % 2], np.float32)
        centroids.append(pts.reshape(-1, 2).mean(axis=0))
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
# The two photographs are taken from different positions, so they are compared
# in template coordinates — and matched by the same `match` at the same
# tolerance the scoring uses, so a mark that shifted between the photographs is
# one mark and two marks near one pre-existing mark are not folded together.

DERIVED_NAME = "board.new.txt"
RAW_NAMES = {"before": "board.before.export.txt",
             "after": "board.after.export.txt"}


def read_export(path):
    """`(lines, normalised centroids)`, one centroid per line, or refuse.

    The scoring tolerates a damaged line and warns; a derivation cannot.
    Dropping a line here would silently move a mark out of ground truth
    altogether — out of the before set, where it stops suppressing a
    pre-existing mark, or out of the after set, where it flatters recall. It
    also breaks the line-for-line correspondence the derived file is built
    from. So a mixed or damaged export is reported and nothing is written.
    """
    lines = [l for l in open(path).read().strip().splitlines() if l.strip()]
    bad = damaged_lines(lines)
    if bad:
        raise SystemExit(
            f"[REFUSED] {path} is a mixed or damaged export: "
            f"{', '.join(f'line {n}' for n in bad)} cannot be read as a "
            "polygon. Export from Roboflow as DETECTION, not segmentation; "
            "where the export needs correcting, keep the raw file and correct "
            "a derived copy. Dropping the line would understate ground truth.")
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


def derive_new_holes(before_image, before_labels, after_image, after_labels,
                     template_path=board.DEFAULT_TEMPLATE,
                     tolerance=MATCH_TOLERANCE_TPL):
    """The new Bullet Holes, as indices into the after export's lines.

    `before_image` is the photograph of the Board before firing, or — where the
    recording was already shot and nobody can return to the Board — the frame
    an operator hand-labelled. That is explicitly not the detector's own
    baseline output; independence from the model is what makes it evidence.
    """
    lines, _ = read_export(after_labels)
    read_export(before_labels)          # refuse a damaged before export too

    template = cv2.imread(template_path)
    if template is None:
        raise SystemExit(f"cannot read template {template_path}")
    _, template_mask = board.find_targets(template, min_area=1)

    before, before_correlation, _ = truth_in_template(
        before_image, before_labels, template_mask)
    after, after_correlation, _ = truth_in_template(
        after_image, after_labels, template_mask)

    pairs, only_before = match(before, after, tolerance)
    return {"lines": lines,
            "new": _unmatched(pairs, len(after)),
            "pre_existing": sorted(i for i, _, _ in pairs),
            "only_before": only_before,
            "before_correlation": before_correlation,
            "after_correlation": after_correlation}


def write_derived(out_dir, lines, new, before_labels, after_labels):
    """The derived file, beside byte-for-byte copies of both raw exports.

    The derived file is a correction; the exports are the evidence it was
    derived from, so they are kept unchanged rather than overwritten.
    """
    os.makedirs(out_dir, exist_ok=True)
    derived = os.path.join(out_dir, DERIVED_NAME)
    with open(derived, "w") as f:
        f.write("".join(lines[i] + "\n" for i in new))
    written = {"derived": derived}
    for which, source in (("before", before_labels), ("after", after_labels)):
        raw = os.path.join(out_dir, RAW_NAMES[which])
        if os.path.abspath(source) != os.path.abspath(raw):
            shutil.copyfile(source, raw)
        written[f"{which}_raw"] = raw
    return written


def _one(path, pattern):
    if os.path.isfile(path):
        return path
    hits = sorted(glob.glob(os.path.join(path, pattern)))
    if not hits:
        raise SystemExit(f"no {pattern} under {path}")
    return hits[0]


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

    truth, correlation, damaged = truth_in_template(
        _one(a.truth_image, "*.jp*g"), _one(a.truth_labels, "*.txt"), template_mask)
    print(f"[TRUTH] {len(truth)} labelled Bullet Holes, "
          f"ground-truth registration correlation {correlation:.4f}")
    if damaged:
        print(f"[WARN] {damaged} label(s) were malformed or truncated; "
              f"their positions are approximate")

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
