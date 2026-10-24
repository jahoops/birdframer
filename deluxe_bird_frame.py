import cv2
import torch
import argparse
from ultralytics import YOLO
from pathlib import Path
import numpy as np

# ---------- CONFIG ----------
MODEL_NAME = "yolov8s.pt"        # detection model
CONF_THRESH = 0.3                # lower to catch more possible detections
CROP_MARGIN = 0.15               # expand crop around the bird
UPSCALE = 2                      # 1=no upscale, 2=double size
# -----------------------------

def enhance_image(img):
    """Apply gentle enhancements for a deluxe look."""
    # Denoise a bit
    img = cv2.fastNlMeansDenoisingColored(img, None, 5, 5, 7, 15)
    # Slight color/contrast boost
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    cl = clahe.apply(l)
    merged = cv2.merge((cl, a, b))
    img = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    # Subtle sharpen
    sharp = cv2.GaussianBlur(img, (0, 0), 3)
    img = cv2.addWeighted(img, 1.4, sharp, -0.4, 0)
    # Optional upscale
    if UPSCALE > 1:
        img = cv2.resize(img, (0,0), fx=UPSCALE, fy=UPSCALE, interpolation=cv2.INTER_CUBIC)
    return img

def extract_frame(video_path, frame_index):
    """Extract a specific frame from video."""
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Could not read frame {frame_index} from {video_path}")
    return frame

def detect_and_crop(model, frame):
    """Run YOLO detection and return best bird crop."""
    H, W = frame.shape[:2]
    results = model.predict(frame, conf=CONF_THRESH, classes=[14], imgsz=1280, verbose=False)
    if not results or len(results[0].boxes) == 0:
        print("No bird detected.")
        return frame
    # pick largest box
    box = max(results[0].boxes, key=lambda b: (b.xyxy[0][2]-b.xyxy[0][0])*(b.xyxy[0][3]-b.xyxy[0][1]))
    x1, y1, x2, y2 = map(int, box.xyxy[0])
    # expand margin
    dx, dy = (x2 - x1) * CROP_MARGIN, (y2 - y1) * CROP_MARGIN
    x1, y1 = int(max(0, x1 - dx)), int(max(0, y1 - dy))
    x2, y2 = int(min(W, x2 + dx)), int(min(H, y2 + dy))
    return frame[y1:y2, x1:x2]

def main():
    parser = argparse.ArgumentParser(description="Deluxe bird frame reprocessor")
    parser.add_argument("--video", required=True, help="Path to MP4 file")
    parser.add_argument("--frame", type=int, required=True, help="Frame index to extract")
    parser.add_argument("--out", default="F:\\BirdFramer\\deluxe", help="Output folder")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")

    model = YOLO(MODEL_NAME)
    model.to(device)

    frame = extract_frame(args.video, args.frame)
    crop = detect_and_crop(model, frame)
    enhanced = enhance_image(crop)

    # Save PNG (lossless)
    out_file = out_dir / f"deluxe_{Path(args.video).stem}_f{args.frame:05d}.png"
    cv2.imwrite(str(out_file), enhanced, [int(cv2.IMWRITE_PNG_COMPRESSION), 2])
    print(f"[ok] Saved deluxe frame to {out_file}")

if __name__ == "__main__":
    main()
