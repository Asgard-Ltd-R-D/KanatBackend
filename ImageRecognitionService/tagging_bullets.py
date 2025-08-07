import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO
from collections import defaultdict
import os
import argparse
from datetime import timedelta
import random

# === CONFIG ===
MODEL_PATH           = './trained_models/kanat_model10_v.2.0/weights/best.pt'
VIDEO_PATH           = './videos/good_shooting_vid2.mp4'
OUTPUT_DIR           = './video_output'
EXCEL_OUTPUT         = os.path.join(OUTPUT_DIR, 'bullet_results.xlsx')
IMAGE_SAVE_TEMPLATE  = os.path.join(OUTPUT_DIR, 'bullet_{id}.jpg')

TARGET_SIZE_CM       = 18

# Duplicate-suppression thresholds
BULLET_MIN_DIST      = 5     # px (was 10)
IOU_THRESH           = 0.5   # only suppress when IoU > 0.5

# Annotation styling (thicker/bolder)
OUTER_RADIUS         = 12
OUTER_THICKNESS      = 2
INNER_RADIUS         = 4
MEAN_RADIUS          = 8
MEAN_THICKNESS       = 2
RECT_THICKNESS       = 2
FONT_SCALE           = 0.7
TEXT_THICKNESS       = 2

os.makedirs(OUTPUT_DIR, exist_ok=True)

# === GLOBALS ===
target_color_map   = {}   # target_id → [B, G, R]
seen_bullet_dict   = {}   # center_key → {'row': ..., 'box': ...}

# === HELPERS ===

def time_str_to_seconds(time_str):
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(time_str.split(":"))))

def get_center(box):
    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
    return np.array([(x1 + x2) / 2, (y1 + y2) / 2])

def compute_iou(boxA, boxB):
    xA1, yA1, xA2, yA2 = boxA.xyxy[0].cpu().numpy()
    xB1, yB1, xB2, yB2 = boxB.xyxy[0].cpu().numpy()
    xi1, yi1 = max(xA1, xB1), max(yA1, yB1)
    xi2, yi2 = min(xA2, xB2), min(yA2, yB2)
    interW, interH = max(0, xi2 - xi1), max(0, yi2 - yi1)
    interA = interW * interH
    areaA = (xA2 - xA1) * (yA2 - yA1)
    areaB = (xB2 - xB1) * (yB2 - yB1)
    return interA / (areaA + areaB - interA + 1e-6)

def find_seen_key(center, box, seen_dict):
    for prev_key, data in seen_dict.items():
        prev_ctr = np.array(prev_key)
        if np.linalg.norm(center - prev_ctr) < BULLET_MIN_DIST:
            return prev_key
        if compute_iou(data['box'], box) > IOU_THRESH:
            return prev_key
    return None

def assign_target_ids(centers):
    sorted_list = sorted(enumerate(centers), key=lambda x: (x[1][1], x[1][0]))
    return {orig_idx: new_id+1 for new_id, (orig_idx, _) in enumerate(sorted_list)}

def assign_target_colors(tids):
    return {tid: [random.randint(0,255) for _ in range(3)] for tid in tids}

def annotate_frame(img, bullet_ctr, mean_cm, tgt_box, tgt_id, dist_cm, cm_per_px, tgt_ctr_px):
    # pixel-offset for mean
    mean_px = tgt_ctr_px + (mean_cm / cm_per_px)

    # bullet outer + inner
    cv2.circle(img, tuple(bullet_ctr.astype(int)), OUTER_RADIUS, (0,0,255), OUTER_THICKNESS)
    cv2.circle(img, tuple(bullet_ctr.astype(int)), INNER_RADIUS, (0,0,255), -1)

    # mean hit
    cv2.circle(img, tuple(mean_px.astype(int)), MEAN_RADIUS, (0,255,0), MEAN_THICKNESS)
    cv2.putText(
        img,
        f"{dist_cm:.2f} cm",
        tuple((bullet_ctr + np.array([OUTER_RADIUS, -OUTER_RADIUS])).astype(int)),
        cv2.FONT_HERSHEY_SIMPLEX,
        FONT_SCALE,
        (255,0,0),
        TEXT_THICKNESS
    )

    # target box + label
    x1,y1,x2,y2 = tgt_box.xyxy[0].cpu().numpy().astype(int)
    color = target_color_map[tgt_id]
    cv2.rectangle(img, (x1,y1), (x2,y2), color, RECT_THICKNESS)
    cv2.putText(
        img,
        f"Target {tgt_id}",
        (x1+5, y1-5),
        cv2.FONT_HERSHEY_SIMPLEX,
        FONT_SCALE,
        color,
        TEXT_THICKNESS
    )

# === MAIN PROCESS ===

def process_video(start_time, end_time):
    cap       = cv2.VideoCapture(VIDEO_PATH)
    fps       = cap.get(cv2.CAP_PROP_FPS)
    start_fr  = int(time_str_to_seconds(start_time) * fps)
    end_fr    = int(time_str_to_seconds(end_time)   * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_fr)

    model         = YOLO(MODEL_PATH)
    target_hits   = defaultdict(list)
    bullet_count  = 0
    rows          = []
    frame_idx     = start_fr

    try:
        while cap.isOpened() and frame_idx < end_fr:
            ret, frame = cap.read()
            if not ret:
                break

            res     = model(frame)[0]
            boxes   = res.boxes
            targets = [b for b in boxes if int(b.cls[0]) == 2]
            bullets = [b for b in boxes if int(b.cls[0]) == 1]

            if not targets:
                frame_idx += 1
                continue

            # assign target IDs & colors
            centers  = [get_center(t) for t in targets]
            tid_map  = assign_target_ids(centers)
            if not target_color_map:
                target_color_map.update(assign_target_colors(tid_map.values()))

            # scale cm/px
            w,h      = targets[0].xywh[0][2:].cpu().numpy()
            cm_per_px= TARGET_SIZE_CM / ((w+h)/2)

            for b in bullets:
                ctr    = get_center(b)
                key    = (int(ctr[0]), int(ctr[1]))
                seen_k = find_seen_key(ctr, b, seen_bullet_dict)
                if seen_k is not None:
                    # already processed
                    continue

                # brand-new bullet →
                dists  = [np.linalg.norm(ctr - c) for c in centers]
                ni     = int(np.argmin(dists))
                tgt_b  = targets[ni]
                tgt_ctr= centers[ni]
                tgt_id = tid_map[ni]
                dist_cm= dists[ni] * cm_per_px

                bullet_count += 1
                target_hits[tgt_id].append(ctr)
                mean_px = np.mean(target_hits[tgt_id], axis=0)
                mean_cm = (mean_px - tgt_ctr) * cm_per_px

                ts_str = str(timedelta(seconds=int(frame_idx/fps)))
                out   = frame.copy()
                annotate_frame(out, ctr, mean_cm, tgt_b, tgt_id, dist_cm, cm_per_px, tgt_ctr)

                path  = IMAGE_SAVE_TEMPLATE.format(id=bullet_count)
                cv2.imwrite(path, out)

                # row
                row = {
                    "Bullet ID": bullet_count,
                    "Position": key,
                    "Dist (cm)": round(dist_cm,2),
                    "Target ID": tgt_id,
                    "Timestamp": ts_str,
                    "Snapshot": path
                }
                # mean hits
                for t in sorted(target_color_map):
                    if t == tgt_id:
                        row[f"MeanHit T{t}"] = (round(mean_cm[0],2), round(mean_cm[1],2))
                    else:
                        row[f"MeanHit T{t}"] = 'X'

                rows.append(row)
                seen_bullet_dict[key] = {'row': row, 'box': b}

            frame_idx += 1

    except KeyboardInterrupt:
        print("\n[INFO] User interrupted.")

    finally:
        cap.release()
        cv2.destroyAllWindows()

    # save Excel
    pd.DataFrame(rows).to_excel(EXCEL_OUTPUT, index=False)
    print(f"[INFO] → {len(rows)} bullets saved in {EXCEL_OUTPUT}")
    print(f"[INFO] Unique bullets detected: {len(seen_bullet_dict)}")


# === ENTRY POINT ===

if __name__ == "__main__":
    p = argparse.ArgumentParser("Video Bullet Detection with YOLOv11")
    p.add_argument("--start", required=True, help="HH:MM:SS")
    p.add_argument("--end",   required=True, help="HH:MM:SS")
    args = p.parse_args()
    process_video(args.start, args.end)
