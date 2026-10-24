"""
cleanup_videos_reolink.py
-------------------------
Handles Reolink-style filenames like:
    Backyard-0-20251026220234-20251026220302.mp4

Deletes duplicates (same name + size)
and any captured between 20:00–05:59.
Logs everything to JSON.
"""

import re, json, time, shutil
from pathlib import Path

# ---------- CONFIG ----------
BASE = Path(r"F:\BirdFramer\raw_videos")
VIDEO_EXTS = {".mp4", ".avi", ".mkv"}
LOG_FILE = BASE / f"cleanup_log_{time.strftime('%Y%m%d_%H%M%S')}.json"
MOVE_TO_TRASH = False  # change to True to move instead of delete
TRASH_DIR = BASE / "_trash"
# ----------------------------

def extract_hour_from_reolink(name: str):
    """
    Parse Reolink filenames like:
    Backyard-0-20251026220234-20251026220302.mp4
    Return start_hour (int) if possible.
    """
    m = re.search(r"-(\d{8})(\d{6})-", name)
    if not m:
        return None
    try:
        hour = int(m.group(2)[:2])
        return hour
    except Exception:
        return None

def delete_or_move(path, reason):
    if MOVE_TO_TRASH:
        TRASH_DIR.mkdir(exist_ok=True)
        dest = TRASH_DIR / path.name
        shutil.move(str(path), dest)
        return str(dest)
    else:
        path.unlink(missing_ok=True)
        return None

def main():
    actions = []
    seen = {}
    dup_count = 0
    night_count = 0
    total = 0

    for path in BASE.rglob("*"):
        if path.suffix.lower() not in VIDEO_EXTS or not path.is_file():
            continue
        total += 1

        size = path.stat().st_size
        name = path.name.lower()
        hour = extract_hour_from_reolink(name)

        # --- Nighttime deletion ---
        if hour is not None and (hour >= 20 or hour < 6):
            newloc = delete_or_move(path, "night")
            night_count += 1
            actions.append({
                "action": "delete_night",
                "file": str(path),
                "moved_to": newloc,
                "hour": hour
            })
            continue

        # --- Duplicate deletion ---
        key = (name, size)
        if key in seen:
            newloc = delete_or_move(path, "duplicate")
            dup_count += 1
            actions.append({
                "action": "delete_duplicate",
                "file": str(path),
                "moved_to": newloc
            })
            continue

        seen[key] = str(path)
        actions.append({"action": "keep", "file": str(path)})

    summary = {
        "scanned": total,
        "deleted_duplicates": dup_count,
        "deleted_nighttime": night_count,
        "remaining_unique": len(seen),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "moved to trash" if MOVE_TO_TRASH else "deleted"
    }

    log = {"summary": summary, "actions": actions}
    LOG_FILE.write_text(json.dumps(log, indent=2), encoding="utf-8")

    print(f"\n[done] Scanned {total} videos.")
    print(f"       Deleted {dup_count} duplicates, {night_count} night clips.")
    print(f"       Log written to {LOG_FILE}")

if __name__ == "__main__":
    main()
