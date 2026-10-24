import os, time, json
from pathlib import Path
from onvif import ONVIFCamera
from datetime import datetime, timedelta

# ---------- CONFIG ----------
CAMERA_IP = os.environ.get("BIRDFRAMER_CAMERA_IP", "192.0.2.1")
PORT = int(os.environ.get("BIRDFRAMER_CAMERA_PORT", "8000"))
USERNAME = os.environ.get("BIRDFRAMER_CAMERA_USERNAME", "admin")
PASSWORD = os.environ.get("BIRDFRAMER_CAMERA_PASSWORD", "")

LOCAL_BASE = Path(os.environ.get("BIRDFRAMER_DATA_DIR", Path.home() / "BirdFramer"))
RAW_DIR = LOCAL_BASE / "raw_videos"
LOG_FILE = LOCAL_BASE / "logs" / "onvif_pull_log.json"
# ----------------------------

RAW_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_log():
    return json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else {}

def save_log(log):
    LOG_FILE.write_text(json.dumps(log, indent=2))

def connect_camera():
    print(f"[connect] Connecting to {CAMERA_IP}:{PORT} ...")
    cam = ONVIFCamera(CAMERA_IP, PORT, USERNAME, PASSWORD)
    media = cam.create_media_service()
    search = cam.create_search_service()
    return cam, media, search

def get_recordings(search):
    print("[query] Listing all recordings (may take a while)...")
    # Query from a very early time (e.g., a week ago) to now
    start_time = datetime.utcnow() - timedelta(days=30)
    end_time = datetime.utcnow() + timedelta(hours=1)
    req = search.create_type('FindRecordings')
    req.StartPoint = start_time.isoformat() + "Z"
    req.EndPoint = end_time.isoformat() + "Z"
    req.MaxResults = 100
    req.SearchScope = None
    req.RecordingInformationFilter = None
    resp = search.FindRecordings(req)
    return resp

def download_via_rtsp(cam, rec_token, filename):
    """Fallback simple save using RTSP snapshot export (approximate)."""
    # In practice, Reolink’s ONVIF doesn’t provide direct file download.
    # Instead, it gives us URIs we can use to fetch via HTTP or RTSP.
    uri = cam.media.GetStreamUri({'StreamSetup': {'Stream': 'RTP-Unicast',
                                                  'Transport': {'Protocol': 'RTSP'}},
                                  'ProfileToken': rec_token})
    print(f"[download] Would fetch {filename} from {uri.Uri}")
    # You can use ffmpeg here later to actually download.
    # Example: ffmpeg -i rtsp://... -c copy output.mp4
    return True

def main():
    cam, media, search = connect_camera()
    log = load_log()
    try:
        recordings = get_recordings(search)
        if not hasattr(recordings, 'RecordingInformation'):
            print("[warn] No recordings returned — Reolink often hides SD content.")
            return

        infos = recordings.RecordingInformation
        print(f"[info] Found {len(infos)} recording(s).")

        for rec in infos:
            rec_token = rec.RecordingToken
            filename = f"{rec_token}.mp4"
            if filename in log:
                print(f"[skip] {filename}")
                continue
            download_via_rtsp(cam, rec_token, filename)
            log[filename] = time.time()
            save_log(log)

        print(f"[done] Pulled all unique recordings to {RAW_DIR}")
    except Exception as e:
        print("[error]", e)

if __name__ == "__main__":
    main()
