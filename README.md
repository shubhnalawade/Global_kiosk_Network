# Global Kiosk Network - Print Management System

## 📋 System Overview

A modern, distributed printing vending machine system with:
- **Kiosk Page** (Port 5001): Main interface for print job queue management
- **Upload Page** (Port 5000): Mobile-friendly document upload interface
- **Sync Service**: Automatic file synchronization between cloud and local kiosk
- **Authentication**: Owner login/registration with dashboard
- **Real-time Pricing**: Dynamic cost calculation based on print settings

---

## 🔄 Complete Workflow

### 1. **User Scans QR Code** (From Kiosk Page)
   - Opens mobile upload page on their phone
   - Automatically connects to the same network as kiosk

### 2. **Upload Documents**
   - Mobile user selects PDF/Image files
   - Uploads to cloud server at `http://localhost:5000/upload?kiosk_id=TB001`
   - Files stored temporarily in `cloud_uploads/TB001/`

### 3. **Automatic Sync**
   - Kiosk Sync Service polls cloud server every 3 seconds
   - Downloads new files to `kiosk/uploads/TB001/`
   - Files appear instantly in queue on Kiosk Page

### 4. **Queue Management**
   - Documents appear on right panel of Kiosk Page
   - Each file shows status: "Needs Setup" (no price) or "₹XX" (setup complete)
   - User can select multiple files for batch operations

### 5. **Configure Each Document**
   - Click on document to open print settings modal
   - **Preview Panel** (Left 60%):
     - Full PDF preview with continuous scroll
     - Zoom in/out, rotate, fit to width/page
     - All pages visible with N-up layout preview
   
   - **Settings Panel** (Right 40%):
     - **Color**: Black & White or Color
     - **Copies**: 1-999
     - **Pages**: All or Custom range (e.g., "1-5, 8, 10-12")
     - **Layout**: Portrait or Landscape
     - **Paper Size**: A4, A3, Letter, Legal
     - **Pages Per Sheet**: 1, 2, 4, 6, 9, 16
     - **Advanced**: Margins, scale, duplex, headers/footers
   
   - **Price Calculation** (Footer):
     - Real-time calculation as you change settings
     - Formula: `(total_pages ÷ pages_per_sheet) × copies × rate_per_sheet`
     - Shows total sheets and final cost

### 6. **Repeat for All Documents**
   - Click "Done" to save settings after configuring each document
   - Price automatically saved to `kiosk/uploads/TB001/<job_id>.price.json`
   - Modal closes and returns to queue

### 7. **Total Cost Calculation**
   - Once ALL documents have settings saved:
     - Total cost appears at bottom-left: "Total Estimated Cost: ₹XXX"
     - "Proceed to Payment" button activates
     - Button changes from gray (disabled) to purple gradient (enabled)

### 8. **Payment & Print**
   - Click "Proceed to Payment"
   - System ready to process payment and print jobs

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Flask, PyPDF2, qrcode (installed via requirements)
- Windows/Linux/Mac

### 1. Setup Virtual Environment
```bash
# Navigate to project directory
cd Global_Kiosk_Network

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\Activate.ps1
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the System
```bash
# Make sure you're in the project root with venv activated
python run_system.py
```

This will:
- Start Cloud Server (Port 5000)
- Start Kiosk Server (Port 5001)
- Start Sync Service
- Display access URLs

### 3. Access the System
Open your browser:
- **Control Center**: http://localhost:5001
- **Kiosk Page**: http://localhost:5001/kiosk/TB001
- **Upload Page**: http://localhost:5000/upload?kiosk_id=TB001

---

## 📁 Project Structure

```
Global_Kiosk_Network/
├── cloud_server/
│   ├── app.py                  # Cloud server (port 5000)
│   ├── cloud_uploads/          # Uploaded files (temp storage)
│   │   └── TB001/             # Kiosk-specific uploads
│   └── templates/
│       └── upload.html        # Mobile upload interface
│
├── kiosk/
│   ├── app.py                 # Kiosk server (port 5001)
│   ├── kiosk_sync.py          # Sync service (polls cloud)
│   ├── kiosk_config.json      # Configuration & pricing
│   ├── uploads/               # Local synced files
│   │   └── TB001/            # Kiosk-specific files
│   └── templates/
│       ├── index.html         # Landing page with links
│       ├── kiosk.html         # Main kiosk interface
│       └── owner.html         # Owner dashboard
│
├── run_system.py              # Main launcher (starts all services)
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

---

## 🔧 Configuration

### Pricing (kiosk/kiosk_config.json)
```json
{
  "owner": null,
  "pricing": {
    "A4_BW": 2,        // ₹2 per sheet (A4 Black & White)
    "A4_Color": 5,     // ₹5 per sheet (A4 Color)
    "A3_BW": 4,        // ₹4 per sheet (A3 Black & White)
    "A3_Color": 10     // ₹10 per sheet (A3 Color)
  }
}
```

### Kiosk ID
Default: `TB001` - Change in URLs if using different kiosk ID

---

## 🔐 Authentication

### Owner Registration
1. Click "Login" button in top-right of Kiosk Page
2. Click "New User? Register"
3. Enter:
   - Name & Surname
   - Mobile Number (required)
   - Email (optional)
   - Password (min 6 chars: uppercase, lowercase, symbol)
4. Click "Register Owner"

### Owner Login
- **Mobile Number** (for login):  Use phone number from registration
- **Password**: Use registered password
- Access **Owner Dashboard** to view statistics and manage settings

### Owner Dashboard
Once logged in, access:
- Pricing management
- Account settings
- Print job history
- Kiosk statistics

---

## 📱 Device Files

Each document creates multiple files during the workflow:

```
kiosk/uploads/TB001/
├── <uuid>_document.pdf              # Uploaded document
├── <uuid>.meta                      # Upload timestamp
├── <uuid>.settings.json             # User's print settings (saved after "Done")
└── <uuid>.price.json               # Calculated price (saved after "Done")
```

**Deletion**: When user deletes a document, all related files are removed

---

## 🔄 Payment Flow

Currently, the system achieves:
✅ All documents configured with print settings
✅ Real-time price calculation
✅ Total cost aggregation
✅ Payment button activation

**Next Steps** (Not yet implemented):
- Payment gateway integration
- Print job submission
- Print status tracking

---

## 🎨 UI Features

### Kiosk Page
- **Dark/Light Theme Toggle**: Top-right switch
- **QR Code Display**: Left panel for mobile access
- **Document Queue**: Right panel with file cards
- **Selection**: Checkbox to select multiple files
- **Bulk Delete**: Delete selected files at once
- **Price Animation**: Green pulse when price updates
- **Responsive**: Works on desktop and tablets

### Upload Page
- **Mobile Optimized**: Vertical layout for phones
- **Drag & Drop**: Drop files or click to browse
- **Real-time Upload**: Shows progress
- **Multiple Files**: Upload multiple documents at once
- **Confirmation**: Success message after upload

### Print Settings Modal
- **Two-Panel Layout**:
  - Left: Live PDF preview with controls
  - Right: Settings & price calculation
- **Continuous Scroll**: See all pages at once
- **Preview Controls**:
  - Zoom: -, +, Fit to Page, Fit to Width
  - Rotate: 90° increments
  - Modern glass-morphism UI
- **Settings Collapse**: More options expandable

---

## 🐛 Troubleshooting

### Services Not Starting
```bash
# Check if ports are available
netstat -ano | findstr :5000   # Windows
netstat -ano | findstr :5001   # Windows
lsof -i :5000                  # Linux/Mac
```

### Files Not Syncing
- Check `kiosk_sync.py` console output
- Verify `cloud_uploads/TB001/` has files
- Check network connectivity between services

### Preview Not Loading
- Ensure PDF.js CDN is accessible
- Check browser console for errors
- Verify PDF file is valid

### Price Calculation Wrong
- Check pricing in `kiosk_config.json`
- Verify paper size and color selection
- Recalculate manually: `(pages ÷ pages_per_sheet) × copies × rate`

---

## 📊 API Endpoints

### Kiosk Server (5001)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Landing page with links |
| GET | `/kiosk/<kiosk_id>` | Main kiosk interface |
| GET | `/qr/<kiosk_id>` | Generate QR code |
| GET | `/fetch/<kiosk_id>` | List documents in queue |
| POST | `/settings/<kiosk_id>/<filename>` | Save print settings |
| POST | `/price` | Calculate quick price |
| GET | `/session/<kiosk_id>` | Check if ready for payment |
| POST | `/auth/register` | Register owner |
| POST | `/auth/login` | Owner login |

### Cloud Server (5000)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Health check |
| GET/POST | `/upload` | Upload documents |
| GET | `/fetch/<kiosk_id>` | List pending files |
| GET | `/download/<kiosk_id>/<filename>` | Download file |
| POST | `/ack/<kiosk_id>/<job_id>` | Acknowledge download |

---

## 📝 Notes

- All prices in Indian Rupees (₹)
- PDF.js renders PDFs in browser (no server-side processing needed)
- Settings and prices persist in JSON files
- No database required (file-based storage)
- Beginner-friendly with modern UI/UX

---

## 🎯 Future Enhancements

- [ ] Payment gateway integration (Razorpay/Stripe)
- [ ] Print job queue management
- [ ] Email receipt generation
- [ ] Admin dashboard
- [ ] SQLite/PostgreSQL database
- [ ] Docker containerization
- [ ] Mobile app native implementation
- [ ] Multi-language support
- [ ] Analytics dashboard
- [ ] Printer hardware integration

---

## 📞 Support

For issues or questions:
1. Check troubleshooting section
2. Review console output from services
3. Check browser developer console (F12)
4. Review file system permissions

---

**Version**: 1.0.0  
**Last Updated**: February 2025  
**License**: MIT

