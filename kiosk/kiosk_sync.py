import requests
import os
import time

# ---------------- CONFIG ----------------
# Use localhost for reliable local sync (Service runs on same machine as Cloud Server)
CLOUD_SERVER_URL = "http://127.0.0.1:5000"
# Use absolute path so sync works correctly from any working directory
_SYNC_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_BASE_DIR = os.path.join(_SYNC_DIR, "uploads")
KIOSK_ID = "TB001"
POLL_INTERVAL = 3  # seconds


import logging

# Setup logging
logging.basicConfig(
    filename='sync_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def sync_files():
    kiosk_dir = os.path.join(LOCAL_BASE_DIR, KIOSK_ID)
    os.makedirs(kiosk_dir, exist_ok=True)

    print(f"### KIOSK SYNC STARTED ###")
    logging.info("Kiosk Sync Service Started")
    logging.info(f"Kiosk ID: {KIOSK_ID}")
    logging.info(f"Cloud URL: {CLOUD_SERVER_URL}")
    logging.info(f"Local Dir: {kiosk_dir}")

    while True:
        try:
            # 1️⃣ Fetch pending files from cloud
            # logging.debug("Fetching files...")
            try:
                response = requests.get(f"{CLOUD_SERVER_URL}/fetch/{KIOSK_ID}", timeout=10)
            except requests.exceptions.ConnectionError:
                logging.error(f"Connection Failed to {CLOUD_SERVER_URL}")
                time.sleep(POLL_INTERVAL)
                continue

            if response.status_code != 200:
                logging.error(f"Fetch failed: {response.status_code} - {response.text}")
                time.sleep(POLL_INTERVAL)
                continue

            remote_files = response.json()
            if remote_files:
                logging.info(f"Found {len(remote_files)} pending files.")

            for rf in remote_files:
                job_id = rf["job_id"]
                filename = rf["filename"]
                # Fix double slash issue if present
                safe_url = rf["url"].lstrip("/")
                download_url = f"{CLOUD_SERVER_URL.rstrip('/')}/{safe_url}"
                
                # Truncate filename locally too just in case
                if len(filename) > 50:
                    name_part, ext_part = os.path.splitext(filename)
                    filename = name_part[:50] + ext_part

                local_path = os.path.join(kiosk_dir, filename)

                # 2️⃣ Download only if not already present
                if os.path.exists(local_path):
                    logging.info(f"File {filename} exists. Sending cleanup ACK.")
                    try:
                        requests.post(f"{CLOUD_SERVER_URL}/ack/{KIOSK_ID}/{job_id}", timeout=5)
                    except Exception as e:
                        logging.error(f"ACK Error: {e}")
                    continue

                logging.info(f"Downloading {filename} from {download_url}")

                try:
                    file_resp = requests.get(download_url, timeout=30)
                    file_resp.raise_for_status()

                    with open(local_path, "wb") as f:
                        f.write(file_resp.content)

                    logging.info(f"Saved {filename}")

                    # 3️⃣ ACK to cloud (safe delete)
                    ack_resp = requests.post(
                        f"{CLOUD_SERVER_URL}/ack/{KIOSK_ID}/{job_id}",
                        timeout=5
                    )

                    if ack_resp.status_code == 200:
                        logging.info(f"ACK Success for {job_id}")
                    else:
                        logging.warning(f"ACK Failed for {job_id}: {ack_resp.status_code}")

                except Exception as e:
                    logging.error(f"Download/Save Failed for {filename}: {e}")

        except Exception as e:
            logging.exception("Main Loop Error")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    sync_files()
