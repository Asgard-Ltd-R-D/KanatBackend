import cv2
import numpy as np
from ultralytics import YOLO
from collections import defaultdict

# --- Constants ---
IMAGE_NAME="shear2"
IMAGE_PATH = f'images/{IMAGE_NAME}.jpg'
MODEL_PATH = './trained_models/kanat_model10_v.2.0/weights/best.pt'
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

# --- Compute cm_per_pixel using first target ---
if not targets:
    raise ValueError("No targets detected.")
target_box = targets[0]  # use the first detected target

# get pixel coordinates as floats
x1, y1, x2, y2 = target_box.xyxy[0].cpu().numpy().tolist()
w_pixels = x2 - x1
h_pixels = y2 - y1

# average the two dimensions to reduce noise
avg_pixels = (w_pixels + h_pixels) / 2.0

# compute centimeters per pixel
cm_per_pixel = TARGET_SIZE_CM / avg_pixels
print(f"INFO: each pixel ≈ {cm_per_pixel:.4f} cm")

# --- Utility function ---
def get_center(box):
    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
    return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0])

# --- Compute centers ---
bullet_centers = [get_center(b) for b in bullets]
target_centers = [get_center(t) for t in targets]

# --- Assign bullets to the nearest targets ---
bullet_assignments = []
for bc in bullet_centers:
    distances = [np.linalg.norm(bc - tc) for tc in target_centers]
    nearest_idx = int(np.argmin(distances))
    bullet_assignments.append(nearest_idx)

# --- Draw distance annotations ---
for i, bullet_center in enumerate(bullet_centers):
    target_center = target_centers[bullet_assignments[i]]
    pixel_dist = np.linalg.norm(bullet_center - target_center)
    dist_cm = pixel_dist * cm_per_pixel

    # Draw thin circle around bullet
    cv2.circle(image, tuple(map(int, bullet_center)), 8, (0, 255, 255), 1)  # Thin yellow circle
    # Draw pixelized dot in center of bullet hole
    cv2.circle(image, tuple(map(int, bullet_center)), 2, (0, 0, 255), -1)  # Small red dot
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
    # Mark center of target with a cross
    target_center = get_center(target)
    center_x, center_y = map(int, target_center)
    cv2.line(image, (center_x-5, center_y), (center_x+5, center_y), (255, 0, 0), 2)  # Horizontal line
    cv2.line(image, (center_x, center_y-5), (center_x, center_y+5), (255, 0, 0), 2)  # Vertical line



# --- Draw mean hit points per target ---
target_hits = defaultdict(list)
for i, bc in enumerate(bullet_centers):
    target_idx = bullet_assignments[i]
    target_hits[target_idx].append(bc)

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
cv2.imwrite(f'./images/{IMAGE_NAME}Process.jpg', image)
# cv2.imshow('Annotated Image', image)
# cv2.waitKey(0)
# cv2.destroyAllWindows()
