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

from flask import Flask, request, render_template, jsonify, send_from_directory
from werkzeug.utils import secure_filename

# =============================================================================
# CONFIGURATION
# =============================================================================

app = Flask(__name__)

_CLOUD_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_BASE  = os.path.join(_CLOUD_DIR, "cloud_uploads")

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
# UPLOAD (MOBILE USER)
# =============================================================================

@app.route("/upload", methods=["GET", "POST"])
def upload():
    """
    GET  → Render the upload form (kiosk_id passed as query param).
    POST → Save uploaded files to cloud_uploads/<kiosk_id>/.
    """
    kiosk_id = request.args.get("kiosk_id")
    if not kiosk_id:
        return "Missing kiosk_id parameter.", 400

    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    os.makedirs(kiosk_dir, exist_ok=True)

    if request.method == "POST":
        files = request.files.getlist("files")
        if not files:
            return "No files received.", 400

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
                file.save(os.path.join(kiosk_dir, f"{job_id}_{filename}"))

                # Write a timestamp meta file so the kiosk can track upload time
                with open(os.path.join(kiosk_dir, f"{job_id}.meta"), "w") as mf:
                    mf.write(str(time.time()))

            except Exception as e:
                print(f"[UPLOAD] Failed to save file: {e}")
                return f"Server error: {e}", 500

        return "Upload successful. Please go to the kiosk."

    return render_template("upload.html")


# =============================================================================
# FILE LISTING (KIOSK SYNC)
# =============================================================================

@app.route("/fetch/<kiosk_id>")
def fetch_files(kiosk_id):
    """
    Return a JSON list of files pending download for a given kiosk.
    Excludes .meta files and any entries without an underscore (not a real job).
    """
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    files = []

    if not os.path.exists(kiosk_dir):
        return jsonify(files)

    for f in os.listdir(kiosk_dir):
        if f.endswith(".meta") or "_" not in f:
            continue
        if not os.path.isfile(os.path.join(kiosk_dir, f)):
            continue

        job_id = f.split("_", 1)[0]
        files.append({
            "job_id":   job_id,
            "filename": f,
            "url":      f"/download/{kiosk_id}/{f}",
        })

    return jsonify(files)


# =============================================================================
# FILE DOWNLOAD (KIOSK SYNC)
# =============================================================================

@app.route("/download/<kiosk_id>/<filename>")
def download_file(kiosk_id, filename):
    """Serve a stored file for the Kiosk Sync Service to download."""
    return send_from_directory(os.path.join(UPLOAD_BASE, kiosk_id), filename)


# =============================================================================
# ACKNOWLEDGE DOWNLOAD (KIOSK → CLOUD CLEANUP)
# =============================================================================

@app.route("/ack/<kiosk_id>/<job_id>", methods=["POST"])
def acknowledge_download(kiosk_id, job_id):
    """
    Called by the Kiosk Sync Service after a successful file download.
    Deletes all files for this job_id from the cloud so they aren't re-synced.
    """
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    if not os.path.exists(kiosk_dir):
        return jsonify({"status": "kiosk_not_found"}), 404

    deleted = []
    for f in os.listdir(kiosk_dir):
        if f.startswith(job_id):
            os.remove(os.path.join(kiosk_dir, f))
            deleted.append(f)

    return jsonify({"status": "acknowledged", "deleted_files": deleted})


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
