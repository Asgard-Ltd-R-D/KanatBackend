"""Capture Profile sweep: run a confidence x inference-size grid over one frame.

Operator tooling, deliberately outside the processing pipeline. It shows what
each candidate setting finds; it does not pick one. Auto-selecting by highest
count optimises straight into false positives — at low confidence the model
emits far more boxes than there are Bullet Holes on the Board.

    python sweep_profile.py images/board.jpg

Look at the annotated frames, compare against the Bullet Holes you can see on
the Board, then copy the winning cell's numbers into capture_profiles.json.
"""
import argparse
import os

import cv2
import numpy as np
import pandas as pd

from tagging_bullets import (CLS_BULLET_HOLE, CLS_TARGET, MODEL_PATH,
                             OUTER_RADIUS, OUTER_THICK, RECT_THICK,
                             get_center, is_duplicate_bullet)

CONFIDENCES     = [0.30, 0.40, 0.50, 0.60]
INFERENCE_SIZES = [1280, 1600, 1920]
OUTPUT_DIR      = './sweep_output'
CONTACT_WIDTH   = 800  # per cell in the contact sheet; the full-res cells carry the detail


def annotate_cell(frame, targets, bullet_holes, caption):
    img = frame.copy()
    # markers scale with the capture: a 4K frame's Bullet Hole marker would
    # otherwise shrink to a couple of pixels in the contact sheet
    radius = max(OUTER_RADIUS, img.shape[1] // 100)
    for t in targets:
        x1, y1, x2, y2 = t.xyxy[0].cpu().numpy().astype(int)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), RECT_THICK)
    for b in bullet_holes:
        cv2.circle(img, tuple(get_center(b).astype(int)), radius, (0, 0, 255), OUTER_THICK)

    # the banner scales to the frame so the settings stay readable — and stay on
    # screen — whatever the capture's resolution and aspect
    font  = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.95 * img.shape[1] / cv2.getTextSize(caption, font, 1.0, 2)[0][0]
    (_, text_h), _ = cv2.getTextSize(caption, font, scale, 2)
    cv2.rectangle(img, (0, 0), (img.shape[1], int(text_h * 2)), (0, 0, 0), -1)
    cv2.putText(img, caption, (int(text_h * 0.3), int(text_h * 1.4)), font, scale,
                (255, 255, 255), max(1, int(scale * 2)))
    return img


def contact_sheet(cells, sizes, confidences):
    """One index image, inference size down the rows, confidence across."""
    def scaled(img):
        h = int(img.shape[0] * CONTACT_WIDTH / img.shape[1])
        return cv2.resize(img, (CONTACT_WIDTH, h))
    return np.vstack([np.hstack([scaled(cells[(c, s)]) for c in confidences])
                      for s in sizes])


def sweep(image_path, confidences, sizes, output_dir):
    from ultralytics import YOLO  # imported lazily: pulls in torch

    frame = cv2.imread(image_path)
    if frame is None:
        raise SystemExit(f"[ERROR] could not read {image_path}")
    os.makedirs(output_dir, exist_ok=True)
    model = YOLO(MODEL_PATH)

    # Ultralytics' own floor has to sit under the lowest cell, or it swallows
    # the boxes the grid is here to compare. Every cell in a row then filters
    # the same inference, so a row costs one model run rather than one per cell.
    model_floor = min(0.25, *confidences)

    cells, rows = {}, []
    for size in sizes:
        boxes = model(frame, imgsz=size, conf=model_floor)[0].boxes

        for conf in confidences:
            # A run of this cell would put the model floor at min(conf, 0.25),
            # so a Target scoring under that is one the pipeline never sees —
            # even though the row's shared inference admitted it.
            targets      = [b for b in boxes if int(b.cls[0]) == CLS_TARGET
                            and b.conf[0] >= min(conf, 0.25)]
            above_floor  = [b for b in boxes
                            if int(b.cls[0]) == CLS_BULLET_HOLE and b.conf[0] >= conf]
            bullet_holes = []
            # The pipeline discards a frame carrying no Target, so a cell that
            # misses the Target reports nothing however many boxes it found —
            # otherwise the sweep recommends a setting that yields zero in a run.
            for b in above_floor if targets else []:
                if not is_duplicate_bullet(b, bullet_holes):
                    bullet_holes.append(b)

            caption = (f"confidence={conf} inference_size={size}  ->  "
                       f"{len(bullet_holes)} Bullet Holes "
                       f"({len(above_floor)} before de-duplication), "
                       f"{len(targets)} Target(s)")
            cells[(conf, size)] = annotate_cell(frame, targets, bullet_holes, caption)
            cv2.imwrite(os.path.join(output_dir, f"confidence{conf}_size{size}.jpg"),
                        cells[(conf, size)])
            rows.append({'inference_size': size, 'confidence': conf,
                         'bullet_holes': len(bullet_holes),
                         'before_dedup': len(above_floor), 'targets': len(targets)})

    cv2.imwrite(os.path.join(output_dir, 'contact_sheet.jpg'),
                contact_sheet(cells, sizes, confidences))
    counts = pd.DataFrame(rows)
    counts.to_csv(os.path.join(output_dir, 'counts.csv'), index=False)
    return counts


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Capture Profile sweep over a single frame")
    p.add_argument("image", help="one representative frame of the Board")
    p.add_argument("--confidences", type=float, nargs='+', default=CONFIDENCES,
                   help="confidence column of the grid")
    p.add_argument("--inference-sizes", type=int, nargs='+', default=INFERENCE_SIZES,
                   help="inference-size row of the grid; multiples of 32")
    p.add_argument("--output-dir", default=OUTPUT_DIR)
    args = p.parse_args()

    counts = sweep(args.image, args.confidences, args.inference_sizes, args.output_dir)

    print("\nBullet Holes per grid cell (rows: inference size, columns: confidence)")
    print(counts.pivot(index='inference_size', columns='confidence', values='bullet_holes'))
    print(f"\n[INFO] annotated cells, contact_sheet.jpg and counts.csv → {args.output_dir}")
    print("[INFO] no setting is picked for you: compare against the Bullet Holes you can "
          "see on the Board, then add the winning cell to capture_profiles.json")
