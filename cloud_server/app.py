"""
cloud_server/app.py
====================
Cloud Server — Flask application that acts as the public-facing upload relay
for the Global Kiosk Network (runs on port 5000).

Responsibilities:
  - Serve the mobile-optimised upload page (upload.html)
  - Accept file uploads from mobile users and store them per-kiosk
  - Allow the Kiosk Sync Service to list, download, and acknowledge files

File lifecycle:
  1. Mobile user uploads → files saved to cloud_uploads/<kiosk_id>/
  2. Kiosk Sync polls /fetch/<kiosk_id> → learns about pending files
  3. Kiosk Sync downloads /download/<kiosk_id>/<filename>
  4. Kiosk Sync posts /ack/<kiosk_id>/<job_id> → cloud removes the file

File format on cloud:
  cloud_uploads/<kiosk_id>/<job_id>_<original_filename>  — the document
  cloud_uploads/<kiosk_id>/<job_id>.meta                 — upload timestamp
"""

print("### CLOUD SERVER STARTED ###")

import os
import uuid
import time
import json
from io import BytesIO

from flask import Flask, request, render_template, jsonify, send_file
from werkzeug.utils import secure_filename


# =============================================================================
# CONFIGURATION
# =============================================================================

app = Flask(__name__)

_CLOUD_DIR = os.path.dirname(os.path.abspath(__file__))

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

# 50 MB max upload size
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


def allowed_file(filename: str) -> bool:
    """Return True if the file extension is in the allowed set."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# =============================================================================
# STATUS
# =============================================================================

@app.route("/")
def home():
    """Simple health-check endpoint."""
    return "CLOUD SERVER ONLINE"


# =============================================================================

# LOCAL STORAGE CONFIGURATION
LOCAL_UPLOAD_BASE = os.path.join(_CLOUD_DIR, "cloud_uploads")


# =============================================================================
# UPLOAD (MOBILE USER)
# =============================================================================

@app.route("/upload", methods=["GET", "POST"])
def upload():
    """
    GET  → Render the upload form (kiosk_id passed as query param).
    POST → Save uploaded files to local storage.
    """
    kiosk_id = request.args.get("kiosk_id")
    if not kiosk_id:
        return "Missing kiosk_id parameter.", 400


    if request.method == "POST":
        files = request.files.getlist("files")
        if not files:
            return "No files received.", 400

        kiosk_dir = os.path.join(LOCAL_UPLOAD_BASE, kiosk_id)
        os.makedirs(kiosk_dir, exist_ok=True)

        for file in files:
            if not file.filename or not allowed_file(file.filename):
                continue  # Skip empty or disallowed files

            job_id   = str(uuid.uuid4())
            filename = secure_filename(file.filename)

            # Guard against Windows MAX_PATH issues with long filenames
            if len(filename) > 50:
                stem, ext = os.path.splitext(filename)
                filename  = stem[:50] + ext

            try:
                # Save file locally
                file_path = os.path.join(kiosk_dir, f"{job_id}_{filename}")
                file.save(file_path)

                # Write a timestamp meta file locally
                meta_path = os.path.join(kiosk_dir, f"{job_id}.meta")
                with open(meta_path, "w") as meta_file:
                    meta_file.write(str(time.time()))

            except Exception as e:
                print(f"[UPLOAD] Failed to save file: {e}")
                return f"Server error: {e}", 500

        return "Upload successful. Please go to the kiosk."

    return render_template("upload.html", kiosk_id=kiosk_id)


# =============================================================================
# FILE LISTING (KIOSK SYNC)
# =============================================================================

@app.route("/fetch/<kiosk_id>")
def fetch_files(kiosk_id):
    """
    Return a JSON list of files pending download for a given kiosk.
    Excludes .meta files and any entries without an underscore (not a real job).
    """
    try:
        kiosk_dir = os.path.join(LOCAL_UPLOAD_BASE, kiosk_id)
        files = []
        if not os.path.exists(kiosk_dir):
            return jsonify(files)

        for fname in os.listdir(kiosk_dir):
            if fname.endswith(".meta") or "_" not in fname:
                continue
            job_id = fname.split("_", 1)[0]
            files.append({
                "job_id": job_id,
                "filename": fname,
                "url": f"/download/{kiosk_id}/{fname}"
            })
        return jsonify(files)
    except Exception as e:
        print(f"[FETCH] Failed to list files: {e}")
        return jsonify([]), 500


# =============================================================================
# FILE DOWNLOAD (KIOSK SYNC)
# =============================================================================

@app.route("/download/<kiosk_id>/<filename>")
def download_file(kiosk_id, filename):
    """Serve a stored file for the Kiosk Sync Service to download."""
    try:
        kiosk_dir = os.path.join(LOCAL_UPLOAD_BASE, kiosk_id)
        file_path = os.path.join(kiosk_dir, filename)
        if not os.path.exists(file_path):
            return "File not found.", 404
        return send_file(
            file_path,
            download_name=filename,
            as_attachment=True,
        )
    except Exception as e:
        print(f"[DOWNLOAD] Failed to download file: {e}")
        return "File not found.", 404


# =============================================================================
# ACKNOWLEDGE DOWNLOAD (KIOSK → CLOUD CLEANUP)
# =============================================================================

@app.route("/ack/<kiosk_id>/<job_id>", methods=["POST"])
def acknowledge_download(kiosk_id, job_id):
    """
    Called by the Kiosk Sync Service after a successful file download.
    Deletes all files for this job_id from the cloud so they aren't re-synced.
    """
    try:
        kiosk_dir = os.path.join(LOCAL_UPLOAD_BASE, kiosk_id)
        deleted = []
        for fname in os.listdir(kiosk_dir):
            if fname.startswith(job_id):
                fpath = os.path.join(kiosk_dir, fname)
                try:
                    os.remove(fpath)
                    deleted.append(fname)
                except Exception as e:
                    print(f"[ACK] Failed to delete {fname}: {e}")
        return jsonify({"status": "acknowledged", "deleted_files": deleted})
    except Exception as e:
        print(f"[ACK] Failed to delete files: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


# =============================================================================
# KIOSK AGENT API
# =============================================================================

# Store kiosks in memory (in production, use a database)
_kiosks = {}

@app.route("/api/kiosks/register", methods=["POST"])
def register_kiosk():
    """
    Register a new kiosk device.
    POST body:
    {
        "name": "Kiosk-01",
        "location": "Main Lobby",
        "ip_address": "192.168.1.50",
        "version": "1.0.0",
        "metadata": { ... }
    }
    Returns:
    { "id": "<kiosk_id>" }
    """
    data = request.get_json()
    kiosk_id = str(uuid.uuid4())[:8].upper()
    
    _kiosks[kiosk_id] = {
        "id": kiosk_id,
        "name": data.get("name", "Unknown"),
        "location": data.get("location", "Unknown"),
        "ip_address": data.get("ip_address", "0.0.0.0"),
        "version": data.get("version", "1.0.0"),
        "metadata": data.get("metadata", {}),
        "registered_at": time.time(),
        "last_heartbeat": None,
        "metrics": {},
    }
    
    print(f"[REGISTER] Kiosk {kiosk_id} registered: {data.get('name')} at {data.get('location')}")
    return jsonify({"id": kiosk_id}), 201


@app.route("/api/kiosks/<kiosk_id>/heartbeat", methods=["POST"])
def kiosk_heartbeat(kiosk_id):
    """
    Receive heartbeat and metrics from a kiosk agent.
    POST body:
    {
        "cpu": 25.5,
        "memory": 60.2,
        "disk": 45.8,
        "uptime": 830635
    }
    Returns:
    { "commands": [ ... ] }
    """
    if kiosk_id not in _kiosks:
        return jsonify({"error": "Kiosk not found"}), 404
    
    data = request.get_json()
    _kiosks[kiosk_id]["last_heartbeat"] = time.time()
    _kiosks[kiosk_id]["metrics"] = data
    
    # Return any pending commands (empty for now)
    commands = []
    
    return jsonify({"commands": commands}), 200


@app.route("/api/kiosks/<kiosk_id>/command/<cmd_id>/ack", methods=["PATCH"])
def acknowledge_command(kiosk_id, cmd_id):
    """
    Acknowledge command execution from kiosk agent.
    """
    if kiosk_id not in _kiosks:
        return jsonify({"error": "Kiosk not found"}), 404
    
    data = request.get_json()
    status = data.get("status", "executed")
    
    print(f"[COMMAND ACK] Kiosk {kiosk_id} - Command {cmd_id}: {status}")
    return jsonify({"status": "acknowledged"}), 200


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
