import requests
import json

CLOUD_SERVER_URL = "http://127.0.0.1:5000"
KIOSK_ID = "TB001"

def test_sync():
    print(f"Testing connectivity to {CLOUD_SERVER_URL}...")
    try:
        resp = requests.get(CLOUD_SERVER_URL)
        print(f"Root Check: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Root Check Failed: {e}")
        return

    print(f"\nFetching files for {KIOSK_ID}...")
    try:
        resp = requests.get(f"{CLOUD_SERVER_URL}/fetch/{KIOSK_ID}")
        print(f"Fetch Status: {resp.status_code}")
        if resp.status_code == 200:
            files = resp.json()
            print(f"Files Found: {len(files)}")
            # Test Download first file
            if files:
                f0 = files[0]
                url = CLOUD_SERVER_URL + f0['url']
                print(f"Testing Download: {url}")
                dresp = requests.get(url)
                print(f"Download Status: {dresp.status_code}")
                if dresp.status_code == 200:
                    print(f"Download Size: {len(dresp.content)} bytes")
                else:
                    print(f"Download Failed: {dresp.text}")
        else:
            print(f"Fetch Failed: {resp.text}")
    except Exception as e:
        print(f"Fetch Error: {e}")

if __name__ == "__main__":
    test_sync()
