# Kiosk 2 Setup - Multi-Kiosk Configuration

## Overview
The Global Kiosk Network now supports **two independent kiosk machines** (TB001 and TB002) with a shared cloud server. Each kiosk has:
- Its own UI interface on different ports (5001 and 5002)
- Separate file storage directories
- Independent sync service that polls the cloud server for files specific to that kiosk
- Own owner configuration and pricing settings

## Architecture

### Services Running

```
Port 5000 - Cloud Server (Shared)
├─ Receives uploads from mobile users with kiosk_id parameter
├─ Routes files to cloud_uploads/<kiosk_id>/
├─ Provides /fetch, /download, /ack endpoints for sync services
└─ Single instance handles all kiosks

Port 5001 - Kiosk 1 Server (TB001)
├─ Kiosk UI for machine 1
├─ Uses uploads/TB001/ for local file storage
└─ Runs on localhost:5001

Port 5002 - Kiosk 2 Server (TB002)
├─ Kiosk UI for machine 2
├─ Uses uploads/TB002/ for local file storage
└─ Runs on localhost:5002

Background - Kiosk 1 Sync Service
├─ KIOSK_ID = "TB001"
├─ Polls cloud_server at /fetch/TB001
├─ Downloads files to uploads/TB001/
└─ Acknowledges with /ack/TB001/<job_id>

Background - Kiosk 2 Sync Service
├─ KIOSK_ID = "TB002"
├─ Polls cloud_server at /fetch/TB002
├─ Downloads files to uploads/TB002/
└─ Acknowledges with /ack/TB002/<job_id>
```

## Directory Structure

```
Global_Kiosk_Network/
├── cloud_server/
│   ├── app.py                      # Shared cloud server
│   └── cloud_uploads/
│       ├── TB001/                  # Files uploaded for kiosk 1
│       └── TB002/                  # Files uploaded for kiosk 2
│
├── kiosk/                          # Kiosk 1 (TB001)
│   ├── app.py                      # Port 5001, TB001 as default
│   ├── kiosk_sync.py               # KIOSK_ID = "TB001"
│   ├── kiosk_config.json
│   ├── uploads/
│   │   └── TB001/                  # Local files for kiosk 1
│   ├── templates/
│   └── static/
│
├── kiosk2/                         # Kiosk 2 (TB002) - NEW
│   ├── app.py                      # Port 5002, TB002 as default
│   ├── kiosk_sync.py               # KIOSK_ID = "TB002"
│   ├── kiosk_config.json
│   ├── uploads/
│   │   └── TB002/                  # Local files for kiosk 2
│   ├── templates/
│   └── static/
│
├── uploads/
│   ├── TB001/                      # Backup/reference directory
│   └── TB002/                      # Backup/reference directory
│
└── run_system.py                   # Updated to launch both kiosks
```

## File Flow - How It Works

### Scenario 1: Upload via Kiosk 1 QR Code
```
1. User scans QR code on Kiosk 1 (TB001)
   └─ QR URL: http://localhost:5000/upload?kiosk_id=TB001

2. Mobile user uploads file to Cloud Server
   └─ File saved to cloud_uploads/TB001/<job_id>_<filename>

3. Kiosk 1 Sync Service (running continuously)
   └─ Polls GET /fetch/TB001
   └─ Receives list of pending files
   └─ Downloads to uploads/TB001/

4. Kiosk 1 UI displays the file
   └─ Owner can set print settings, calculate price, etc.

5. After processing, Sync Service sends ACK
   └─ POST /ack/TB001/<job_id>
   └─ Cloud Server deletes cloud_uploads/TB001/<job_id>_*
```

### Scenario 2: Upload via Kiosk 2 QR Code
```
1. User scans QR code on Kiosk 2 (TB002)
   └─ QR URL: http://localhost:5000/upload?kiosk_id=TB002

2. Mobile user uploads file to Cloud Server
   └─ File saved to cloud_uploads/TB002/<job_id>_<filename>

3. Kiosk 2 Sync Service (running continuously)
   └─ Polls GET /fetch/TB002 (NOT TB001!)
   └─ Only retrieves files for TB002
   └─ Downloads to uploads/TB002/

4. Kiosk 2 UI displays the file
   └─ Owner settings are independent of Kiosk 1

5. Kiosk 1 Sync Service ignores TB002 files
   └─ Because it only polls /fetch/TB001
```

## Key Modifications Made

### 1. **kiosk2/app.py**
   - Changed port from 5001 to 5002
   - Changed default redirect from TB001 to TB002
   - All other functionality identical to kiosk/app.py

### 2. **kiosk2/kiosk_sync.py**
   - Changed KIOSK_ID from "TB001" to "TB002"
   - Creates and uses uploads/TB002/ directory
   - Syncs only from cloud_uploads/TB002/

### 3. **kiosk2/kiosk_config.json**
   - Independent owner credentials
   - Independent pricing configuration
   - Initially same as kiosk1, but can be modified per kiosk

### 4. **run_system.py**
   - Added "Kiosk 2 Server" service (port 5002)
   - Added "Kiosk 2 Sync Service" background service
   - Updated status banner to show both kiosks
   - All services launched simultaneously

### 5. **Directory Structure**
   - Created `cloud_uploads/TB002/` for cloud files
   - Created `uploads/TB002/` for local sync
   - Deleted copied TB001 files from kiosk2

## How to Use

### Start the System
```bash
python run_system.py
```

This will launch:
- Cloud Server on port 5000
- Kiosk 1 UI on port 5001
- Kiosk 1 Sync Service (background)
- Kiosk 2 UI on port 5002
- Kiosk 2 Sync Service (background)

### Access Kiosk 1
- UI: http://localhost:5001
- Kiosk Page: http://localhost:5001/kiosk/TB001
- Mobile Upload: http://localhost:5000/upload?kiosk_id=TB001

### Access Kiosk 2
- UI: http://localhost:5002
- Kiosk Page: http://localhost:5002/kiosk/TB002
- Mobile Upload: http://localhost:5000/upload?kiosk_id=TB002

### Generate QR Codes
- Kiosk 1 QR: Visit http://localhost:5001/qr/TB001
- Kiosk 2 QR: Visit http://localhost:5002/qr/TB002

## File Separation Logic

The cloud server uses the `kiosk_id` parameter to ensure files are routed correctly:

```python
# kiosk_id comes from upload URL or sync fetch request
kiosk_dir = os.path.join(UPLOAD_BASE, kiosk_id)
# Results in: cloud_uploads/TB001/ or cloud_uploads/TB002/
```

Each sync service ONLY polls its own kiosk_id:

```python
# Kiosk 1 Sync: KIOSK_ID = "TB001"
response = requests.get(f"{CLOUD_SERVER_URL}/fetch/TB001")

# Kiosk 2 Sync: KIOSK_ID = "TB002"
response = requests.get(f"{CLOUD_SERVER_URL}/fetch/TB002")
```

This ensures **files uploaded from Kiosk 1 QR never appear on Kiosk 2 queue** and vice versa.

## Future Extensions

To add more kiosks (TB003, TB004, etc.):

1. Copy `kiosk2/` folder to `kiosk3/`
2. Modify `kiosk3/app.py`:
   - Change redirect_home() to use "TB003"
   - Change port to 5003
3. Modify `kiosk3/kiosk_sync.py`:
   - Change KIOSK_ID = "TB003"
4. Create directories:
   - `uploads/TB003/`
   - `cloud_uploads/TB003/`
5. Update `run_system.py` to add Kiosk 3 services
6. Each kiosk remains independent but shares same cloud server

## Cloud Server API Reference

All endpoints remain the same, just parametrized by kiosk_id:

```
GET  /upload?kiosk_id=<id>                      # Upload page (with QR kiosk_id)
POST /upload?kiosk_id=<id>                      # Accept file upload
GET  /fetch/<kiosk_id>                          # List pending files for kiosk
GET  /download/<kiosk_id>/<filename>            # Download specific file
POST /ack/<kiosk_id>/<job_id>                   # Acknowledge file received
```

## Troubleshooting

### Files not syncing to Kiosk 2
- Check that mobile upload URL includes `?kiosk_id=TB002`
- Verify Kiosk 2 Sync Service is running
- Check `kiosk2/sync_debug.log`

### Same files appearing on both kiosks
- Verify each kiosk is polling its correct endpoint
- Check KIOSK_ID in kiosk2/kiosk_sync.py is "TB002"
- Check cloud server isn't mixing directories

### Port conflicts
- Ensure port 5001 and 5002 are available
- Update port numbers in app.py if needed

## Testing Workflow

```
1. Start system: python run_system.py
2. Visit Kiosk 1: http://localhost:5001/kiosk/TB001
3. Get Kiosk 1 QR: http://localhost:5001/qr/TB001
4. Scan QR on mobile → upload file
5. File appears in Kiosk 1 queue
6. Visit Kiosk 2: http://localhost:5002/kiosk/TB002
7. Get Kiosk 2 QR: http://localhost:5002/qr/TB002
8. Scan different QR on mobile → upload different file
9. File 1 appears only on Kiosk 1
10. File 2 appears only on Kiosk 2
11. Both kiosks can manage independently ✓
```

---

**Status**: ✅ Multi-kiosk system successfully configured and ready for testing!
