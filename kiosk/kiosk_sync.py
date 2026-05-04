"""
kiosk/kiosk_sync.py
====================
Kiosk Sync Service — polls the Cloud Server for pending uploads and
downloads them to the local kiosk upload directory.

Workflow per poll cycle:
  1. GET  /fetch/<kiosk_id>       — list pending files on cloud
  2. GET  /download/<kiosk_id>/<filename> — download each new file
  3. POST /ack/<kiosk_id>/<job_id>         — tell cloud to clean up its copy

Run this as a standalone script; it loops forever with a configurable interval.
"""

import os
import time
import json
import logging


# =============================================================================
# CONFIGURATION
# =============================================================================

# Anchor local upload directory to this script's location
_SYNC_DIR      = os.path.dirname(os.path.abspath(__file__))
LOCAL_BASE_DIR = os.path.join(_SYNC_DIR, "uploads")

# Kiosk identifier — must match the kiosk_id used in the UI
KIOSK_ID = "TB001"

# Polling interval in seconds
POLL_INTERVAL = 3

# =============================================================================
# LOGGING
# =============================================================================

LOG_FILE = os.path.join(_SYNC_DIR, "sync_debug.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# =============================================================================

# CLOUD SERVER CONFIGURATION
import requests
CLOUD_SERVER_URL = "http://127.0.0.1:5000"

# =============================================================================
# SYNC LOGIC
# =============================================================================

def _truncate_filename(filename: str, max_len: int = 50) -> str:
    """Truncate filename stem to avoid Windows MAX_PATH issues."""
    if len(filename) <= max_len:
        return filename
    name, ext = os.path.splitext(filename)
    return name[:max_len] + ext



def sync_once(kiosk_dir: str) -> None:
    """
    Perform a single sync pass:
      - Fetch pending files from cloud server
      - Download any that are not yet local
      - Acknowledge completed downloads so cloud can clean up
    """
    # --- Step 1: Fetch pending file list from cloud server ---
    try:
        resp = requests.get(f"{CLOUD_SERVER_URL}/fetch/{KIOSK_ID}")
        if resp.status_code != 200:
            logging.error(f"Failed to fetch files from cloud: {resp.text}")
            return
        remote_files = resp.json()
        logging.info(f"Found {len(remote_files)} pending file(s) on cloud.")
    except Exception as e:
        logging.error(f"Failed to fetch files from cloud: {e}")
        return

    # --- Step 2 & 3: Download new files and acknowledge ---
    for rf in remote_files:
        filename = rf["filename"]
        job_id = rf["job_id"]
        if filename.endswith(".meta") or "_" not in filename:
            continue

        local_path = os.path.join(kiosk_dir, filename)

        if os.path.exists(local_path):
            logging.info(f"Already have '{filename}'. Skipping download.")
            continue

        # Download the file
        logging.info(f"Downloading '{filename}' from cloud server")
        try:
            file_url = f"{CLOUD_SERVER_URL}/download/{KIOSK_ID}/{filename}"
            file_resp = requests.get(file_url)
            if file_resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(file_resp.content)
                logging.info(f"Saved '{filename}' ({len(file_resp.content)} bytes)")
                # Acknowledge download
                ack_url = f"{CLOUD_SERVER_URL}/ack/{KIOSK_ID}/{job_id}"
                try:
                    requests.post(ack_url)
                except Exception as e:
                    logging.error(f"Failed to acknowledge file '{filename}': {e}")
            else:
                logging.error(f"Failed to download '{filename}': {file_resp.text}")
        except Exception as e:
            logging.error(f"Failed to download/save '{filename}': {e}")


def sync_loop() -> None:
    """Main sync loop — runs forever, polling Supabase every POLL_INTERVAL seconds."""
    kiosk_dir = os.path.join(LOCAL_BASE_DIR, KIOSK_ID)
    os.makedirs(kiosk_dir, exist_ok=True)

    print("### KIOSK SYNC SERVICE STARTED ###")
    logging.info("Kiosk Sync Service Started")
    logging.info(f"  Kiosk ID  : {KIOSK_ID}")
    logging.info(f"  Cloud URL : {CLOUD_SERVER_URL}")
    logging.info(f"  Local Dir : {kiosk_dir}")

    while True:
        try:
            sync_once(kiosk_dir)
        except Exception:
            logging.exception("Unexpected error in sync loop")
        time.sleep(POLL_INTERVAL)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    sync_loop()
