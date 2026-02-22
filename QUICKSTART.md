# 🚀 QUICK START GUIDE

## ⚡ 30 Second Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the System
```bash
python run_system.py
```

### 3. Open in Browser
- **Control Center**: http://localhost:5001
- **Direct Kiosk**: http://localhost:5001/kiosk/TB001
- **Mobile Upload**: http://localhost:5000/upload?kiosk_id=TB001

---

## 📝 COMPLETE SYSTEM ANALYSIS

### Architecture: 3-Tier Distributed System

**Port 5000 - Cloud Server**
- Receives PDFs from mobile users
- Temporary storage for uploads
- File listing API for sync service
- Lightweight, stateless

**Port 5001 - Kiosk Server**
- Main UI with document queue
- Print settings configuration
- Real-time price calculation
- Receipt & payment interface

**Background - Sync Service**
- Polls cloud every 3 seconds
- Downloads files to local kiosk
- Maintains file consistency

---

## 🔄 COMPLETE WORKFLOW EXPLANATION

### Full User Journey (Step by Step)

**1. UPLOAD PHASE** 
- User at kiosk sees QR code on left panel
- Scans with phone → Opens upload page
- Selects PDFs on phone → Uploads to cloud server
- Cloud stores: `cloud_uploads/TB001/<job_id>_filename.pdf`

**2. SYNC PHASE**
- Kiosk Sync Service detects new files (polls every 3s)
- Downloads to local: `kiosk/uploads/TB001/`
- Acknowledges to cloud → Cloud auto-deletes
- Documents instantly appear in kiosk queue

**3. QUEUE PHASE**
- Right panel shows all uploaded documents
- Each file shows status: "Needs Setup" or "₹XX" (if configured)
- User can select/delete files
- Button disabled until ALL files configured

**4. CONFIGURATION PHASE**
- Click document to open print settings modal
- **Left side (65%)**: Live PDF preview
  - Zoom, rotate, fit-to-page controls
  - All pages visible in continuous scroll
- **Right side (35%)**: Settings & price
  - Color: Black & White (₹2-4/sheet) or Color (₹5-10/sheet)
  - Copies: 1-999
  - Pages: All or custom range
  - Layout: Portrait or Landscape
  - Paper Size: A4/A3/Letter/Legal
  - Pages Per Sheet: 1/2/4/6/9/16
  - **Price updates in real-time** as you change settings

**5. SETTINGS SAVE PHASE**
- Click "Done" to confirm settings for that document
- Settings saved: `<job_id>.settings.json`
- Price saved: `<job_id>.price.json`
- Status changes from "Needs Setup" → "₹XX"
- Modal closes, returns to queue

**6. REPEAT FOR ALL DOCUMENTS**
- Open next document
- Adjust settings (or keep defaults)
- Click "Done"
- Repeat until all documents have prices

**7. FINAL APPROVAL PHASE**
- System checks: Do ALL documents have prices?
- GET `/session/TB001` endpoint returns:
  ```json
  {
    "ready": true,
    "total": 130
  }
  ```
- **Button ACTIVATES**: "Proceed to Payment" → "Pay & Print"
- Total cost displays: ₹130 (sum of all document prices)

**8. PAYMENT PHASE** (Future Integration)
- User clicks "Pay & Print"
- Payment gateway processes
- Print jobs submitted to printer
- Status tracking begins

---

## 💰 PRICE CALCULATION LOGIC

### Formula
```
Total Cost = ceil(total_pages ÷ pages_per_sheet) × copies × price_per_sheet
```

### Example Calculations

| Document | Pages | Color | Paper | PPS | Copies | Calculation | Cost |
|----------|-------|-------|-------|-----|--------|-------------|------|
| Doc 1 | 10 | B&W | A4 | 1 | 1 | (10÷1) × 1 × ₹2 | ₹20 |
| Doc 2 | 5 | B&W | A4 | 1 | 1 | (5÷1) × 1 × ₹2 | ₹10 |
| Doc 3 | 15 | Color | A3 | 2 | 1 | (15÷2) × 1 × ₹10 | ₹100 |
| **TOTAL** | - | - | - | - | - | - | **₹130** |

### Pricing Table
```
A4 - Black & White:  ₹2 per sheet
A4 - Color:          ₹5 per sheet
A3 - Black & White:  ₹4 per sheet
A3 - Color:          ₹10 per sheet
```

---

## 📁 FILE STORAGE STRUCTURE

### Cloud (Temporary)
```
cloud_uploads/
└── TB001/
    ├── a1b2c3d4_Document1.pdf     (Uploaded PDF)
    ├── a1b2c3d4.meta              (Timestamp)
    ├── e5f6g7h8_Document2.pdf
    ├── e5f6g7h8.meta
    └── ... (deleted after sync)
```

### Local Kiosk (Persistent)
```
kiosk/uploads/
└── TB001/
    ├── a1b2c3d4_Document1.pdf                  (The PDF file)
    ├── a1b2c3d4.meta                          (Upload time)
    ├── a1b2c3d4.settings.json                 (User choices)
    │   └─ {"color": "bw", "copies": 1, ...}
    ├── a1b2c3d4.price.json                    (Calculated cost)
    │   └─ {"price": 20}
    ├── e5f6g7h8_Document2.pdf
    ├── e5f6g7h8.meta
    ├── e5f6g7h8.settings.json
    ├── e5f6g7h8.price.json
    └── ... (persists until user deletes)
```

---

## 🎨 UI LAYOUT BREAKDOWN

### Kiosk Page (1920×1080)
```
┌──────────────────────────────────────────────────────────┐
│ Print Kiosk    [Login] [☀️Dark/Light]  [Theme]           │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  LEFT PANEL (350px)      │        RIGHT PANEL (Flex)     │
│  ┌──────────────────┐    │    ┌──────────────────────┐   │
│  │ Scan to Upload   │    │    │ Documents Queue      │   │
│  │                  │    │    │                      │   │
│  │   ┌──────────┐   │    │    │ ☐ Doc1.pdf: ₹100    │   │
│  │   │          │   │    │    │ ☐ Doc2.pdf: ₹10     │   │
│  │   │  QR CODE │   │    │    │ ☐ Doc3.pdf: Needs   │   │
│  │   │          │   │    │    │    Setup    [🗑️]    │   │
│  │   └──────────┘   │    │    │                      │   │
│  │                  │    │    └──────────────────────┘   │
│  │  📱 Scan w/phone │    │    ┌──────────────────────┐   │
│  │  📶 Same network │    │    │ [Delete Selected]    │   │
│  │                  │    │    │ Total: ₹120           │   │
│  └──────────────────┘    │    │ [ENABLED] Pay Print  │   │
│                          │    └──────────────────────┘   │
└──────────────────────────┴──────────────────────────────┘
```

### Print Settings Modal
```
┌───────────────────────────────────────────────────────────┐
│ Print Settings                                         [×] │
├──────────────────────────────┬──────────────────────────┤
│                              │ Destination: Canon...  │
│                              │ Pages: All / Custom    │
│        PDF PREVIEW           │ Copies: 1 [+][-]      │
│     (Continuous Scroll)      │ Layout: Portrait       │
│                              │ Color: B&W / Color    │
│  [Page 1]                    │ Paper: A4 [▼]         │
│  [Page 2]                    │ PPS: 1 [▼]            │
│  [Page 3]                    │ ► More settings       │
│  ...                         │                        │
│  [Page 10]                   │ Total Pages: 10        │
│                              │ Total: ₹20             │
│  [Zoom] [Rotate] [Fit]       │ [Cancel] [Done]       │
│                              │                        │
└──────────────────────────────┴──────────────────────────┘
```

---

## 🔐 Authentication Flow

### First Time Setup
1. Click "Login" button
2. Click "New User? Register"
3. Enter Name, Surname, Mobile, Email, Password
4. Password requirements:
   - Minimum 6 characters
   - At least 1 uppercase letter
   - At least 1 lowercase letter
   - At least 1 symbol (!@#$%^&* etc)
5. Passwords must match
6. Click "Register"

### Subsequent Logins
1. Click "Login"
2. Enter mobile number
3. Enter password
4. Click "Login"
5. Redirects to owner dashboard

### Owner Dashboard Features
- Update mobile number
- Update password
- Delete account
- View pricing
- View job history

---

## 🧪 Testing the System

### Scenario 1: Basic Workflow
1. Open Kiosk Page
2. Upload 1 PDF (10 pages)
3. Open in print settings
4. Keep default (B&W, 1 copy, A4, 1 PPS)
5. Expected: Price = 10 × 1 × ₹2 = ₹20
6. Click Done
7. Button should enable
8. Total should show ₹20

### Scenario 2: Multiple Documents
1. Upload 3 PDFs (10, 5, 15 pages)
2. Configure Doc1: Color A4, 2copies = (10÷1)×2×₹5 = ₹100
3. Configure Doc2: B&W A4, 1copy = (5÷1)×1×₹2 = ₹10
4. Configure Doc3: Color A3, 2-up = (15÷2)×1×₹10 = ₹100
5. Expected Total: ₹210
6. Button should enable
7. Click Pay & Print

### Scenario 3: Custom Pages
1. Upload 20-page PDF
2. Set Pages: Custom → "1-5, 10-15"
3. That's 12 pages
4. B&W A4, 1copy = 12 × ₹2 = ₹24
5. Verify preview shows correct layout

### Scenario 4: N-up Layout
1. Upload 8-page PDF
2. Set Pages Per Sheet: 4 (2×2 grid)
3. That creates 2 sheets (8÷4=2)
4. Color A4, 1copy = 2 × ₹5 = ₹10
5. Preview should show 4 pages per sheet

---

## 📞 Common Issues & Solutions

### Issue: Port Already in Use
```bash
# Find process using port 5000/5001
netstat -ano | findstr :5000
# Kill process
taskkill /PID <PID> /F
```

### Issue: Files Not Syncing
- Check if Sync Service console shows errors
- Verify `cloud_uploads/TB001/` has files
- Wait 5 seconds and refresh kiosk page
- Check network connectivity

### Issue: PDF Preview Not Loading
- Check browser console (F12)
- Verify PDF.js CDN is accessible: `cdnjs.cloudflare.com`
- Try a different PDF file
- Check browser supports Canvas/JavaScript

### Issue: Price Not Calculating
- Ensure all form fields are filled
- Check browser console for errors
- Verify pricing in `kiosk_config.json`
- Try page refresh

### Issue: Button Not Enabling
- Verify ALL documents have settings saved
- Check `/session/TB001` API returns `ready=true`
- Try refreshing page
- Check browser console for errors

---

## 📊 System Status Indicators

### Green Dot (Online)
- Service is running and responding
- All endpoints accessible
- No errors in logs

### Gray Dot (Offline)
- Service crashed or not started
- Check logs in service console window
- Restart system with `python run_system.py`

### Slow Indicators
- Sync taking >5 seconds: Network issue
- Preview slow: Large PDF file
- Price calculation slow: Complex document

---

## 🎯 Next Integration Points

Once system is verified operational, next steps:

1. **Payment Gateway**
   - Integrate Razorpay for Indian market
   - Alternative: Stripe
   - Mock payment for testing

2. **Printer Integration**
   - Connect to physical printer via CUPS (Linux) or Windows Print Spooler
   - Format print jobs into device commands
   - Track print status

3. **Database**
   - Replace JSON with SQLite/PostgreSQL
   - Store job history
   - User analytics

4. **Authentication**
   - Hash passwords with bcrypt/werkzeug
   - Add rate limiting
   - Implement session timeout

5. **Mobile App**
   - React Native / Flutter
   - Push notifications
   - QR code scanning native API

---

## ✅ VERIFICATION CHECKLIST

Run through these steps to verify system is working:

- [ ] `python run_system.py` starts without errors
- [ ] All service windows open (3 windows total)
- [ ] Control center loads: http://localhost:5001
- [ ] Cloud Server responds: http://localhost:5000
- [ ] Kiosk Page loads: http://localhost:5001/kiosk/TB001
- [ ] QR code displays
- [ ] Upload page mobile responsive
- [ ] Upload files successfully
- [ ] Files appear in queue within 5 seconds
- [ ] "Needs Setup" status shows initially
- [ ] Modal opens without errors
- [ ] PDF preview renders
- [ ] Price calculates and updates live
- [ ] Settings save when clicking Done
- [ ] Status changes to "₹XX"
- [ ] Button enables when all configured
- [ ] Total cost correct
- [ ] No console errors
- [ ] Theme toggle works
- [ ] Responsive on mobile

---

## 📬 Final Notes

**This is a complete, production-ready system for:**
- Learning distributed systems architecture
- Understanding Flask microservices
- Real-time file synchronization
- Dynamic price calculation
- Modern UI/UX patterns

**All core functionality is implemented:**
✅ Multi-document queue management
✅ Real-time PDF preview with advanced controls
✅ Dynamic pricing calculation
✅ Settings persistence
✅ Auto-sync file management
✅ Owner authentication
✅ Responsive design
✅ Dark/Light theme

**Ready for:**
- Payment gateway integration
- Print hardware connection
- Multi-kiosk deployment
- Database backend
- Mobile app development

---

**Happy Printing! 🖨️**

