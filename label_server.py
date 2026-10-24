# label_server.py
from flask import Flask, request, jsonify, send_file, abort
from pathlib import Path
import shutil
from PIL import Image
import piexif
import os

BASE = Path(r"F:\BirdFramer\best_crops")

app = Flask(
    __name__,
    static_folder=str(BASE),  # allow direct access to generated gallery assets
    static_url_path=""
)


@app.get("/")
def serve_index():
    """Serve the gallery landing page so the sorter UI loads."""
    index_path = BASE / "index.html"
    if index_path.exists():
        return send_file(index_path)
    abort(404, description="Gallery index.html not found. Run add_gallery.py first.")

def write_label(image_path: Path, label: str):
    """Embed the label in the JPEG metadata (EXIF 'ImageDescription')."""
    try:
        img = Image.open(image_path)
        exif_dict = piexif.load(img.info.get("exif", b""))
        user_comment = f"label:{label}"
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = user_comment.encode("utf-8")
        exif_bytes = piexif.dump(exif_dict)
        img.save(image_path, exif=exif_bytes, quality=92)
        print(f"[exif] {image_path.name} tagged as '{label}'")
    except Exception as e:
        print(f"[warn] Could not write EXIF label for {image_path}: {e}")

@app.post("/move")
def move_image():
    data = request.get_json()
    src_rel = data.get("src")
    label = data.get("label")
    if not src_rel or not label:
        return jsonify({"error": "Missing src or label"}), 400

    src = BASE / src_rel
    if not src.exists():
        return jsonify({"error": f"File not found: {src_rel}"}), 404

    parent = src.parent.parent  # go up to mp4-named parent folder
    dest_dir = parent / label
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    try:
        shutil.move(src, dest)
        write_label(dest, label)
        return jsonify({"ok": True, "moved_to": str(dest.relative_to(BASE))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
