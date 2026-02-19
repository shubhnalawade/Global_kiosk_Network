"""
kiosk/app.py
============
Kiosk Server — Flask application that runs on the local kiosk machine (port 5001).

Responsibilities:
  - Serve the kiosk UI (kiosk.html)
  - Serve the owner dashboard (owner.html)
  - Generate QR codes pointing to the Cloud Server upload page
  - List, preview, and delete locally synced files
  - Calculate and persist per-job print pricing
  - Handle owner authentication (register, login, update credentials)
  - Provide session status (total cost, readiness to pay)

Files on disk:
  uploads/<kiosk_id>/<job_id>_<filename>        — The print document
  uploads/<kiosk_id>/<job_id>.settings.json     — Chosen print settings
  uploads/<kiosk_id>/<job_id>.price.json        — Computed price
  uploads/<kiosk_id>/<job_id>.meta              — Upload timestamp (from cloud)
"""

print("### KIOSK SERVER STARTED ###")

import os
import json
import math
import socket

import qrcode
from io import BytesIO
from PyPDF2 import PdfReader
from flask import (
    Flask, request, render_template, jsonify, session,
    send_from_directory, send_file, redirect, url_for, make_response
)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Anchor all paths to this file's directory so the server works from any CWD.
_KIOSK_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_BASE  = os.path.join(_KIOSK_DIR, "uploads")
CONFIG_FILE  = os.path.join(_KIOSK_DIR, "kiosk_config.json")

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

# Default pricing (₹ per sheet)
DEFAULT_CONFIG = {
    "owner": None,  # Populated after first registration
    "pricing": {
        "A4_BW":    2,
        "A4_Color": 5,
        "A3_BW":    4,
        "A3_Color": 10,
    }
}


def get_local_ip() -> str:
    """Detect the machine's LAN IP for QR code generation."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


LOCAL_IP         = get_local_ip()
CLOUD_SERVER_URL = f"http://{LOCAL_IP}:5000"  # Cloud Server must be reachable at this address

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Used for Flask session (owner login state)

# =============================================================================
# CONFIG HELPERS
# =============================================================================

def load_config() -> dict:
    """Load kiosk_config.json. Returns a fresh DEFAULT_CONFIG copy on error."""
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Persist the config dictionary to kiosk_config.json."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


# =============================================================================
# KIOSK UI ROUTES
# =============================================================================

@app.route("/")
def redirect_home():
    """Redirect root to the default kiosk screen."""
    return redirect(url_for("kiosk_home", kiosk_id="TB001"))


@app.route("/kiosk/<kiosk_id>")
def kiosk_home(kiosk_id):
    """Render the main kiosk UI for the given kiosk ID."""
    os.makedirs(os.path.join(UPLOAD_BASE, kiosk_id), exist_ok=True)
    return render_template("kiosk.html", kiosk_id=kiosk_id)


@app.route("/owner/dashboard")
def owner_dashboard():
    """Render the owner dashboard (requires login session)."""
    if not session.get("logged_in"):
        return redirect(url_for("redirect_home"))

    config = load_config()
    owner  = config.get("owner")
    if not owner:
        return redirect(url_for("redirect_home"))

    response = make_response(render_template("owner.html", owner=owner))
    # Prevent browser caching of the dashboard page
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"]        = "no-cache"
    response.headers["Expires"]       = "0"
    return response


# =============================================================================
# QR CODE
# =============================================================================

@app.route("/qr/<kiosk_id>")
def qr_code(kiosk_id):
    """Generate a QR code image pointing to the Cloud Server upload page."""
    try:
        url = f"{CLOUD_SERVER_URL}/upload?kiosk_id={kiosk_id}"
        print(f"[QR] Generating QR for: {url}")
        img = qrcode.make(url)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    except Exception as e:
        print(f"[QR] Error: {e}")
        return str(e), 500


# =============================================================================
# LOCAL FILE MANAGEMENT
# =============================================================================

def get_logical_pages(file_path: str) -> int:
    """Return the number of pages in a document. Images always count as 1."""
    if file_path.lower().endswith((".jpg", ".jpeg", ".png")):
        return 1
    try:
        return len(PdfReader(file_path).pages)
    except Exception:
        return 1


@app.route("/fetch/<kiosk_id>")
def fetch_local_files(kiosk_id):
    """
    List documents synced to this kiosk's local upload directory.
    Each entry includes the filename and its saved price (if settings are done).
    """
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    files = []

    if not os.path.exists(kiosk_dir):
        return jsonify(files)

    for f in os.listdir(kiosk_dir):
        full_path = os.path.join(kiosk_dir, f)
        if not os.path.isfile(full_path):
            continue

        ext = f.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue

        # Every valid document file is named <job_id>_<filename>
        if "_" not in f:
            continue
        job_id = f.split("_", 1)[0]

        # Load price if settings have been saved for this job
        price = None
        price_file = os.path.join(kiosk_dir, f"{job_id}.price.json")
        if os.path.exists(price_file):
            with open(price_file) as pf:
                price = json.load(pf).get("price")

        files.append({"name": f, "price": price})

    return jsonify(files)


@app.route("/preview/<kiosk_id>/<filename>")
def preview_file(kiosk_id, filename):
    """Serve a document file for inline preview (PDF or image)."""
    directory = os.path.abspath(os.path.join(UPLOAD_BASE, kiosk_id))
    if not os.path.exists(os.path.join(directory, filename)):
        return "File not found", 404

    response = make_response(send_from_directory(directory, filename))
    if filename.lower().endswith(".pdf"):
        response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "inline"
    return response


@app.route("/delete/<kiosk_id>/<filename>")
def delete_file(kiosk_id, filename):
    """
    Delete a document and all its associated metadata files.
    Deletes: the document, its .meta, .settings.json, and .price.json files.
    """
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    job_id    = filename.split("_")[0]

    targets = [
        filename,
        f"{job_id}.meta",
        f"{job_id}.settings.json",
        f"{job_id}.price.json",
    ]
    for t in targets:
        path = os.path.join(kiosk_dir, t)
        if os.path.exists(path):
            os.remove(path)

    return jsonify({"status": "success", "deleted": targets})


# =============================================================================
# AUTHENTICATION
# =============================================================================

@app.route("/auth/status")
def auth_status():
    """Check whether an owner account has been registered."""
    config = load_config()
    return jsonify({"registered": config.get("owner") is not None})


@app.route("/auth/register", methods=["POST"])
def auth_register():
    """Register the first (and only) owner account for this kiosk."""
    data   = request.json
    config = load_config()

    if config.get("owner"):
        return jsonify({"status": "error", "message": "Owner already registered"}), 403

    # Validate required fields
    for field in ["name", "surname", "mobile", "password"]:
        if not data.get(field):
            return jsonify({"status": "error", "message": f"Missing field: {field}"}), 400

    config["owner"] = {
        "name":     data["name"],
        "surname":  data["surname"],
        "mobile":   data["mobile"],
        "email":    data.get("email", ""),
        "password": data["password"],   # TODO: Hash in production!
    }
    save_config(config)
    return jsonify({"status": "success"})


@app.route("/auth/login", methods=["POST"])
def auth_login():
    """Authenticate the owner using mobile number or email + password."""
    data   = request.json
    config = load_config()
    owner  = config.get("owner")

    if not owner:
        return jsonify({"status": "error", "message": "No owner registered"}), 404

    login_id = data.get("login_id")  # Can be mobile or email
    password = data.get("password")

    mobile_match = login_id == owner["mobile"]
    email_match  = owner.get("email") and login_id == owner["email"]
    if (mobile_match or email_match) and password == owner["password"]:
        session["logged_in"] = True
        return jsonify({"status": "success", "redirect": "/owner/dashboard"})

    return jsonify({"status": "error", "message": "Invalid credentials"}), 401


@app.route("/auth/logout")
def auth_logout():
    """Log the owner out and redirect to the kiosk home."""
    session.pop("logged_in", None)
    return redirect(url_for("redirect_home"))


def _verify_owner_credentials(data: dict, config: dict) -> bool:
    """
    Helper: verify the owner's current mobile + password before credential changes.
    Returns True if credentials match, False otherwise.
    """
    owner = config.get("owner")
    if not owner:
        return False
    return (
        data.get("current_mobile") == owner["mobile"] and
        data.get("password")       == owner["password"]
    )


@app.route("/auth/update/mobile", methods=["POST"])
def auth_update_mobile():
    """Update the owner's mobile number after verifying current credentials."""
    data   = request.json
    config = load_config()

    if not _verify_owner_credentials(data, config):
        return jsonify({"status": "error", "message": "Invalid current mobile or password"}), 403

    new_mobile = data.get("new_mobile")
    if not new_mobile:
        return jsonify({"status": "error", "message": "New mobile number required"}), 400

    config["owner"]["mobile"] = new_mobile
    save_config(config)
    return jsonify({"status": "success", "message": "Mobile updated"})


@app.route("/auth/update/password", methods=["POST"])
def auth_update_password():
    """Update the owner's password after verifying current credentials."""
    data   = request.json
    config = load_config()

    if not _verify_owner_credentials(data, config):
        return jsonify({"status": "error", "message": "Invalid current mobile or password"}), 403

    new_password = data.get("new_password")
    if not new_password:
        return jsonify({"status": "error", "message": "New password required"}), 400

    config["owner"]["password"] = new_password
    save_config(config)
    return jsonify({"status": "success", "message": "Password updated"})


@app.route("/auth/delete", methods=["POST"])
def auth_delete():
    """Permanently delete the owner account after credential verification."""
    data   = request.json
    config = load_config()

    if not _verify_owner_credentials(data, config):
        return jsonify({"status": "error", "message": "Verification failed: invalid credentials"}), 403

    config["owner"] = None
    save_config(config)
    return jsonify({"status": "success", "redirect": "/"})


# =============================================================================
# PRICING API
# =============================================================================

@app.route("/api/pricing", methods=["GET", "POST"])
def api_pricing():
    """
    GET  → Return the current pricing table.
    POST → Merge new pricing values into the config and persist.
    """
    config = load_config()
    if request.method == "POST":
        current = config.get("pricing", DEFAULT_CONFIG["pricing"])
        current.update(request.json)
        config["pricing"] = current
        save_config(config)
        return jsonify({"status": "success", "pricing": current})

    return jsonify(config.get("pricing", DEFAULT_CONFIG["pricing"]))


# =============================================================================
# PRICING CALCULATION  &  SETTINGS
# =============================================================================

def _calculate_price(kiosk_id: str, filename: str, color: str,
                     copies: int, pps: int, paper_size: str) -> int:
    """
    Shared price calculation logic.
    Formula: ceil(total_pages / pps) * copies * rate_per_sheet
    """
    file_path     = os.path.join(UPLOAD_BASE, kiosk_id, filename)
    logical_pages = get_logical_pages(file_path)
    sheets        = math.ceil(logical_pages / pps)

    config  = load_config()
    pricing = config.get("pricing", DEFAULT_CONFIG["pricing"])

    # Key format: "A4_BW" / "A4_Color" / "A3_BW" / "A3_Color"
    mode_suffix = "BW" if color == "bw" else "Color"
    price_key   = f"{paper_size.upper()}_{mode_suffix}"
    rate        = pricing.get(price_key, 2 if color == "bw" else 5)

    return sheets * copies * rate


@app.route("/price", methods=["POST"])
def price_preview():
    """Return a live price estimate for the current print settings."""
    data       = request.json
    total_cost = _calculate_price(
        kiosk_id   = data["kiosk_id"],
        filename   = data["filename"],
        color      = data["color"],
        copies     = int(data["copies"]),
        pps        = int(data["pages_per_sheet"]),
        paper_size = data.get("size", "A4"),
    )
    return jsonify({"total_cost": total_cost})


@app.route("/settings/<kiosk_id>/<filename>", methods=["POST"])
def save_settings(kiosk_id, filename):
    """
    Persist the chosen print settings and computed price for a job.
    Writes:
      <job_id>.settings.json   — Full settings object
      <job_id>.price.json      — {"price": <int>}
    """
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    job_id    = filename.split("_")[0]
    data      = request.json

    price = _calculate_price(
        kiosk_id   = kiosk_id,
        filename   = filename,
        color      = data["color"],
        copies     = int(data["copies"]),
        pps        = int(data["pages_per_sheet"]),
        paper_size = data.get("size", "A4"),
    )

    # Save settings blob
    with open(os.path.join(kiosk_dir, f"{job_id}.settings.json"), "w") as f:
        json.dump(data, f)

    # Save computed price
    with open(os.path.join(kiosk_dir, f"{job_id}.price.json"), "w") as f:
        json.dump({"price": price}, f)

    return jsonify({"price": price})


@app.route("/session/<kiosk_id>")
def session_status(kiosk_id):
    """
    Check if ALL documents in the queue have been configured (settings saved).
    Returns: {"ready": True, "total": <sum_of_prices>}
          or {"ready": False}
    """
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    if not os.path.exists(kiosk_dir):
        return jsonify({"ready": False})

    # Collect unique job IDs from document files
    job_ids = set()
    for f in os.listdir(kiosk_dir):
        if "_" in f and not f.endswith(".meta") and not f.endswith(".json"):
            job_ids.add(f.split("_")[0])

    # Every job must have a price file; if any is missing → not ready
    total = 0
    for jid in job_ids:
        price_file = os.path.join(kiosk_dir, f"{jid}.price.json")
        if not os.path.exists(price_file):
            return jsonify({"ready": False})
        with open(price_file) as f:
            total += json.load(f)["price"]

    return jsonify({"ready": True, "total": total})


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Kiosk server runs on port 5001 to avoid conflict with Cloud Server on 5000
    app.run(host="0.0.0.0", port=5001)
