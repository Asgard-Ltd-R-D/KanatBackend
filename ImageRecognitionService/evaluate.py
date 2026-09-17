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
"""
import argparse
import glob
import os

import cv2
import numpy as np

import board
import new_bullet_holes as nbh

# A Bullet Hole is roughly 25 template px across, so this is about one hole's
# width of slack between a detection and the label it is credited to.
MATCH_TOLERANCE_TPL = 40.0


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

    centroids, damaged = [], 0
    for values in rows:
        if len(values) < 6:            # fewer than 3 points is not a polygon
            damaged += 1
            continue
        if len(values) % 2:
            values = values[:-1]
            damaged += 1
        pts = np.array(values, np.float32).reshape(-1, 2)
        centroids.append(pts.mean(axis=0))
    return np.array(centroids, np.float32).reshape(-1, 2), damaged


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


def match(truth, found, tolerance):
    """Greedy one-to-one matching, nearest first.

    One-to-one matters: without it a cluster of false positives all credit
    themselves to the same label and precision looks far better than it is.
    Returns `(pairs, missed)` where pairs is [(found_index, truth_index, distance)].
    """
    pairs, claimed = [], set()
    order = []
    for i, p in enumerate(found):
        if not len(truth):
            break
        distances = np.linalg.norm(truth - p, axis=1)
        order.append((float(distances.min()), i, int(np.argmin(distances))))
    for _, i, _ in sorted(order):
        distances = np.linalg.norm(truth - found[i], axis=1)
        for j in np.argsort(distances):
            if j in claimed:
                continue
            if distances[j] <= tolerance:
                claimed.add(int(j))
                pairs.append((i, int(j), float(distances[j])))
            break
    missed = [j for j in range(len(truth)) if j not in claimed]
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
    p.add_argument("--tolerance", type=float, default=MATCH_TOLERANCE_TPL,
                   help="how close a detection must be to claim a label, template px")
    a = p.parse_args()

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
                        None, None, a.template, not a.no_change_filter,
                        a.merge_displaced)

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
