import os, time, shutil
from pathlib import Path

# --- CONFIG ---
ARCHIVE_DIR = Path(r"F:\BirdFramer\archives")
DAYS_TO_KEEP = 7

# --- LOGGING ---
log_file = Path(r"F:\BirdFramer\scripts\cleanup_log.txt")
def log(msg):
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")

# --- CLEANUP ---
now = time.time()
cutoff = now - DAYS_TO_KEEP * 86400

if not ARCHIVE_DIR.exists():
    log(f"Archive folder not found: {ARCHIVE_DIR}")
    exit()

deleted = 0
for root, _, files in os.walk(ARCHIVE_DIR):
    for name in files:
        path = Path(root) / name
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
        except Exception as e:
            log(f"Could not delete {path}: {e}")

# Remove empty folders
for dirpath, dirnames, _ in os.walk(ARCHIVE_DIR, topdown=False):
    for d in dirnames:
        p = Path(dirpath) / d
        try:
            if not any(p.iterdir()):
                p.rmdir()
        except Exception:
            pass

log(f"Cleanup complete. Deleted {deleted} old files.")
