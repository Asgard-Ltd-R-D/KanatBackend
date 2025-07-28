import cv2
import numpy as np
from ultralytics import YOLO
from collections import defaultdict

# --- Constants ---
IMAGE_PATH = 'images/original.jpg'
MODEL_PATH = './trained_models/kanat_model9_v.2.0/weights/best.pt'
TARGET_SIZE_CM = 18  # Target is 18x18 cm

# --- Load image ---
image = cv2.imread(IMAGE_PATH)

# --- Load YOLOv11 Model ---
model = YOLO(MODEL_PATH)
results = model(image)

# --- Separate detected objects ---
targets = []
bullets = []

for box in results[0].boxes:
    cls = int(box.cls[0])
    if cls == 2:  # Target class
        targets.append(box)
    elif cls == 1:  # Bullet hole class
        bullets.append(box)

# --- Compute pixel/cm ratio using first target ---
if not targets:
    raise ValueError("No targets detected.")
target_box = targets[0] # taking the first target for pixel ratio measurement
x1, y1, x2, y2 = target_box.xyxy[0].tolist()
w_pixels = x2 - x1
h_pixels = y2 - y1

px_per_cm_w = w_pixels / TARGET_SIZE_CM
px_per_cm_h = h_pixels / TARGET_SIZE_CM
px_per_cm = (px_per_cm_w + px_per_cm_h) / 2
print(f"INFO: cm per pixel is in rate 1:{px_per_cm}")

# --- Utility function ---
def get_center(box):
    x1, y1, x2, y2 = box.xyxy[0]
    return np.array([(x1 + x2) / 2, (y1 + y2) / 2])

# --- Compute centers ---
bullet_centers = [get_center(b) for b in bullets]
target_centers = [get_center(t) for t in targets]

# --- Assign bullets to nearest targets ---
bullet_assignments = []
for bc in bullet_centers:
    distances = [np.linalg.norm(bc - tc) for tc in target_centers] # List of distances from center bullet{i} to center target{j}
    nearest_idx = np.argmin(distances) #Taking out the minimum distance
    bullet_assignments.append(nearest_idx)

# --- Draw distance annotations ---
for i, bullet_center in enumerate(bullet_centers):
    target_center = target_centers[bullet_assignments[i]]
    pixel_dist = np.linalg.norm(bullet_center - target_center)
    dist_cm = pixel_dist / px_per_cm

    cv2.circle(image, tuple(map(int, bullet_center)), 5, (0, 0, 255), -1)
    cv2.putText(
        image,
        f"{dist_cm:.2f} cm",
        tuple(map(int, bullet_center + np.array([5, -5]))),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 0, 0),
        1
    )
# --- Draw red bounding boxes around each target ---
for target in targets:
    x1, y1, x2, y2 = target.xyxy[0].cpu().numpy().astype(int)
    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 1)

# --- Draw mean hit points per target ---
target_hits = defaultdict(list)
for i, bullet_center in enumerate(bullet_centers):
    target_idx = bullet_assignments[i]
    target_hits[target_idx].append(bullet_center)

for target_idx, hits in target_hits.items():
    mean_hit = np.mean(hits, axis=0).astype(int)
    cv2.circle(image, tuple(mean_hit), 7, (0, 255, 0), -1)
    cv2.putText(
        image,
        "Mean",
        tuple(mean_hit + np.array([5, 5])),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 255, 0),
        1
    )

# --- Save or show output ---
cv2.imwrite('./images/annotated_output.jpg', image)
# cv2.imshow('Annotated Image', image)
# cv2.waitKey(0)
# cv2.destroyAllWindows()
