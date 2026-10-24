"""
scan_backyard_metadata.py
-------------------------
Utility for crawling F:\BirdFramer\best_crops and extracting the rich metadata
that `pick_best_bird_frames.py` embeds into each JPG. The script searches for
folders beginning with "Backyard" (recursing into their subfolders) and emits a
JSON report for every image discovered.

Usage
~~~~~
    # Print JSON to stdout
    python scan_backyard_metadata.py

    # Write the report to a file instead
    python scan_backyard_metadata.py --output report.json
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Tuple

import piexif

BASE_DIR = Path(r"F:\BirdFramer\best_crops")
FOLDER_PREFIX = "Backyard"


def iter_backyard_folders(base_dir: Path) -> list[Path]:
    """Return all direct child directories whose names start with the prefix."""
    return [child for child in base_dir.iterdir() if child.is_dir() and child.name.startswith(FOLDER_PREFIX)]


def decode_user_comment(raw: bytes | None) -> Tuple[str | None, Dict[str, Any] | None]:
    """Decode EXIF UserComment bytes and return the raw string plus parsed JSON if available."""
    if not raw:
        return None, None

    payload = raw
    ascii_prefix = b"ASCII\0\0\0"
    if payload.startswith(ascii_prefix):
        payload = payload[len(ascii_prefix) :]

    try:
        text = payload.decode("utf-8", errors="ignore")
    except Exception:
        return None, None

    if not text:
        return None, None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    return text, parsed


def extract_metadata(image_path: Path) -> Dict[str, Any]:
    """Pull metadata fields that mirror the structure produced in pick_best_bird_frames."""
    record: Dict[str, Any] = {
        "path": str(image_path),
        "filename": image_path.name,
        "folder": str(image_path.parent.relative_to(BASE_DIR)),
    }

    try:
        exif_dict = piexif.load(str(image_path))
    except Exception as exc:  # pragma: no cover - defensive logging
        record["error"] = f"EXIF load failed: {exc}"
        return record

    zeroth = exif_dict.get("0th", {})
    exif = exif_dict.get("Exif", {})

    description = zeroth.get(piexif.ImageIFD.ImageDescription)
    document_name = zeroth.get(piexif.ImageIFD.DocumentName)
    datetime_tag = zeroth.get(piexif.ImageIFD.DateTime)
    datetime_original = exif.get(piexif.ExifIFD.DateTimeOriginal)
    datetime_digitized = exif.get(piexif.ExifIFD.DateTimeDigitized)
    user_comment_raw, user_comment = decode_user_comment(exif.get(piexif.ExifIFD.UserComment))

    if description:
        record["image_description"] = description.decode("utf-8", errors="ignore") if isinstance(description, bytes) else str(description)
    if document_name:
        record["document_name"] = document_name.decode("utf-8", errors="ignore") if isinstance(document_name, bytes) else str(document_name)
    if datetime_tag:
        record["datetime"] = datetime_tag.decode("utf-8", errors="ignore") if isinstance(datetime_tag, bytes) else str(datetime_tag)
    if datetime_original:
        record["datetime_original"] = datetime_original.decode("utf-8", errors="ignore") if isinstance(datetime_original, bytes) else str(datetime_original)
    if datetime_digitized:
        record["datetime_digitized"] = datetime_digitized.decode("utf-8", errors="ignore") if isinstance(datetime_digitized, bytes) else str(datetime_digitized)
    if user_comment_raw:
        record["user_comment_raw"] = user_comment_raw
    if user_comment:
        record["user_comment"] = user_comment

    # When the UserComment JSON was written by pick_best_bird_frames.py, surface
    # its keys at the top level as well for easier analysis.
    if isinstance(user_comment, dict):
        record.update({key: value for key, value in user_comment.items() if key not in record})

    return record


def scan(base_dir: Path, move: bool) -> list[Dict[str, Any]]:
    """Walk the Backyard folders and return a list of metadata records.

    When ``move`` is True, each processed file is moved into the unprocessed
    gallery root after its metadata is collected.
    """
    results: list[Dict[str, Any]] = []
    destination_root = base_dir / "unprocessed"

    for folder in iter_backyard_folders(base_dir):
        for image_path in folder.rglob("*.jpg"):
            record = extract_metadata(image_path)
            results.append(record)

            if move:
                destination_root.mkdir(parents=True, exist_ok=True)
                target = destination_root / image_path.name
                if target.exists():
                    record.setdefault("move_warning", "destination already exists; source left in place")
                else:
                    shutil.move(str(image_path), str(target))
                    record["moved_to"] = str(target)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan Backyard folders for EXIF metadata and optionally move files.")
    parser.add_argument("--base", type=Path, default=BASE_DIR, help="Root directory to scan (default: %(default)s)")
    parser.add_argument("--output", type=Path, help="If provided, write JSON array to this file instead of stdout")
    parser.add_argument("--move", action="store_true", help="Move each processed JPG into the unprocessed folder")
    args = parser.parse_args()

    base_dir = args.base
    if not base_dir.exists():
        raise SystemExit(f"Base directory not found: {base_dir}")

    records = scan(base_dir, move=args.move)
    payload = json.dumps(records, indent=2, ensure_ascii=False)

    if args.output:
        args.output.write_text(payload, encoding="utf-8")
        print(f"[ok] Wrote {len(records)} records to {args.output}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
