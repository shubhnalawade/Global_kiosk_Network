print("### KIOSK SERVER STARTED ###")

from flask import (
    Flask, request, render_template, jsonify, session,
    send_from_directory, send_file, redirect, url_for, make_response
)
import os, json, qrcode, math
from io import BytesIO
from PyPDF2 import PdfReader

# ---------------- CONFIG ----------------
UPLOAD_BASE = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
# Point to Cloud Server for valid QR code generation
CLOUD_SERVER_URL = "http://192.168.1.8:5000" 

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Required for session management if we used sessions (using simple logic for now)

# ---------------- CONFIG & STORAGE ----------------
CONFIG_FILE = "kiosk_config.json"

DEFAULT_CONFIG = {
    "owner": None,  # {name, surname, mobile, password, email}
    "pricing": {
        "A4_BW": 2,
        "A4_Color": 5,
        "A3_BW": 5,
        "A3_Color": 10
    }
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

# ---------------- ROOT (Kiosk UI) ----------------
@app.route("/")
def redirect_home():
    # Default to a specific kiosk ID or a selection screen
    # For now, default to TB001
    return redirect(url_for("kiosk_home", kiosk_id="TB001"))

@app.route("/kiosk/<kiosk_id>")
def kiosk_home(kiosk_id):
    os.makedirs(os.path.join(UPLOAD_BASE, kiosk_id), exist_ok=True)
    return render_template("kiosk.html", kiosk_id=kiosk_id)

@app.route("/owner/dashboard")
def owner_dashboard():
    # Verify session
    if not session.get("logged_in"):
        return redirect(url_for("redirect_home"))

    config = load_config()
    owner = config.get("owner")
    if not owner:
        return redirect(url_for("redirect_home")) 
    
    # Render with no-cache headers
    response = make_response(render_template("owner.html", owner=owner))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/auth/logout")
def auth_logout():
    session.pop("logged_in", None)
    return redirect(url_for("redirect_home"))


# ---------------- QR CODE (Points to Cloud) ----------------
@app.route("/qr/<kiosk_id>")
def qr_code(kiosk_id):
    # Generate QR pointing to the GLOBAL Cloud Server upload page
    url = f"{CLOUD_SERVER_URL}/upload?kiosk_id={kiosk_id}"
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# ---------------- LOCAL FILE MANAGEMENT ----------------
def get_logical_pages(file_path):
    if file_path.lower().endswith((".jpg", ".jpeg", ".png")):
        return 1
    try:
        reader = PdfReader(file_path)
        return len(reader.pages)
    except:
        return 1

@app.route("/fetch/<kiosk_id>")
def fetch_local_files(kiosk_id):
    # This fetches files from LOCAL disk (synced by kiosk_sync.py)
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
            
        if "_" not in f:
            continue
        job_id = f.split("_", 1)[0]

        price_file = os.path.join(kiosk_dir, f"{job_id}.price.json")
        price = None
        if os.path.exists(price_file):
            with open(price_file) as pf:
                price = json.load(pf).get("price")

        files.append({
            "name": f,
            "price": price
        })

    return jsonify(files)

@app.route("/preview/<kiosk_id>/<filename>")
def preview_file(kiosk_id, filename):
    directory = os.path.abspath(os.path.join(UPLOAD_BASE, kiosk_id))
    if not os.path.exists(os.path.join(directory, filename)):
        return "File not found", 404
        
    response = make_response(
        send_from_directory(directory, filename)
    )
    if filename.lower().endswith('.pdf'):
        response.headers["Content-Type"] = "application/pdf"
    
    response.headers["Content-Disposition"] = "inline"
    return response


@app.route("/delete/<kiosk_id>/<filename>")
def delete_file(kiosk_id, filename):
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    job_id = filename.split("_")[0]
    
    # We delete locally. 
    # NOTE: In a full sync system, we might want to tell the cloud to delete too,
    # or the sync script might re-download it. 
    # For now, we assume local delete is sufficient for the user session.
    
    targets = [filename, f"{job_id}.meta", f"{job_id}.settings.json", f"{job_id}.price.json"]
    for t in targets:
        path = os.path.join(kiosk_dir, t)
        if os.path.exists(path):
            os.remove(path)
            
    return jsonify({"status": "success", "deleted": targets})

    return jsonify({"status": "success", "deleted": targets})

# ---------------- AUTH & REGISTRATION ----------------
@app.route("/auth/status")
def auth_status():
    config = load_config()
    return jsonify({"registered": config.get("owner") is not None})

@app.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.json
    config = load_config()
    
    if config.get("owner"):
        return jsonify({"status": "error", "message": "Owner already registered"}), 403
        
    # Basic validation
    required = ["name", "surname", "mobile", "password"]
    for field in required:
        if not data.get(field):
            return jsonify({"status": "error", "message": f"Missing {field}"}), 400
            
    config["owner"] = {
        "name": data["name"],
        "surname": data["surname"],
        "mobile": data["mobile"],
        "email": data.get("email", ""),
        "password": data["password"] # In production, HASH THIS!
    }
    save_config(config)
    return jsonify({"status": "success"})

@app.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.json
    config = load_config()
    owner = config.get("owner")
    
    if not owner:
        return jsonify({"status": "error", "message": "No owner registered"}), 404
        
    # Check credentials
    # Allow login via Mobile or Email
    login_id = data.get("login_id") # Email or Mobile
    password = data.get("password")
    
    if (login_id == owner["mobile"] or (owner["email"] and login_id == owner["email"])) and password == owner["password"]:
        session["logged_in"] = True
        return jsonify({"status": "success", "redirect": "/owner/dashboard"})
        
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

def verify_creds(data, config):
    owner = config.get("owner")
    if not owner: return False
    
    # Must provide CURRENT mobile and password
    mobile = data.get("current_mobile")
    password = data.get("password") # Verification password
    
    if mobile == owner["mobile"] and password == owner["password"]:
        return True
    return False

@app.route("/auth/update/mobile", methods=["POST"])
def auth_update_mobile():
    data = request.json
    config = load_config()
    
    if not verify_creds(data, config):
        return jsonify({"status": "error", "message": "Invalid Current Mobile or Password"}), 403
        
    new_mobile = data.get("new_mobile")
    if not new_mobile:
        return jsonify({"status": "error", "message": "New Mobile required"}), 400
        
    config["owner"]["mobile"] = new_mobile
    save_config(config)
    return jsonify({"status": "success", "message": "Mobile Updated"})

@app.route("/auth/update/password", methods=["POST"])
def auth_update_password():
    data = request.json
    config = load_config()
    
    if not verify_creds(data, config):
        return jsonify({"status": "error", "message": "Invalid Current Mobile or Password"}), 403
        
    new_password = data.get("new_password")
    if not new_password:
        return jsonify({"status": "error", "message": "New Password required"}), 400
        
    config["owner"]["password"] = new_password
    save_config(config)
    return jsonify({"status": "success", "message": "Password Updated"})

@app.route("/auth/delete", methods=["POST"])
def auth_delete():
    data = request.json
    config = load_config()
    
    if not verify_creds(data, config):
        return jsonify({"status": "error", "message": "Verification Failed: Invalid Credentials"}), 403
        
    config["owner"] = None
    save_config(config)
    return jsonify({"status": "success", "redirect": "/"})


# ---------------- PRICING API ----------------
@app.route("/api/pricing", methods=["GET", "POST"])
def api_pricing():
    config = load_config()
    if request.method == "POST":
        new_pricing = request.json
        # Merge/Overwrite existing pricing keys
        current_pricing = config.get("pricing", DEFAULT_CONFIG["pricing"])
        current_pricing.update(new_pricing)
        config["pricing"] = current_pricing
        save_config(config)
        return jsonify({"status": "success", "pricing": current_pricing})
        
    return jsonify(config.get("pricing", DEFAULT_CONFIG["pricing"]))

# ---------------- PRICING CALCULATION ----------------
@app.route("/price", methods=["POST"])
def price_preview():
    data = request.json
    kiosk_id = data["kiosk_id"]
    filename = data["filename"]
    color = data["color"] # "bw" or "color"
    copies = int(data["copies"])
    pps = int(data["pages_per_sheet"])
    # New: Paper Size
    paper_size = data.get("size", "A4") # Default A4

    file_path = os.path.join(UPLOAD_BASE, kiosk_id, filename)
    logical_pages = get_logical_pages(file_path)
    sheets = math.ceil(logical_pages / pps)
    
    # Dynamic Rate Calculation
    config = load_config()
    pricing = config.get("pricing", DEFAULT_CONFIG["pricing"])
    
    # Construct key: e.g. "A4_BW", "A3_Color"
    # Ensure keys match config format
    mode_suffix = "BW" if color == "bw" else "Color"
    price_key = f"{paper_size}_{mode_suffix}"
    
    # Fallback if key missing, though it shouldn't be
    rate = pricing.get(price_key, 2 if color == "bw" else 5)
    
    total_cost = sheets * copies * rate

    return jsonify({"total_cost": total_cost})

@app.route("/settings/<kiosk_id>/<filename>", methods=["POST"])
def save_settings(kiosk_id, filename):
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    job_id = filename.split("_")[0]
    data = request.json
    
    # Calculate price again to be safe
    color = data["color"]
    copies = int(data["copies"])
    pps = int(data["pages_per_sheet"])
    paper_size = data.get("size", "A4")
    
    file_path = os.path.join(kiosk_dir, filename)
    logical_pages = get_logical_pages(file_path)
    sheets = math.ceil(logical_pages / pps)
    
    # Config-based Rate
    config = load_config()
    pricing = config.get("pricing", DEFAULT_CONFIG["pricing"])
    mode_suffix = "BW" if color == "bw" else "Color"
    price_key = f"{paper_size}_{mode_suffix}"
    rate = pricing.get(price_key, 2)
    
    price = sheets * copies * rate

    with open(os.path.join(kiosk_dir, f"{job_id}.settings.json"), "w") as f:
        json.dump(data, f)
    with open(os.path.join(kiosk_dir, f"{job_id}.price.json"), "w") as f:
        json.dump({"price": price}, f)

    return jsonify({"price": price})

@app.route("/session/<kiosk_id>")
def session_status(kiosk_id):
    kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
    total = 0
    if not os.path.exists(kiosk_dir):
        return jsonify({"ready": False})

    # Only count jobs that have a price (settings saved)
    job_ids = set()
    for f in os.listdir(kiosk_dir):
        if "_" in f and not f.endswith(".meta") and not f.endswith(".json"):
             job_ids.add(f.split("_")[0])

    for jid in job_ids:
        price_file = os.path.join(kiosk_dir, f"{jid}.price.json")
        if not os.path.exists(price_file):
            return jsonify({"ready": False})
        with open(price_file) as f:
            total += json.load(f)["price"]

    return jsonify({"ready": True, "total": total})

if __name__ == "__main__":
    # Kiosk runs on port 5001 to avoid conflict with cloud server on same machine
    app.run(host="0.0.0.0", port=5001)
