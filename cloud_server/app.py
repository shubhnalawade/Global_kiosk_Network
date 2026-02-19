print("### CLOUD SERVER STARTED ###")

from flask import Flask, request, render_template, jsonify, send_from_directory
import os
import uuid
import time
from werkzeug.utils import secure_filename

# ---------------- APP INIT ----------------
app = Flask(__name__)

# ---------------- CONFIG ----------------
_CLOUD_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_BASE = os.path.join(_CLOUD_DIR, "cloud_uploads")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------- ROOT ----------------
@app.route("/")
def home():
    return "CLOUD SERVER ONLINE"


# ---------------- UPLOAD (MOBILE USER) ----------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    kiosk_id = request.args.get("kiosk_id")
    if not kiosk_id:
        return "Invalid kiosk ID", 400

    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    os.makedirs(kiosk_dir, exist_ok=True)

    if request.method == "POST":
        files = request.files.getlist("files")
        if not files:
            return "No files uploaded", 400

        for file in files:
            if file.filename == "":
                continue
            if not allowed_file(file.filename):
                continue

            job_id = str(uuid.uuid4())
            filename = secure_filename(file.filename)
            
            # Truncate filename to prevent Windows path length issues
            if len(filename) > 50:
                name_part, ext_part = os.path.splitext(filename)
                filename = name_part[:50] + ext_part

            try:
                save_path = os.path.join(kiosk_dir, f"{job_id}_{filename}")
                file.save(save_path)

                # Meta file (timestamp)
                with open(os.path.join(kiosk_dir, f"{job_id}.meta"), "w") as f:
                    f.write(str(time.time()))
            except Exception as e:
                print(f"FAILED TO SAVE FILE: {e}")
                return f"Server Error: {str(e)}", 500

        return "Upload successful. Please go to kiosk."

    return render_template("upload.html")


# ---------------- FETCH FILES (KIOSK SYNC) ----------------
@app.route("/fetch/<kiosk_id>")
def fetch_files(kiosk_id):
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    files = []

    if not os.path.exists(kiosk_dir):
        return jsonify(files)

    for f in os.listdir(kiosk_dir):
        if f.endswith(".meta"):
            continue

        full_path = os.path.join(kiosk_dir, f)
        if not os.path.isfile(full_path):
            continue

        if "_" not in f:
            continue

        job_id = f.split("_", 1)[0]

        files.append({
            "job_id": job_id,
            "filename": f,
            "url": f"/download/{kiosk_id}/{f}"
        })

    return jsonify(files)


# ---------------- DOWNLOAD FILE (KIOSK SYNC) ----------------
@app.route("/download/<kiosk_id>/<filename>")
def download_file(kiosk_id, filename):
    return send_from_directory(os.path.join(UPLOAD_BASE, kiosk_id), filename)


# ---------------- ACK DOWNLOAD (KIOSK → CLOUD) ----------------
@app.route("/ack/<kiosk_id>/<job_id>", methods=["POST"])
def acknowledge_download(kiosk_id, job_id):
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)

    if not os.path.exists(kiosk_dir):
        return jsonify({"status": "kiosk_not_found"}), 404

    deleted = []

    for f in os.listdir(kiosk_dir):
        if f.startswith(job_id):
            os.remove(os.path.join(kiosk_dir, f))
            deleted.append(f)

    return jsonify({
        "status": "acknowledged",
        "deleted_files": deleted
    })


# ---------------- MAIN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
