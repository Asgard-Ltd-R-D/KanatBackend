"""Capture Profile sweep: run a confidence x inference-size grid over one frame.

Operator tooling, deliberately outside the processing pipeline. It shows what
each candidate setting detects; it does not pick one. Auto-selecting by highest
count optimises straight into false positives — at low confidence the detector
emits far more boxes than there are Bullet Holes.

    python sweep_profile.py images/board.jpg

Look at the annotated images, compare against the holes you can see on the
Board, then copy the winning cell's numbers into capture_profiles.json.
"""
import argparse
import os

import cv2
import numpy as np
import pandas as pd

from tagging_bullets import (MODEL_PATH, RECT_THICK, get_center,
                             is_duplicate_bullet)

CONFIDENCES     = [0.30, 0.40, 0.50, 0.60]
INFERENCE_SIZES = [1280, 1600, 1920]
OUTPUT_DIR      = './sweep_output'
CONTACT_WIDTH   = 800  # per cell in the contact sheet; the full-res cells carry the detail


def annotate(frame, targets, holes, caption):
    img = frame.copy()
    for t in targets:
        x1, y1, x2, y2 = t.xyxy[0].cpu().numpy().astype(int)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), RECT_THICK)
    for h in holes:
        cv2.circle(img, tuple(get_center(h).astype(int)), 12, (0, 0, 255), 2)
    # scale the banner to the frame so the settings stay readable — and stay on
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
    model = YOLO(MODEL_PATH)

    frame = cv2.imread(image_path)
    if frame is None:
        raise SystemExit(f"[ERROR] could not read {image_path}")
    os.makedirs(output_dir, exist_ok=True)

    cells, rows = {}, []
    for size in sizes:
        for conf in confidences:
            # Same call the pipeline makes: ultralytics filters at 0.25 by
            # default, which would swallow a lower floor before we see it.
            boxes   = model(frame, imgsz=size, conf=min(conf, 0.25))[0].boxes
            targets = [b for b in boxes if int(b.cls[0]) == 2]
            raw     = [b for b in boxes if int(b.cls[0]) == 1 and b.conf[0] >= conf]

            holes = []  # de-duplicated, so the count matches what the pipeline reports
            for b in raw:
                if not is_duplicate_bullet(b, holes):
                    holes.append(b)

            caption = f"conf={conf} inference_size={size}  ->  {len(holes)} holes ({len(raw)} raw), {len(targets)} target(s)"
            cells[(conf, size)] = annotate(frame, targets, holes, caption)
            cv2.imwrite(os.path.join(output_dir, f"conf{conf}_size{size}.jpg"), cells[(conf, size)])
            rows.append({'inference_size': size, 'confidence': conf,
                         'holes': len(holes), 'raw': len(raw), 'targets': len(targets)})

    cv2.imwrite(os.path.join(output_dir, 'contact_sheet.jpg'),
                contact_sheet(cells, sizes, confidences))
    counts = pd.DataFrame(rows)
    counts.to_csv(os.path.join(output_dir, 'counts.csv'), index=False)
    return counts


if __name__ == "__main__":
    p = argparse.ArgumentParser("Capture Profile sweep over a single frame")
    p.add_argument("image", help="one representative frame of the Board")
    p.add_argument("--confidences", type=float, nargs='+', default=CONFIDENCES)
    p.add_argument("--inference-sizes", type=int, nargs='+', default=INFERENCE_SIZES,
                   help="multiples of 32")
    p.add_argument("--output-dir", default=OUTPUT_DIR)
    args = p.parse_args()

    counts = sweep(args.image, args.confidences, args.inference_sizes, args.output_dir)

    print("\nBullet Holes per grid cell (rows: inference size, columns: confidence)")
    print(counts.pivot(index='inference_size', columns='confidence', values='holes'))
    print(f"\n[INFO] annotated cells, contact_sheet.jpg and counts.csv → {args.output_dir}")
    print("[INFO] no setting is picked for you: compare against the holes you can see "
          "on the Board, then add the winning cell to capture_profiles.json")
