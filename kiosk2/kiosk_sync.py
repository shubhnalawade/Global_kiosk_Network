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
import logging
import requests

# =============================================================================
# CONFIGURATION
# =============================================================================

# Cloud server is assumed to be on the same machine (or change to LAN IP)
CLOUD_SERVER_URL = "http://127.0.0.1:5000"

# Anchor local upload directory to this script's location
_SYNC_DIR      = os.path.dirname(os.path.abspath(__file__))
LOCAL_BASE_DIR = os.path.join(_SYNC_DIR, "uploads")

# Kiosk identifier — must match the kiosk_id used in the UI
KIOSK_ID = "TB002"

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
      - Fetch pending files from cloud
      - Download any that are not yet local
      - Acknowledge completed downloads so the cloud can clean up
    """
    # --- Step 1: Fetch pending file list from cloud ---
    try:
        response = requests.get(
            f"{CLOUD_SERVER_URL}/fetch/{KIOSK_ID}", timeout=10
        )
    except requests.exceptions.ConnectionError:
        logging.error(f"Cannot connect to Cloud Server at {CLOUD_SERVER_URL}")
        return

    if response.status_code != 200:
        logging.error(f"Fetch returned {response.status_code}: {response.text}")
        return

    remote_files = response.json()
    if remote_files:
        logging.info(f"Found {len(remote_files)} pending file(s) on cloud.")

    # --- Step 2 & 3: Download new files and acknowledge ---
    for rf in remote_files:
        job_id   = rf["job_id"]
        filename = _truncate_filename(rf["filename"])

        # Build a clean download URL (guard against double slashes)
        safe_url     = rf["url"].lstrip("/")
        download_url = f"{CLOUD_SERVER_URL.rstrip('/')}/{safe_url}"

        local_path = os.path.join(kiosk_dir, filename)

        if os.path.exists(local_path):
            # File already downloaded — just re-send ACK to ensure cloud cleanup
            logging.info(f"Already have '{filename}'. Sending ACK.")
            try:
                requests.post(
                    f"{CLOUD_SERVER_URL}/ack/{KIOSK_ID}/{job_id}", timeout=5
                )
            except Exception as e:
                logging.error(f"ACK error for existing file ({job_id}): {e}")
            continue

        # Download the file
        logging.info(f"Downloading '{filename}' from {download_url}")
        try:
            file_resp = requests.get(download_url, timeout=30)
            file_resp.raise_for_status()

            with open(local_path, "wb") as f:
                f.write(file_resp.content)
            logging.info(f"Saved '{filename}' ({len(file_resp.content)} bytes)")

            # Acknowledge successful download to cloud
            ack_resp = requests.post(
                f"{CLOUD_SERVER_URL}/ack/{KIOSK_ID}/{job_id}", timeout=5
            )
            if ack_resp.status_code == 200:
                logging.info(f"ACK OK for job {job_id}")
            else:
                logging.warning(f"ACK failed for job {job_id}: {ack_resp.status_code}")

        except Exception as e:
            logging.error(f"Failed to download/save '{filename}': {e}")


def sync_loop() -> None:
    """Main sync loop — runs forever, polling the cloud every POLL_INTERVAL seconds."""
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
