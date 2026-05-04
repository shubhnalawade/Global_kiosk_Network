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
import shutil
import subprocess
from datetime import datetime

import qrcode
from io import BytesIO
try:
    from pypdf import PdfReader, PdfWriter, Transformation
    _PDF_LIB = "pypdf"
except Exception:
    try:
        from PyPDF2 import PdfReader, PdfWriter, Transformation
        _PDF_LIB = "PyPDF2"
    except Exception:
        from PyPDF2 import PdfReader, PdfWriter
        Transformation = None
        _PDF_LIB = "PyPDF2"
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
    },
    "printer": {
        "name": "",
        "backend": "sumatra" if os.name == "nt" else "cups",
        "sumatra_path": "",
    },
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


LOCAL_IP = get_local_ip()
# Allow override if auto-detected IP is unreachable from phones.
CLOUD_SERVER_URL = os.getenv("CLOUD_SERVER_URL", f"http://{LOCAL_IP}:5000")

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


def _get_printer_config(config: dict) -> dict:
    printer = config.get("printer") or {}
    if "name" not in printer:
        printer["name"] = ""
    if "backend" not in printer:
        printer["backend"] = "sumatra" if os.name == "nt" else "cups"
    if "sumatra_path" not in printer:
        printer["sumatra_path"] = ""
    return printer


def _list_printers() -> list:
    if os.name == "nt":
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True,
            text=True,
        )
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return ["Save as PDF"] + names

    result = subprocess.run(
        ["bash", "-lc", "lpstat -p | awk '{print $2}'"],
        capture_output=True,
        text=True,
    )
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return ["Save as PDF"] + names


def _resolve_sumatra_path(printer_cfg: dict) -> str:
    override = (printer_cfg.get("sumatra_path") or "").strip()
    if override and os.path.exists(override):
        return override

    for candidate in [
        shutil.which("SumatraPDF.exe"),
        shutil.which("SumatraPDF"),
        r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
        r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    ]:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def _normalize_paper(value: str) -> str:
    if not value:
        return ""
    key = value.strip().lower()
    mapping = {
        "a4": "A4",
        "a3": "A3",
        "letter": "Letter",
        "legal": "Legal",
    }
    return mapping.get(key, "")


def _paper_size_points(paper_key: str) -> tuple:
    """Return (width, height) in PDF points for common paper sizes."""
    key = (paper_key or "").strip().lower()
    sizes = {
        "a4": (595.28, 841.89),
        "a3": (841.89, 1190.55),
        "letter": (612.0, 792.0),
        "legal": (612.0, 1008.0),
    }
    return sizes.get(key, sizes["a4"])


def _get_margin_points(margins: str) -> float:
    margin_key = (margins or "").strip().lower()
    if margin_key == "none":
        return 0.0
    if margin_key == "min":
        return 10.0
    return 20.0


def _get_nup_grid(pages_per_sheet: int, layout: str) -> tuple:
    layout_key = (layout or "portrait").strip().lower()
    if pages_per_sheet <= 1:
        return (1, 1)
    if pages_per_sheet == 2:
        return (2, 1) if layout_key == "landscape" else (1, 2)
    if pages_per_sheet == 4:
        return (2, 2)
    if pages_per_sheet == 6:
        return (3, 2) if layout_key == "landscape" else (2, 3)
    if pages_per_sheet >= 9:
        return (3, 3) if pages_per_sheet < 16 else (4, 4)
    return (1, 1)


def _compose_nup_pdf(input_path: str, settings: dict, output_path: str) -> None:
    reader = PdfReader(input_path)
    total_pages = len(reader.pages)
    if total_pages == 0:
        raise RuntimeError("No pages to print")

    pages_range = _parse_pages_range(settings.get("pages"), total_pages)
    if not pages_range:
        pages_range = list(range(1, total_pages + 1))

    try:
        pages_per_sheet = int(settings.get("pages_per_sheet") or 1)
    except Exception:
        pages_per_sheet = 1

    if pages_per_sheet < 1:
        pages_per_sheet = 1

    layout = settings.get("layout") or "portrait"
    sheet_w, sheet_h = _paper_size_points(settings.get("size"))
    if str(layout).strip().lower() == "landscape":
        sheet_w, sheet_h = sheet_h, sheet_w

    cols, rows = _get_nup_grid(pages_per_sheet, layout)
    cell_w = sheet_w / cols
    cell_h = sheet_h / rows
    margin = _get_margin_points(settings.get("margins"))

    scale_mode = settings.get("scale")
    scale_factor = 1.0
    if scale_mode == "custom":
        try:
            scale_factor = float(settings.get("customScale") or 100) / 100.0
        except Exception:
            scale_factor = 1.0

    writer = PdfWriter()
    for chunk_start in range(0, len(pages_range), pages_per_sheet):
        sheet = writer.add_blank_page(width=sheet_w, height=sheet_h)
        chunk = pages_range[chunk_start:chunk_start + pages_per_sheet]

        for idx, page_num in enumerate(chunk):
            src_page = reader.pages[page_num - 1]
            src_w = float(src_page.mediabox.width)
            src_h = float(src_page.mediabox.height)

            col = idx % cols
            row = idx // cols
            row = min(row, rows - 1)

            usable_w = max(cell_w - (2 * margin), 1)
            usable_h = max(cell_h - (2 * margin), 1)
            base_scale = min(usable_w / src_w, usable_h / src_h)
            scale = max(base_scale * scale_factor, 0.01)

            draw_w = src_w * scale
            draw_h = src_h * scale

            offset_x = col * cell_w + margin + (usable_w - draw_w) / 2
            offset_y = sheet_h - ((row + 1) * cell_h) + margin + (usable_h - draw_h) / 2

            _merge_page_onto_sheet(sheet, src_page, scale, offset_x, offset_y)

    with open(output_path, "wb") as out_file:
        writer.write(out_file)


def _merge_page_onto_sheet(sheet, src_page, scale: float, offset_x: float, offset_y: float) -> None:
    if hasattr(sheet, "merge_transformed_page") and Transformation is not None:
        transform = Transformation().scale(scale).translate(offset_x, offset_y)
        sheet.merge_transformed_page(src_page, transform)
        return

    if hasattr(sheet, "merge_scaled_translated_page"):
        sheet.merge_scaled_translated_page(src_page, scale, offset_x, offset_y)
        return

    try:
        if hasattr(src_page, "copy"):
            page = src_page.copy()
        else:
            import copy
            page = copy.copy(src_page)

        if Transformation is not None and hasattr(page, "add_transformation"):
            page.add_transformation(Transformation().scale(scale).translate(offset_x, offset_y))
        else:
            if hasattr(page, "scale"):
                page.scale(scale)
            if hasattr(page, "translate"):
                page.translate(offset_x, offset_y)

        if hasattr(sheet, "merge_page"):
            sheet.merge_page(page)
        else:
            sheet.mergePage(page)
    except Exception as exc:
        raise RuntimeError(f"N-up merge failed: {exc}")


def _apply_copies_to_pdf(input_path: str, copies: int, output_path: str) -> None:
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for _ in range(max(1, copies)):
        for page in reader.pages:
            writer.add_page(page)
    with open(output_path, "wb") as out_file:
        writer.write(out_file)


def _load_job_settings(kiosk_dir: str, job_id: str) -> dict:
    path = os.path.join(kiosk_dir, f"{job_id}.settings.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _parse_pages_range(pages_range, max_pages: int) -> list:
    """Parse a page range string like "1-3, 5" into a sorted 1-based list."""
    if max_pages <= 0:
        return []
    if not pages_range:
        return []

    pages_range = str(pages_range).strip().lower()
    if not pages_range or pages_range == "all":
        return []

    selected = set()
    try:
        for part in pages_range.split(","):
            token = part.strip()
            if not token:
                continue
            if "-" in token:
                a_str, b_str = token.split("-", 1)
                a = int(a_str.strip())
                b = int(b_str.strip())
                start = max(1, min(a, b))
                end = min(max_pages, max(a, b))
                if start > end:
                    continue
                for page in range(start, end + 1):
                    selected.add(page)
            else:
                page = int(token)
                if 1 <= page <= max_pages:
                    selected.add(page)
    except Exception:
        return []

    return sorted(selected)


def _build_sumatra_settings(settings: dict) -> str:
    tokens = []

    pages = (settings.get("pages") or "").strip().lower()
    if pages and pages != "all":
        tokens.append(pages)

    copies = int(settings.get("copies") or 1)
    if copies > 1:
        tokens.append(f"copies={copies}")

    sides = settings.get("sides")
    if sides == "two-sided-long-edge":
        tokens.append("duplex")
    elif sides == "two-sided-short-edge":
        tokens.append("duplexshort")

    paper = _normalize_paper(settings.get("size"))
    if paper:
        tokens.append(f"paper={paper}")

    layout = settings.get("layout")
    if layout == "landscape":
        tokens.append("landscape")

    pps = settings.get("pages_per_sheet")
    try:
        pps_val = int(pps)
    except Exception:
        pps_val = 1

    nup_map = {
        1: None,
        2: "2x1" if layout == "landscape" else "1x2",
        4: "2x2",
        6: "3x2" if layout == "landscape" else "2x3",
        9: "3x3",
        16: "4x4",
    }
    nup = nup_map.get(pps_val)
    if nup:
        tokens.append(f"nup={nup}")

    scale = settings.get("scale")
    if scale == "custom":
        custom_scale = str(settings.get("customScale") or "").strip()
        if custom_scale:
            tokens.append(f"scale={custom_scale}")

    return ",".join(tokens)


def _build_cups_args(settings: dict) -> list:
    args = []

    copies = int(settings.get("copies") or 1)
    if copies > 1:
        args.extend(["-n", str(copies)])

    sides = settings.get("sides")
    if sides == "two-sided-long-edge":
        args.extend(["-o", "sides=two-sided-long-edge"])
    elif sides == "two-sided-short-edge":
        args.extend(["-o", "sides=two-sided-short-edge"])

    pages = (settings.get("pages") or "").strip().lower()
    if pages and pages != "all":
        args.extend(["-o", f"page-ranges={pages}"])

    paper = _normalize_paper(settings.get("size"))
    if paper:
        args.extend(["-o", f"media={paper}"])

    layout = settings.get("layout")
    if layout == "landscape":
        args.extend(["-o", "orientation-requested=4"])

    scale = settings.get("scale")
    if scale == "custom":
        custom_scale = str(settings.get("customScale") or "").strip()
        if custom_scale:
            args.extend(["-o", f"scaling={custom_scale}"])

    pps = settings.get("pages_per_sheet")
    if pps and str(pps).isdigit():
        args.extend(["-o", f"number-up={pps}"])

    return args


# =============================================================================
# KIOSK UI ROUTES
# =============================================================================

@app.route("/")
def index():
    """Landing page with links to both Kiosk and Upload pages."""
    return render_template("index.html")


@app.route("/home")
def redirect_home():
    """Redirect to the default kiosk screen."""
    return redirect(url_for("kiosk_home", kiosk_id="TB001"))


@app.route("/kiosk/<kiosk_id>")
def kiosk_home(kiosk_id):
    """Render the main kiosk UI for the given kiosk ID."""
    os.makedirs(os.path.join(UPLOAD_BASE, kiosk_id), exist_ok=True)
    upload_url = f"{CLOUD_SERVER_URL}/upload?kiosk_id={kiosk_id}"
    return render_template("kiosk.html", kiosk_id=kiosk_id, upload_url=upload_url)


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


@app.route("/api/printers")
def api_printers():
    config = load_config()
    printer_cfg = _get_printer_config(config)
    printers = _list_printers()
    return jsonify({
        "printers": printers,
        "selected": printer_cfg.get("name", ""),
        "backend": printer_cfg.get("backend", ""),
        "sumatra_path": printer_cfg.get("sumatra_path", ""),
    })


@app.route("/api/printer", methods=["GET", "POST"])
def api_printer():
    config = load_config()
    printer_cfg = _get_printer_config(config)

    if request.method == "GET":
        return jsonify(printer_cfg)

    data = request.json or {}
    name = (data.get("name") or "").strip()
    sumatra_path = (data.get("sumatra_path") or "").strip()

    printer_cfg["name"] = name
    if sumatra_path:
        printer_cfg["sumatra_path"] = sumatra_path

    config["printer"] = printer_cfg
    save_config(config)
    return jsonify({"status": "success", "printer": printer_cfg})


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


def _count_pages_from_range(pages_range, max_pages: int) -> int:
    """Count unique pages from a human-friendly range string like "1-5, 8".

    Returns max_pages for empty/"all" input, and falls back to max_pages on
    invalid input.
    """
    if max_pages <= 0:
        return 1
    if not pages_range:
        return max_pages

    pages_range = str(pages_range).strip().lower()
    if not pages_range or pages_range == "all":
        return max_pages

    selected = set()
    try:
        for part in pages_range.split(","):
            token = part.strip()
            if not token:
                continue

            if "-" in token:
                a_str, b_str = token.split("-", 1)
                a = int(a_str.strip())
                b = int(b_str.strip())
                start = min(a, b)
                end = max(a, b)
                start = max(1, start)
                end = min(max_pages, end)
                if start > end:
                    continue
                for page in range(start, end + 1):
                    selected.add(page)
            else:
                page = int(token)
                if 1 <= page <= max_pages:
                    selected.add(page)
    except Exception:
        return max_pages

    return len(selected) if selected else max_pages


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

def _calculate_price(
    kiosk_id: str,
    filename: str,
    color: str,
    copies: int,
    pps: int,
    paper_size: str,
    pages=None,
) -> int:
    """
    Shared price calculation logic.
    Formula: ceil(total_pages / pps) * copies * rate_per_sheet
    """
    file_path     = os.path.join(UPLOAD_BASE, kiosk_id, filename)
    max_pages = get_logical_pages(file_path)
    logical_pages = _count_pages_from_range(pages, max_pages)
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
        pages      = data.get("pages"),
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
        pages      = data.get("pages"),
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
        if "_" not in f:
            continue
        if f.endswith(".meta") or f.endswith(".json"):
            continue
        ext = f.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
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


@app.route("/print/<kiosk_id>", methods=["POST"])
def print_jobs(kiosk_id):
    """
    Send a print command for ready jobs.
    Optionally accepts {"files": ["<job>_<name>", ...]} to limit the list.
    """
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    if not os.path.exists(kiosk_dir):
        return jsonify({"status": "error", "message": "Kiosk not found"}), 404

    config = load_config()
    printer_cfg = _get_printer_config(config)

    data = request.json or {}
    requested_files = data.get("files")
    if requested_files is not None and not isinstance(requested_files, list):
        return jsonify({"status": "error", "message": "Invalid files list"}), 400

    if requested_files:
        candidates = requested_files
    else:
        candidates = os.listdir(kiosk_dir)

    printable = []
    for name in candidates:
        if not name or "/" in name or "\\" in name:
            continue
        if "_" not in name or name.endswith(".meta") or name.endswith(".json"):
            continue
        ext = name.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        path = os.path.join(kiosk_dir, name)
        if os.path.isfile(path):
            printable.append((name, path))

    if not printable:
        return jsonify({"status": "error", "message": "No printable files"}), 400

    # Ensure all jobs have pricing saved before printing
    job_ids = {name.split("_")[0] for name, _ in printable}
    for jid in job_ids:
        price_file = os.path.join(kiosk_dir, f"{jid}.price.json")
        if not os.path.exists(price_file):
            return jsonify({"status": "error", "message": "Session not ready"}), 400

    printer_name = (printer_cfg.get("name") or "").strip()
    if not printer_name:
        return jsonify({"status": "error", "message": "No printer configured"}), 400

    def _job_timestamp(job_id: str, file_path: str) -> float:
        meta_path = os.path.join(kiosk_dir, f"{job_id}.meta")
        if os.path.exists(meta_path):
            return os.path.getmtime(meta_path)
        return os.path.getmtime(file_path)

    printable.sort(key=lambda item: _job_timestamp(item[0].split("_")[0], item[1]))

    backend = printer_cfg.get("backend") or ("sumatra" if os.name == "nt" else "cups")
    sumatra_path = _resolve_sumatra_path(printer_cfg) if backend == "sumatra" else ""

    log_path = os.path.join(kiosk_dir, "print_debug.log")
    work_dir = os.path.join(kiosk_dir, "print_work")
    os.makedirs(work_dir, exist_ok=True)
    printed = []
    failed = []
    for name, path in printable:
        job_id = name.split("_")[0]
        settings = _load_job_settings(kiosk_dir, job_id)
        stamp = datetime.now().isoformat(timespec="seconds")

        try:
            if printer_name.lower() == "save as pdf":
                output_dir = os.path.join(kiosk_dir, "print_outputs")
                os.makedirs(output_dir, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base_name = f"{job_id}_print_{timestamp}.pdf"
                temp_path = os.path.join(work_dir, f"{job_id}_nup_{timestamp}.pdf")

                _compose_nup_pdf(path, settings, temp_path)

                copies = int(settings.get("copies") or 1)
                if copies > 1:
                    out_path = os.path.join(output_dir, base_name)
                    _apply_copies_to_pdf(temp_path, copies, out_path)
                else:
                    out_path = os.path.join(output_dir, base_name)
                    os.replace(temp_path, out_path)

                with open(log_path, "a") as log_file:
                    log_file.write(f"{stamp} SAVE PDF: {out_path}\n")
                printed.append(name)
                continue

            if backend == "sumatra":
                if not sumatra_path:
                    raise RuntimeError("SumatraPDF not found. Set its path in the admin panel.")
                print_path = path
                settings_for_print = dict(settings or {})
                try:
                    pages_per_sheet = int(settings.get("pages_per_sheet") or 1)
                except Exception:
                    pages_per_sheet = 1
                if pages_per_sheet > 1:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    print_path = os.path.join(work_dir, f"{job_id}_nup_{timestamp}.pdf")
                    _compose_nup_pdf(path, settings, print_path)
                    # Avoid double-nup/rotation; composed PDF already matches layout.
                    settings_for_print.pop("pages_per_sheet", None)
                    settings_for_print.pop("layout", None)
                    settings_for_print.pop("pages", None)

                settings_arg = _build_sumatra_settings(settings_for_print)
                cmd = [
                    sumatra_path,
                    "-silent",
                    "-exit-on-print",
                    "-print-to", printer_name,
                ]
                if settings_arg:
                    cmd.extend(["-print-settings", settings_arg])
                cmd.append(print_path)
                with open(log_path, "a") as log_file:
                    log_file.write(f"{stamp} SUMATRA CMD: {cmd}\n")
                    log_file.write(f"{stamp} SETTINGS: {settings_for_print}\n")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.stdout or result.stderr:
                    with open(log_path, "a") as log_file:
                        if result.stdout:
                            log_file.write(f"{stamp} SUMATRA OUT: {result.stdout}\n")
                        if result.stderr:
                            log_file.write(f"{stamp} SUMATRA ERR: {result.stderr}\n")
                with open(log_path, "a") as log_file:
                    log_file.write(f"{stamp} SUMATRA RC: {result.returncode}\n")
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "SumatraPDF print failed")
            else:
                cmd = ["lp", "-d", printer_name]
                settings_for_print = dict(settings or {})
                try:
                    pages_per_sheet = int(settings.get("pages_per_sheet") or 1)
                except Exception:
                    pages_per_sheet = 1
                if pages_per_sheet > 1:
                    settings_for_print.pop("pages_per_sheet", None)
                    settings_for_print.pop("layout", None)
                    settings_for_print.pop("pages", None)
                cmd.extend(_build_cups_args(settings_for_print))
                cmd.append(path)
                with open(log_path, "a") as log_file:
                    log_file.write(f"{stamp} CUPS CMD: {cmd}\n")
                    log_file.write(f"{stamp} SETTINGS: {settings_for_print}\n")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.stdout or result.stderr:
                    with open(log_path, "a") as log_file:
                        if result.stdout:
                            log_file.write(f"{stamp} CUPS OUT: {result.stdout}\n")
                        if result.stderr:
                            log_file.write(f"{stamp} CUPS ERR: {result.stderr}\n")
                with open(log_path, "a") as log_file:
                    log_file.write(f"{stamp} CUPS RC: {result.returncode}\n")
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "CUPS print failed")

            printed.append(name)
        except Exception as exc:
            failed.append({"file": name, "error": str(exc)})

    status = "success" if printed and not failed else "partial" if printed else "error"
    message = None
    if failed:
        message = failed[0].get("error") or "Print failed"
    return jsonify({"status": status, "printed": printed, "failed": failed, "message": message})


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Kiosk server runs on port 5001 to avoid conflict with Cloud Server on 5000
    app.run(host="0.0.0.0", port=5001)
