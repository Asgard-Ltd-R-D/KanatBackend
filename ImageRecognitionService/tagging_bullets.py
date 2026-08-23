import cv2
import numpy as np
import pandas as pd
from datetime import timedelta
from collections import defaultdict
import os
import argparse
import random

# === CONFIG ===
MODEL_PATH          = './trained_models/kanat_model10_v.2.0/weights/best.pt'
VIDEO_PATH          = './videos/test_video.mp4'
OUTPUT_DIR          = './video_output'
EXCEL_OUTPUT        = os.path.join(OUTPUT_DIR, 'bullet_results.xlsx')
IMAGE_SAVE_TEMPLATE = os.path.join(OUTPUT_DIR, 'bullet_{id}.jpg')
TARGET_SIZE_CM      = 18
IMGSZ               = 1280   # model was trained at 1280; ultralytics' 640 default misses most holes

# De-duplication gate. Two detections are the same Bullet Hole if their centres
# lie within DUP_CENTER_FACTOR x the mean box diagonal, or their boxes overlap
# by more than OVERLAP_THRESHOLD of the smaller box's area.
#
# 0.5 is measured, not chosen: across the sample images the closest genuinely
# distinct Bullet Holes sit 0.93x diagonal apart, while duplicate boxes of one
# Bullet Hole sit below 0.3x. The threshold sits in the empty gap between them.
# Box diagonals make it scale-invariant, so it needs no per-setup tuning — which
# is why it is not a Capture Profile field.
DUP_CENTER_FACTOR   = 0.5
OVERLAP_THRESHOLD   = 0.5
MIN_CONFIDENCE      = 0.6    # minimum confidence for bullet detection

# Annotation styling
OUTER_RADIUS = 12
OUTER_THICK  = 2
INNER_RADIUS = 4
MEAN_RADIUS  = 8
MEAN_THICK   = 2
RECT_THICK   = 2
FONT_SCALE   = 0.7
TEXT_THICK   = 2


os.makedirs(OUTPUT_DIR, exist_ok=True)

# === GLOBALS ===
target_color_map = {}  # target_id → BGR color
bullet_holes     = []  # each: dict(box, row) — one entry per unique Bullet Hole

# === HELPERS ===

def time_str_to_seconds(ts):
    h, m, s = map(int, ts.split(':'))
    return h*3600 + m*60 + s

def get_center(box):
    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
    return np.array([(x1 + x2) / 2, (y1 + y2) / 2])

def get_diag(box):
    return np.hypot(*box.xywh[0][2:].cpu().numpy())

def compute_overlap_percentage(box_a, box_b):
    """
    Calculate the overlap percentage between two bounding boxes.
    Returns the percentage of overlap relative to the smaller box area.
    """
    x1, y1, x2, y2 = box_a.xyxy[0].cpu().numpy()
    X1, Y1, X2, Y2 = box_b.xyxy[0].cpu().numpy()
    
    # Calculate intersection
    xi1, yi1 = max(x1, X1), max(y1, Y1)
    xi2, yi2 = min(x2, X2), min(y2, Y2)
    
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0  # No overlap
    
    intersection_area = (xi2 - xi1) * (yi2 - yi1)
    area_a = (x2 - x1) * (y2 - y1)
    area_b = (X2 - X1) * (Y2 - Y1)
    
    # Return overlap percentage relative to the smaller box
    smaller_area = min(area_a, area_b)
    return intersection_area / smaller_area if smaller_area > 0 else 0.0

def is_duplicate_bullet(new_box, existing_bullets):
    """Is this detection the same Bullet Hole as one already recorded?

    Same Bullet Hole if the centres lie within DUP_CENTER_FACTOR x the mean box
    diagonal, or the boxes overlap by more than OVERLAP_THRESHOLD of the
    smaller box's area.
    """
    new_center = get_center(new_box)
    new_diag   = get_diag(new_box)

    for i, existing_box in enumerate(existing_bullets):
        overlap_pct = compute_overlap_percentage(new_box, existing_box)
        if overlap_pct > OVERLAP_THRESHOLD:
            print(f"[DEBUG] Overlap detected: {overlap_pct*100:.1f}% with Bullet Hole {i+1}")
            return True

        existing_diag = get_diag(existing_box)
        distance      = np.linalg.norm(new_center - get_center(existing_box))
        if distance < DUP_CENTER_FACTOR * (new_diag + existing_diag) / 2:
            print(f"[DEBUG] Close center detected: {distance:.1f}px from Bullet Hole {i+1}")
            return True

    return False

def annotate(img, ctr, mean_range_cm, unused, tgt_box, tid, dist_cm, scale, tgt_ctr):
    # bullet
    cv2.circle(img, tuple(ctr.astype(int)), OUTER_RADIUS, (0,0,255), OUTER_THICK)
    cv2.circle(img, tuple(ctr.astype(int)), INNER_RADIUS, (0,0,255), -1)
    
    # Display mean range information
    cv2.putText(
        img,
        f"Range: {dist_cm:.1f}cm",
        tuple((ctr + np.array([OUTER_RADIUS, -OUTER_RADIUS])).astype(int)),
        cv2.FONT_HERSHEY_SIMPLEX,
        FONT_SCALE,
        (255,0,0),
        TEXT_THICK
    )
    
    # Display mean range if available
    if mean_range_cm > 0:
        cv2.putText(
            img,
            f"Mean: {mean_range_cm:.1f}cm",
            tuple((ctr + np.array([OUTER_RADIUS, -OUTER_RADIUS + 20])).astype(int)),
            cv2.FONT_HERSHEY_SIMPLEX,
            FONT_SCALE,
            (0,255,0),
            TEXT_THICK
        )
    
    # target box & label
    x1, y1, x2, y2 = tgt_box.xyxy[0].cpu().numpy().astype(int)
    col = target_color_map[tid]
    cv2.rectangle(img, (x1, y1), (x2, y2), col, RECT_THICK)
    cv2.putText(
        img,
        f"T{tid}",
        (x1 + 5, y1 - 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        FONT_SCALE,
        col,
        TEXT_THICK
    )

# === MAIN PROCESS ===

def process_video(start, end, detect=None, video_path=None):
    """Detect bullet holes between two timestamps.

    `detect` maps a frame to an iterable of detection boxes; defaults to the
    real YOLO model. Injecting it lets tests exercise the de-duplication logic
    without the (gitignored) weights or a torch install.
    """
    # module-level accumulators would otherwise leak between calls
    bullet_holes.clear()
    target_color_map.clear()

    cap    = cv2.VideoCapture(video_path or VIDEO_PATH)
    fps    = cap.get(cv2.CAP_PROP_FPS)
    startF = int(time_str_to_seconds(start) * fps)
    endF   = int(time_str_to_seconds(end)   * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, startF)

    if detect is None:
        from ultralytics import YOLO  # imported lazily: pulls in torch
        model  = YOLO(MODEL_PATH)
        detect = lambda frame: model(frame, imgsz=IMGSZ)[0].boxes
    # For each target ID, track all hit centers to compute relative means over time
    target_hits = defaultdict(list)
    bullet_id   = 0

    # Frame loop
    try:
        frame_idx = startF
        while cap.isOpened() and frame_idx < endF:
            ret, frame = cap.read()
            if not ret:
                break

            boxes   = detect(frame)
            tgts    = [b for b in boxes if int(b.cls[0]) == 2]
            blts    = [b for b in boxes if int(b.cls[0]) == 1]

            if not tgts:
                frame_idx += 1
                continue

            # assign target IDs/colors
            tgt_centers = [get_center(t) for t in tgts]
            sorted_idx  = sorted(enumerate(tgt_centers), key=lambda x: (x[1][1], x[1][0]))
            tid_map     = {orig: i+1 for i,(orig,_) in enumerate(sorted_idx)}
            if not target_color_map:
                target_color_map.update({tid: [random.randint(0,255) for _ in range(3)]
                                         for tid in tid_map.values()})

            # cm-per-pixel from first target
            w, h    = tgts[0].xywh[0][2:].cpu().numpy()
            scale   = TARGET_SIZE_CM / ((w + h) / 2)

            # process each bullet detection
            for b in blts:
                # Check confidence threshold
                if b.conf[0] < MIN_CONFIDENCE:
                    print(f"[INFO] Skipping low confidence detection: {b.conf[0]:.2f} < {MIN_CONFIDENCE}")
                    continue
                
                ctr = get_center(b)

                if is_duplicate_bullet(b, [h['box'] for h in bullet_holes]):
                    continue

                # new unique bullet → build metadata row
                # assign to nearest target
                dists   = [np.linalg.norm(ctr - tc) for tc in tgt_centers]
                ni      = int(np.argmin(dists))
                tid     = tid_map[ni]
                dist_cm = dists[ni] * scale

                # update relative-hit lists for mean range calculation
                target_hits[tid].append(ctr)
                
                # Calculate mean range (distance) to target center
                target_center = tgt_centers[ni]
                distances_to_target = []
                for hit_center in target_hits[tid]:
                    dist_px = np.linalg.norm(hit_center - target_center)
                    dist_cm_hit = dist_px * scale
                    distances_to_target.append(dist_cm_hit)
                
                mean_range_cm = np.mean(distances_to_target)

                # annotate & save snapshot
                bullet_id += 1
                ts_str     = str(timedelta(seconds=int(frame_idx / fps)))
                out_img    = frame.copy()
                annotate(out_img, ctr, mean_range_cm, 0, tgts[ni], tid, dist_cm, scale, tgt_centers[ni])  # Using mean_range_cm instead of mx_cm, my_cm
                snap_path  = IMAGE_SAVE_TEMPLATE.format(id=bullet_id)
                cv2.imwrite(snap_path, out_img)

                # record it → exactly one row per Bullet Hole
                row = {
                    "Bullet ID": bullet_id,
                    "Center X": int(ctr[0]),
                    "Center Y": int(ctr[1]),
                    "Mean Range to Target (cm)": round(mean_range_cm, 2),
                    "Dist to Target (cm)": round(dist_cm, 2),
                    "Target ID": tid,
                    "Timestamp": ts_str,
                    "Snapshot": snap_path
                }
                bullet_holes.append({'box': b, 'row': row})
                print(f"[INFO] New Bullet Hole: ID {bullet_id}, Target {tid}, Distance {dist_cm:.1f}cm")

            frame_idx += 1

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user — cleaning up…")

    finally:
        cap.release()

    # gather rows, exactly one per Bullet Hole
    rows = [h['row'] for h in bullet_holes]
    df   = pd.DataFrame(rows)
    df.to_excel(EXCEL_OUTPUT, index=False)
    print(f"[INFO] → {len(rows)} unique Bullet Holes saved to {EXCEL_OUTPUT}")
    return df


# === ENTRY POINT ===

if __name__ == "__main__":
    p = argparse.ArgumentParser("Video Bullet Detection with YOLOv11")
    p.add_argument("--start", required=True, help="Start HH:MM:SS")
    p.add_argument("--end",   required=True, help="End   HH:MM:SS")
    p.add_argument("--iou", type=float, default=0.5, 
                   help="Overlap threshold for duplicate detection (default: 0.5)")
    p.add_argument("--confidence", type=float, default=0.6,
                   help="Minimum confidence for bullet detection (default: 0.6)")
    args = p.parse_args()
    
    # Update global thresholds if provided
    if args.iou != 0.5:  # Compare with default value
        OVERLAP_THRESHOLD = args.iou
    print(f"[INFO] Using overlap threshold: {OVERLAP_THRESHOLD*100}%")
    
    if args.confidence != 0.6:
        MIN_CONFIDENCE = args.confidence
        print(f"[INFO] Using confidence threshold: {MIN_CONFIDENCE}")
    
    process_video(args.start, args.end)
