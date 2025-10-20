from ultralytics import YOLO
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
print(BASE_DIR)
# Load your best model
model_path = os.path.join(BASE_DIR,'trained_models' ,'kanat_model10_v.2.0', 'weights', 'best.pt')


model = YOLO(model_path)

# Predict on video with safe exit
try:
    model.predict(
        source=os.path.join(BASE_DIR, 'videos', 'good_shooting_vid2.mp4'),  # or 0 for webcam
        show=True,  # show in real-time
        save=True,  # save the output to a file
        conf=0.5,  # confidence threshold
    )
except KeyboardInterrupt:
    print("\n[INFO] Prediction interrupted by user.")
    print("[INFO] Ensuring any buffered video output is finalized...")
    # No need to explicitly close files — Ultralytics handles this