import requests
import time
import os

CLOUD_URL = "http://127.0.0.1:5000"
KIOSK_URL = "http://127.0.0.1:5001"
KIOSK_ID = "TB001"

def test_cloud_server():
    try:
        r = requests.get(CLOUD_URL)
        if r.status_code == 200:
            print("[PASS] Cloud Server is online.")
            return True
        else:
            print(f"[FAIL] Cloud Server returned {r.status_code}")
    except Exception as e:
        print(f"[FAIL] Cloud Server unreachable: {e}")
    return False

def test_kiosk_app():
    try:
        r = requests.get(KIOSK_URL + "/") # Redirects
        if r.status_code < 400: # 302 or 200
            print("[PASS] Kiosk App is online.")
            return True
        else:
            print(f"[FAIL] Kiosk App returned {r.status_code}")
    except Exception as e:
        print(f"[FAIL] Kiosk App unreachable: {e}")
    return False

def test_upload_sync():
    print("Testing Upload -> Sync -> Kiosk...")
    test_filename = "test_verification.txt"
    with open(test_filename, "w") as f:
        f.write("Verification content")
    
    # Needs to be a valid extension: pdf, png, jpg, jpeg
    test_filename_mock = "test_verification.pdf" 
    # We will rename specifically for the upload to trick the allowed_file check if we want,
    # or just make a real dummy pdf.
    # Actually code allows txt? No, ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
    
    # Create a dummy PDF content
    with open(test_filename_mock, "wb") as f:
        f.write(b"%PDF-1.4 header dummy")

    files = {'files': (test_filename_mock, open(test_filename_mock, 'rb'), 'application/pdf')}
    
    try:
        r = requests.post(f"{CLOUD_URL}/upload?kiosk_id={KIOSK_ID}", files=files)
        if r.status_code == 200:
            print("[PASS] Upload to Cloud Server successful.")
        else:
            print(f"[FAIL] Upload failed: {r.status_code} {r.text}")
            return False
            
        print("Waiting 6 seconds for sync...")
        time.sleep(6)
        
        # Check Kiosk Local Files
        r_kiosk = requests.get(f"{KIOSK_URL}/fetch/{KIOSK_ID}")
        data = r_kiosk.json()
        
        found = False
        for file in data:
            if "test_verification.pdf" in file["name"]:
                found = True
                print(f"[PASS] File found in Kiosk: {file['name']}")
                break
        
        if not found:
            print("[FAIL] File NOT found in Kiosk after sync wait.")
            print(f"Kiosk File List: {data}")
            return False
            
        return True

    except Exception as e:
        print(f"[FAIL] Error during upload/sync test: {e}")
        return False
    finally:
        if os.path.exists(test_filename): os.remove(test_filename)
        if os.path.exists(test_filename_mock): os.remove(test_filename_mock)

if __name__ == "__main__":
    c = test_cloud_server()
    k = test_kiosk_app()
    if c and k:
        test_upload_sync()
