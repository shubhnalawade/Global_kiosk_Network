import requests
import os
import time

# ---------------- CONFIG ----------------
CLOUD_SERVER_URL = "http://127.0.0.1:5000"   # Change to cloud IP/domain if remote
LOCAL_BASE_DIR = "uploads"
KIOSK_ID = "TB001"
POLL_INTERVAL = 3  # seconds


def sync_files():
    kiosk_dir = os.path.join(LOCAL_BASE_DIR, KIOSK_ID)
    os.makedirs(kiosk_dir, exist_ok=True)

    print(f"### KIOSK SYNC STARTED ###")
    print(f"Kiosk ID        : {KIOSK_ID}")
    print(f"Cloud Server   : {CLOUD_SERVER_URL}")
    print(f"Local Storage  : {kiosk_dir}")

    while True:
        try:
            # 1️⃣ Fetch pending files from cloud
            response = requests.get(f"{CLOUD_SERVER_URL}/fetch/{KIOSK_ID}", timeout=10)

            if response.status_code != 200:
                print(f"[ERROR] Fetch failed: {response.status_code}")
                time.sleep(POLL_INTERVAL)
                continue

            remote_files = response.json()

            for rf in remote_files:
                job_id = rf["job_id"]
                filename = rf["filename"]
                download_url = CLOUD_SERVER_URL + rf["url"]
                local_path = os.path.join(kiosk_dir, filename)

                # 2️⃣ Download only if not already present
                if os.path.exists(local_path):
                    # If it exists locally but cloud still has it, we must have failed to ACK previously.
                    # Send ACK now to ensure cloud deletes it.
                    print(f"[SYNC CHECK] Found {filename} locally. Sending cleanup ACK to cloud.")
                    try:
                        requests.post(f"{CLOUD_SERVER_URL}/ack/{KIOSK_ID}/{job_id}", timeout=5)
                    except:
                        pass
                    continue

                print(f"[DOWNLOAD] {filename}")

                try:
                    file_resp = requests.get(download_url, timeout=30)
                    file_resp.raise_for_status()

                    with open(local_path, "wb") as f:
                        f.write(file_resp.content)

                    print(f"[SAVED] {filename}")

                    # 3️⃣ ACK to cloud (safe delete)
                    ack_resp = requests.post(
                        f"{CLOUD_SERVER_URL}/ack/{KIOSK_ID}/{job_id}",
                        timeout=5
                    )

                    if ack_resp.status_code == 200:
                        print(f"[ACK] Cloud cleaned for job {job_id}")
                    else:
                        print(f"[WARN] ACK failed for {job_id}")

                except Exception as e:
                    print(f"[FAILED] {filename} → {e}")

        except Exception as e:
            print(f"[SYNC ERROR] {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sync_files()
