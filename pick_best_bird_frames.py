"""
pick_best_bird_frames.py
------------------------
Extracts the best bird frames from Reolink videos:
 - Detects birds with YOLOv8
 - Crops them and scores quality
 - Skips already-processed clips
 - Classifies each crop (species-ish) using a small vision model
"""

import os, math, glob, re, cv2, numpy as np
from pathlib import Path
from ultralytics import YOLO
from PIL import Image
import torch
import shutil, time
import json
from collections import Counter
from datetime import datetime, timedelta
import argparse
import piexif


# >>> update your paths <<<
# override input for one-shot test
INPUT_DIR = r"F:\BirdFramer\raw_videos"
global OUTPUT_DIR
OUTPUT_DIR = r"F:\BirdFramer\best_crops"        # where to save best frames
ARCHIVE_DIR = r"F:\BirdFramer\archives"           # <- new

Path(ARCHIVE_DIR).mkdir(parents=True, exist_ok=True)


def parse_video_start_datetime(name: str) -> datetime | None:
    """Extract the first timestamp (YYYYMMDDHHMMSS) from the video filename."""
    match = re.search(r"(\d{8})(\d{6})", name)
    if not match:
        return None
    stamp = "".join(match.groups())
    try:
        return datetime.strptime(stamp, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def as_exif_datetime(dt: datetime) -> str:
    """Format datetime for EXIF DateTime fields."""
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def build_user_comment(meta: dict) -> bytes:
    """Encode metadata dictionary into EXIF UserComment as ASCII JSON."""
    payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    return b"ASCII\0\0\0" + payload.encode("utf-8")


def iter_model_names(model):
    names = model.names
    if isinstance(names, dict):
        return names.items()
    return enumerate(names)


def class_name(model, cls_id: int) -> str:
    names = model.names
    if isinstance(names, dict):
        return names.get(cls_id, str(cls_id))
    if 0 <= cls_id < len(names):
        return str(names[cls_id])
    return str(cls_id)

def is_nighttime(filename, night_start=20, night_end=6):
    """
    Return True if filename timestamp indicates night hours.
    Example: 'Backyard-0-20251005174033-20251005174113.mp4'
    """
    import re
    m = re.search(r"(\d{8})(\d{6})", filename)
    if not m:
        return False
    date_str, time_str = m.groups()
    hour = int(time_str[:2])
    # e.g., 20–23 or 00–05
    return (hour >= night_start or hour < night_end)

def move_to_archive(video_path: str):
    """Move processed video into archives/YYYY-MM-DD/ with collision safety."""
    dt = time.strftime("%Y-%m-%d")  # or parse from filename if you prefer
    dest_dir = Path(ARCHIVE_DIR) / dt
    dest_dir.mkdir(parents=True, exist_ok=True)

    src = Path(video_path)
    dst = dest_dir / src.name
    # collision-safe rename
    if dst.exists():
        stem, suf = dst.stem, dst.suffix
        i = 1
        while (dest_dir / f"{stem}__{i}{suf}").exists():
            i += 1
        dst = dest_dir / f"{stem}__{i}{suf}"
    shutil.move(str(src), str(dst))
    return dst


def is_archived(video_name: str) -> bool:
    """Return True if a video with this name already exists in the archives tree."""
    archive_root = Path(ARCHIVE_DIR)
    if not archive_root.exists():
        return False
    return next(archive_root.rglob(video_name), None) is not None

# ---------- CONFIG ----------
FRAME_STEP_SEC = 1.00
CONF_THRESH = 0.50
TOP_N_PER_VIDEO = 8
MODEL_NAME = "yolov8m.pt"  # YOLO model to use
CROP_MARGIN = 0.15          # Margin for cropping around detected birds
AUTO_BIRD_CONF = 0.60       # YOLO confidence threshold to accept as bird
AUTO_BIRD_SCORE = 0.20      # Quality score threshold to accept as bird
# ----------------------------
def get_unprocessed_dir() -> Path:
    path = Path(OUTPUT_DIR) / "unprocessed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_path() -> Path:
    return Path(OUTPUT_DIR) / "classification_log.json"

# ===== Quality scoring helpers =====
def lap_var(gray): return cv2.Laplacian(gray, cv2.CV_64F).var()

def brightness(img): return np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)) / 255.0

def centeredness(box, W, H):
    x1, y1, x2, y2 = box
    bx, by = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = abs(bx - W / 2) / (W / 2), abs(by - H / 2) / (H / 2)
    return max(0, 1 - 0.7 * dx - 0.3 * dy)

def quality(img, box, conf, W, H):
    x1, y1, x2, y2 = map(int, box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(W, x2), min(H, y2)
    crop = img[y1:y2, x1:x2]
    if crop.size == 0: return 0, None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    sharp = lap_var(gray)
    bright = brightness(crop)
    cent = centeredness((x1, y1, x2, y2), W, H)
    sharp_n = math.tanh(math.log10(sharp + 1) / 2.0)
    score = 0.5 * sharp_n + 0.3 * bright + 0.2 * (cent * conf)
    return score, crop


# ===== Simple bird/not-bird heuristic =====
def infer_label(confidence: float, score: float) -> str:
    """Return 'bird' when confidence and quality are high, else 'not_bird'."""
    if confidence >= AUTO_BIRD_CONF and score >= AUTO_BIRD_SCORE:
        return "bird"
    return "not_bird"


# ===== Video processing =====
def process_video(path, model, bird_class_ids):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = int(max(1, fps * FRAME_STEP_SEC))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    candidates = []

    for i in range(0, frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok: break

        res = model(frame, conf=CONF_THRESH, verbose=False)
        boxes = []
        if res:
            for box in res[0].boxes:
                cls_tensor = box.cls
                cls_id = int(cls_tensor.item() if hasattr(cls_tensor, "item") else int(cls_tensor))
                if bird_class_ids and cls_id not in bird_class_ids:
                    continue
                boxes.append((box, cls_id))
            if boxes:
                detected = [class_name(model, cls) for _, cls in boxes]
                print(f"Detections in frame {i}:", detected)

        if not boxes and bird_class_ids and CONF_THRESH > 0.3:
            fallback_conf = max(0.2, CONF_THRESH * 0.5)
            fb_res = model(frame, conf=fallback_conf, verbose=False)
            if fb_res:
                for box in fb_res[0].boxes:
                    cls_tensor = box.cls
                    cls_id = int(cls_tensor.item() if hasattr(cls_tensor, "item") else int(cls_tensor))
                    if cls_id in bird_class_ids:
                        boxes.append((box, cls_id))
                if boxes:
                    detected = [class_name(model, cls) for _, cls in boxes]
                    print(f"[fallback conf {fallback_conf:.2f}] frame {i} detections:", detected)

        if not boxes:
            continue

        for box, _ in boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf_tensor = box.conf
            conf = float(conf_tensor.item() if hasattr(conf_tensor, "item") else conf_tensor)
            dx, dy = (x2 - x1) * CROP_MARGIN, (y2 - y1) * CROP_MARGIN
            score, crop = quality(frame, (x1 - dx, y1 - dy, x2 + dx, y2 + dy), conf, W, H)
            if crop is not None:
                candidates.append((score, crop, i, conf, fps))

    cap.release()
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[:TOP_N_PER_VIDEO]


# ===== Save outputs and classify =====
def save_outputs(video_path, picks):
    video_path = Path(video_path)
    base = video_path.stem
    video_name = video_path.name
    video_start_dt = parse_video_start_datetime(video_name)
    out_dir = get_unprocessed_dir()
    saved = []
    label_counts = Counter()
    for rank, (score, img, idx, confidence, fps) in enumerate(picks, start=1):
        label_guess = infer_label(confidence, score)
        label_counts[label_guess] += 1
        fn = out_dir / f"{base}_f{idx:05d}_s{score:.3f}_{label_guess}.jpg"
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}

        frame_offset = round(idx / fps, 6) if fps else None
        frame_dt = None
        if video_start_dt and frame_offset is not None:
            frame_dt = video_start_dt + timedelta(seconds=frame_offset)

        capture_dt = frame_dt or datetime.now()
        dt_str = as_exif_datetime(capture_dt)

        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = b"label:unprocessed"
        exif_dict["0th"][piexif.ImageIFD.DocumentName] = video_name.encode("utf-8", errors="ignore")
        exif_dict["0th"][piexif.ImageIFD.DateTime] = dt_str
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt_str
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str

        meta = {
            "filename": fn.name,
            "source_video": video_name,
            "source_video_path": str(video_path),
            "frame_index": idx,
            "frame_time_offset_sec": frame_offset,
            "frame_timestamp": frame_dt.isoformat() if frame_dt else None,
            "fps": fps,
            "yolo_confidence": round(confidence, 4),
            "quality_score": round(score, 4),
            "initial_label": label_guess,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

        exif_dict["Exif"][piexif.ExifIFD.UserComment] = build_user_comment(meta)
        exif_bytes = piexif.dump(exif_dict)
        pil_img.save(str(fn), format="JPEG", quality=98, exif=exif_bytes)
        saved.append(fn)
    return saved, label_counts



# ===== Main driver =====

def main():
    global OUTPUT_DIR
    parser = argparse.ArgumentParser(description="Extract best bird frames.")
    parser.add_argument("--single", help="Path to a single video file to process", default=None)
    parser.add_argument("--out", help="Override output folder", default=None)
    args = parser.parse_args()

    model = YOLO(MODEL_NAME)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model.to(device)
    print(f"Using device: {device}")

    bird_class_ids = {int(idx) for idx, name in iter_model_names(model) if isinstance(name, str) and "bird" in name.lower()}
    if bird_class_ids:
        print(f"Detected bird classes in model: {sorted(bird_class_ids)}")
    else:
        print("[warn] Could not locate 'bird' class in model names; using all classes for detection.")


    summary_log = []

    if args.out:
        OUTPUT_DIR = Path(args.out)
    else:
        OUTPUT_DIR = Path(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = get_log_path()

    if args.single:
        videos = [args.single]
        print(f"[single mode] 1 video selected: {videos[0]}")
    else:
        videos = []
        for ext in ("*.mp4", "*.mkv", "*.avi"):
            videos += glob.glob(os.path.join(INPUT_DIR, ext))
        print(f"Found {len(videos)} video(s).")

    # --- main loop ---
    for v in videos:
        video_path = Path(v)
        video_name = video_path.name

        if is_nighttime(video_name):
            print(f"[night] {v} (nighttime clip)")
            moved = move_to_archive(v)
            print(f"[archived-night] {moved}")
            continue

        if is_archived(video_name):
            print(f"[skip] {v} already archived.")
            continue

        print(f"[proc] {v}")
        picks = process_video(v, model, bird_class_ids)

        if not picks:
            print(f"[none] No birds found in {v}")
            moved = move_to_archive(v)
            print(f"[archived-none] {moved}")
            continue

        outs, label_counts = save_outputs(v, picks)
        print(f"[done] {len(outs)} best frames saved for {v}")

        record = {
            "video": Path(v).name,
            "label_counts": dict(label_counts),
            "total_frames": sum(label_counts.values()),
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }
        summary_log.append(record)

        moved = move_to_archive(v)
        print(f"[archived] {moved}")

    if summary_log:
        log_path.write_text(json.dumps(summary_log, indent=2))
        print(f"[log] Classification summary written to: {log_path}")

if __name__ == "__main__":
    main()
