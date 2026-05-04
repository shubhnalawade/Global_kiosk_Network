# SYSTEM WORKFLOW - DETAILED ANALYSIS

## 🎯 HIGH-LEVEL ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                 MOBILE USER (Phone/Tablet)                 │
│                      📱 User uploads PDFs                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ Scan QR Code
                     ↓
┌──────────────────────────────────────────────────────────────┐
│                   CLOUD SERVER :5000                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ • Receive PDF uploads from mobile                    │
│  │ • Store in local server storage                      │
│  │ • Serve upload.html (Mobile UI)                      │
│  └──────────────────────────────────────────────────────┘   │
└────────────────┬─────────────────────────────────────────────┘
                 │ Files uploaded here
                 ↓
        ┌────────────────────┐
        │ Local Storage      │
        │  └─ cloud_uploads/ │
        │     └─ TB001/      │
        │        └─ <uuid>_file
        └────────────────────┘
                 ↑
                 │ Kiosk Sync polls every 3s
                 │
┌────────────────┴─────────────────────────────────────────────┐
│              KIOSK SYNC SERVICE (Background)                 │
│  • Lists files in local cloud_uploads for kiosk_id           │
│  • Downloads files to kiosk/uploads/TB001/                   │
│  • Cleanup can be done via cloud server if needed            │
└────────────────┬─────────────────────────────────────────────┘
                 ↓
        ┌────────────────────┐
        │ kiosk/uploads/     │
        │  └─ TB001/         │
        │     ├─ <uuid>_file │
        │     ├─ .meta       │
        │     ├─ .settings   │
        │     └─ .price      │
        └────────────────────┘
                 ↑
                 │ Kiosk reads from here
                 │
┌────────────────┴─────────────────────────────────────────────┐
│                    KIOSK SERVER :5001                        │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ LEFT PANEL                  RIGHT PANEL              │    │
│  │ ├─ QR Code Display          ├─ Documents Queue       │    │
│  │ └─ Instructions             ├─ File List            │    │
│  │                             ├─ Total Cost           │    │
│  │                             └─ Pay & Print Button    │    │
│  └──────────────────────────────────────────────────────┘    │
│                  kiosk.html (Main UI)                        │
└────────────────────────────────────────────────────────────────┘
                 ↑
        ┌────────┴──────────┐
        │                   │
      USER                USER
    (PC/Kiosk)          (Mobile)
```

---

## 📊 DETAILED WORKFLOW STEPS

### STEP 1: Initial State
```
Kiosk Page (http://localhost:5001/kiosk/TB001)

┌─────────────────────────────────────────┐
│  LEFT PANEL              RIGHT PANEL    │
│                                         │
│  ┌─────────────────┐   ┌─────────────┐  │
│  │                 │   │ No documents│  │
│  │    QR Code      │   │    yet      │  │
│  │   (Scan me!)    │   │             │  │
│  │                 │   │ "Scan QR    │  │
│  │ [Image]         │   │  to upload" │  │
│  │                 │   │             │  │
│  └─────────────────┘   ├─────────────┤  │
│                        │ Total: ₹0   │  │
│                        │             │  │
│              [DISABLED] │ Pay & Print │  │
│                        └─────────────┘  │
└─────────────────────────────────────────┘

Status: Waiting for documents
```

### STEP 2: User Uploads PDFs
```
Mobile User:
1. Opens phone browser
2. Scans QR code on kiosk screen
3. Opens http://localhost:5000/upload?kiosk_id=TB001
4. Uploads 3 PDFs: Document1.pdf, Document2.pdf, Document3.pdf

Supabase Storage stores:
kiosk_files/TB001/
  ├── uuid1_Document1.pdf         ← 10 pages
  ├── uuid1.meta                  ← timestamp
  ├── uuid2_Document2.pdf         ← 5 pages
  ├── uuid2.meta                  ← timestamp
  ├── uuid3_Document3.pdf         ← 15 pages
  └── uuid3.meta                  ← timestamp
```

### STEP 3: Sync Service Downloads Files
```
Kiosk Sync Service:
- Every 3 seconds: List Supabase bucket path TB001/
- Detects new files
- Downloads to: kiosk/uploads/TB001/
- Optional cleanup can be done via cloud server if needed

Local Storage:
kiosk/uploads/TB001/
  ├── uuid1_Document1.pdf
  ├── uuid1.meta
  ├── uuid2_Document2.pdf
  ├── uuid2.meta
  ├── uuid3_Document3.pdf
  └── uuid3.meta
```

### STEP 4: Documents Appear in Kiosk Queue
```
GET /fetch/TB001 returns:
[
  {"name": "uuid1_Document1.pdf", "price": null},
  {"name": "uuid2_Document2.pdf", "price": null},
  {"name": "uuid3_Document3.pdf", "price": null}
]

Kiosk Page (Right Panel):
┌──────────────────────────────────┐
│ ✓ Select All                     │
├──────────────────────────────────┤
│ 📄 uuid1_Document1.pdf           │
│    Needs Setup     [🗑️]          │
├──────────────────────────────────┤
│ 📄 uuid2_Document2.pdf           │
│    Needs Setup     [🗑️]          │
├──────────────────────────────────┤
│ 📄 uuid3_Document3.pdf           │
│    Needs Setup     [🗑️]          │
├──────────────────────────────────┤
│ [Delete] Total: ₹0               │
│          [DISABLED] Pay & Print   │
└──────────────────────────────────┘
```

### STEP 5: User Opens First Document
```
User clicks: uuid1_Document1.pdf

Modal Opens:
┌─────────────────────────────────────────────────┐
│ Print Settings                           [×]    │
├──────────────────┬──────────────────────────────┤
│   PREVIEW        │  COLOR: BW    / Color        │
│   (10 pages)     │  COPIES: 1    [▼]            │
│                  │  PAGES: All   / Custom       │
│   [+] [100%] [-] │  LAYOUT: Portrait / Landscape│
│                  │  PAPER: A4     [▼]           │
│  Page 1 of 10    │  PPS: 1        [▼]           │
│   [<<] [>>]      │  ...                         │
│                  │  Total Pages: 10             │
│                  │  Total: ₹20                  │
│                  │  [Cancel] [Done]             │
└──────────────────┴──────────────────────────────┘

Calculation:
- 10 pages ÷ 1 (pages per sheet) = 10 sheets
- 10 sheets × 1 (copy) × ₹2/sheet (A4 BW) = ₹20
```

### STEP 6: User Modifies Settings for Document 1
```
User changes:
- Color: Color (₹5/sheet instead of ₹2)
- Copies: 2
- Pages Per Sheet: 2 (reduces physical sheets)
- Paper Size: A3

New Calculation:
- 10 pages ÷ 2 (2-up) = 5 logical sheets
- 5 sheets × 2 (copies) × ₹10/sheet (A3 Color) = ₹100 per document

Preview updates: Shows 2 pages per sheet layout
Real-time animation: Price updates green
```

### STEP 7: User Saves Settings for Document 1
```
User clicks: [Done]

POST /settings/TB001/uuid1_Document1.pdf:
{
  "color": "color",
  "copies": 2,
  "pages": "all",
  "sides": "one-sided",
  "pages_per_sheet": 2,
  "size": "a3"
}

Server Response:
{
  "price": 100
}

Files created:
  uuid1.settings.json
  └─ {"color": "color", "copies": 2, ...}
  
  uuid1.price.json
  └─ {"price": 100}

Queue updates:
  uuid1_Document1.pdf → "₹100" (green badge)
```

### STEP 8: User Opens Second Document
```
Clicks: uuid2_Document2.pdf (5 pages)

Modal opens with default settings:
- Default: A4, B&W, 1 copy, All pages, 1 page per sheet
- Calculation: 5 × 1 × ₹2 = ₹10

User keeps defaults and clicks [Done]

Files created:
  uuid2.settings.json
  uuid2.price.json ({"price": 10})

Queue updates:
  uuid2_Document2.pdf → "₹10"
```

### STEP 9: User Opens Third Document
```
Clicks: uuid3_Document3.pdf (15 pages)

User sets:
- Color: Color
- Pages Per Sheet: 4
- Copies: 1

Calculation:
- 15 ÷ 4 = 4 logical sheets (rounded up)
- 4 × 1 × ₹5 = ₹20

Files created:
  uuid3.settings.json
  uuid3.price.json ({"price": 20})

Queue updates:
  uuid3_Document3.pdf → "₹20"
```

### STEP 10: All Documents Configured
```
Queue shows:
┌──────────────────────────────┐
│ Document 1: ₹100  ✓          │
│ Document 2: ₹10   ✓          │
│ Document 3: ₹20   ✓          │
├──────────────────────────────┤
│ Total: ₹130                  │
│ [ENABLED] Pay & Print 🖨️     │
└──────────────────────────────┘

GET /session/TB001:
{
  "ready": true,
  "total": 130
}

All files verified:
✓ uuid1.price.json exists
✓ uuid2.price.json exists
✓ uuid3.price.json exists

ALL CONDITIONS MET → Button enabled!
```

### STEP 11: User Clicks Pay & Print
```
User clicks: [Pay & Print]

Current state:
- Queue: 3 documents
- Total Cost: ₹130
- All settings saved
- All prices calculated

↓ (Next integration point - Payment Gateway)
- Razorpay / Stripe integration
- Process payment
- Print jobs submitted to printer
- Status tracking begins
```

---

## 🔍 KEY LOGIC BREAKDOWN

### Price Calculation Formula
```
Total Price = (logical_pages ÷ pages_per_sheet) × copies × rate_per_sheet

Where:
- logical_pages = actual pages in PDF
- pages_per_sheet = N-up layout (1, 2, 4, 6, 9, 16)
- copies = requested copies
- rate_per_sheet = depends on {paper_size}_{color}

Example Scenarios:

Scenario A: 10-page PDF, Black & White, A4
- logical_pages = 10
- pages_per_sheet = 1
- copies = 1
- rate = A4_BW = ₹2
- Result: (10 ÷ 1) × 1 × ₹2 = ₹20

Scenario B: 10-page PDF, Color, A3, 2-up, 2 copies
- logical_pages = 10
- pages_per_sheet = 2
- copies = 2
- rate = A3_Color = ₹10
- Result: (10 ÷ 2) × 2 × ₹10 = ₹100

Scenario C: 5-page PDF, B&W, A4, 4-up, 1 copy
- logical_pages = 5
- pages_per_sheet = 4
- copies = 1
- rate = A4_BW = ₹2
- Result: (5 ÷ 4) × 1 × ₹2 = ₹2.50 → ₹3 (rounded up)
```

### File Lifecycle
```
Stage 1: UPLOAD (Cloud)
  User uploads PDF → Stored in Supabase bucket path TB001/
  Files: <uuid>_<original_name>.pdf, <uuid>.meta

Stage 2: SYNC (Local)
  Kiosk downloads → Stored in kiosk/uploads/TB001/
  Optional cleanup can be done via cloud server if needed

Stage 3: QUEUE (Display)
  PDF listed in Kiosk's right panel
  Status: "Needs Setup" (no price yet)

Stage 4: CONFIGURE (Modal)
  User opens PDF in modal
  Sets print settings
  Price calculated in real-time

Stage 5: SAVE (Settings)
  User clicks Done
  Files created:
    - <uuid>.settings.json (User's choices)
    - <uuid>.price.json (Calculated cost)
  Status changes to "₹XX"

Stage 6: READY (Payment)
  When ALL documents have .price.json files
  Total cost = sum of all prices
  Pay & Print button enabled
```

### Button State Logic
```
        ┌─────────────────────────────┐
        │  Check Session Status        │
        │  GET /session/TB001          │
        └────────────┬──────────────────┘
                     │
         ┌───────────┴────────────┐
         │                        │
    All files have      Missing price files
    .price.json?        for some documents
         │                        │
       YES                       NO
         │                        │
         ↓                        ↓
    ready=true            ready=false
         │                        │
         ↓                        ↓
  ┌─────────────────┐    ┌──────────────────┐
  │ ENABLED Button  │    │  DISABLED Button │
  │                 │    │                  │
  │ "Pay & Print"   │    │ "Proceed..."     │
  │ Purple gradient │    │ Gray background  │
  │ Click active    │    │ Click inactive   │
  └─────────────────┘    └──────────────────┘
```

---

## 🎨 UI STATE TRANSITIONS

### Kiosk Page Right Panel
```
STATE 1: No Documents
┌─────────────────────────────────┐
│ Documents Queue                 │
├─────────────────────────────────┤
│                                 │
│  No documents yet               │
│  Scan the QR code...            │
│                                 │
├─────────────────────────────────┤
│ Total: ₹0                       │
│ [DISABLED] Proceed to Payment   │
└─────────────────────────────────┘

STATE 2: Documents Arrived
┌─────────────────────────────────┐
│ ✓ Select All  Documents Queue   │
├─────────────────────────────────┤
│ ☐ 📄 Document1.pdf              │
│    Needs Setup    [🗑️]          │
├─ ── ── ── ── ── ── ── ── ── ── ─┤
│ ☐ 📄 Document2.pdf              │
│    Needs Setup    [🗑️]          │
├─ ── ── ── ── ── ── ── ── ── ── ─┤
│ ☐ 📄 Document3.pdf              │
│    Needs Setup    [🗑️]          │
├─────────────────────────────────┤
│ [Delete (3)] Total: ₹0          │
│            [DISABLED] Proceed    │
└─────────────────────────────────┘

STATE 3: Partially Configured
┌─────────────────────────────────┐
│ ✓ Select All  Documents Queue   │
├─────────────────────────────────┤
│ ☐ 📄 Document1.pdf              │
│    ₹100 ✓        [🗑️]          │
├─ ── ── ── ── ── ── ── ── ── ── ─┤
│ ☐ 📄 Document2.pdf              │
│    ₹10 ✓         [🗑️]          │
├─ ── ── ── ── ── ── ── ── ── ── ─┤
│ ☐ 📄 Document3.pdf              │
│    Needs Setup    [🗑️]          │
├─────────────────────────────────┤
│ [Delete] Total: ₹110            │
│        [DISABLED] Proceed        │
└─────────────────────────────────┘

STATE 4: All Configured ✓
┌─────────────────────────────────┐
│ ✓ Select All  Documents Queue   │
├─────────────────────────────────┤
│ ☐ 📄 Document1.pdf              │
│    ₹100 ✓        [🗑️]          │
├─ ── ── ── ── ── ── ── ── ── ── ─┤
│ ☐ 📄 Document2.pdf              │
│    ₹10 ✓         [🗑️]          │
├─ ── ── ── ── ── ── ── ── ── ── ─┤
│ ☐ 📄 Document3.pdf              │
│    ₹20 ✓         [🗑️]          │
├─────────────────────────────────┤
│ [Delete] Total: ₹130            │
│     [ENABLED] Pay & Print 🖨️    │
│     (Green/Purple gradient)      │
└─────────────────────────────────┘
```

---

## 📡 API SEQUENCE DIAGRAM

```
USER                KIOSK PAGE              CLOUD SERVER         KIOSK SYNC
 │                      │                       │                    │
 ├─ Scan QR ────────→  │                        │                    │
 │                      │―― GET /qr/TB001 ──→ │                    │
 │                      │← QR Image ―――――――――│                    │
 │                      │                        │                    │
 │────────────────────────────────────────────────────────────────────│
 │ (Opens upload page on phone)               │                    │
 │                      │                        │                    │
 ├─ Upload PDF ═════════════════════════════→│                    │
 │ (to :5000)           │                        │                    │
 │                      │                        │── Store in cloud ──│
 │                      │                        │                    │
 │                      │                        │  [POLLING LOOP]    │
 │                      │                        │←― GET /fetch ――― │
 │                      │                        │                    │
 │                      │                        │― Files list ═════→│
 │                      │                        │                    │
 │                      │                        │←― (DOWNLOAD) ―――│
 │                      │                        │                    │
 │                      │                        │― POST /ack ──────→│
 │                      │                        │  (clean cloud)     │
 │                      │                        │                    │
 ├ Clicks PDF ──────→  │                        │                    │
 │                      │―― GET /preview ━━━━━━━━━━━━━━━━━━━━━━→
 │                      │← PDF content ─────────────────────────────│
 │                      │                        │                    │
 ├ Sets settings ──→  │                        │                    │
 │                      │―― POST /price ──────→│                    │
 │                      │← Calculated price ───│                    │
 │                      │                        │                    │
 ├ Clicks Done ─────→  │                        │                    │
 │                      │―― POST /settings ───→│                    │
 │                      │← Saves settings ─────────────────────────│
 │                      │                        │                    │
 ├ Repeats for all ──────────────────────────────────────────────────
 │ documents
 │
 ├ All done ─────────→  │                        │                    │
 │                      │―― GET /session ─────────────────────────→
 │                      │← ready=true ────────────────────────────│
 │                      │   total=₹130                              │
 │                      │                        │                    │
 ├ Clicks Pay ──────→  │                        │                    │
 │                      │――[PAYMENT GATEWAY]─→                     │
 │                      │←[PRINT SUBMISSION]──                     │
 │
```

---

## ✅ VERIFICATION CHECKLIST

### System Startup
- [ ] Cloud Server started (Port 5000)
- [ ] Kiosk Server started (Port 5001)
- [ ] Sync Service running
- [ ] No console errors

### Landing Page
- [ ] http://localhost:5001 shows landing page
- [ ] Kiosk Page link works
- [ ] Upload Page link works
- [ ] Status bar shows all services online

### Kiosk Page
- [ ] QR code displays correctly
- [ ] Queue shows "No documents yet" message
- [ ] "Proceed to Payment" button is DISABLED (gray)

### Upload Page
- [ ] Mobile responsive layout
- [ ] Drag & drop area visible
- [ ] Upload successful message appears
- [ ] Multiple file support works

### Document Sync
- [ ] Files appear in kiosk queue within 5 seconds
- [ ] Each document shows "Needs Setup" status
- [ ] File cards have delete buttons

### Print Settings Modal
- [ ] Modal opens on document click
- [ ] Preview renders PDF pages
- [ ] Preview controls (zoom, rotate) work
- [ ] Settings panel populated with defaults
- [ ] Price displays at bottom

### Price Calculations
- [ ] Price updates when changing color (BW vs Color)
- [ ] Price updates when changing copies
- [ ] Price updates when changing pages per sheet
- [ ] Price animation plays (green pulse)
- [ ] Final price matches manual calculation

### Button State
- [ ] After first document: Button still DISABLED
- [ ] After second document: Button still DISABLED
- [ ] After all documents: Button ENABLED (purple)
- [ ] Total cost shows correctly
- [ ] "Proceed to Payment" changes to "Pay & Print"

### End-to-End
- [ ] Upload 3 documents
- [ ] Configure each (different settings)
- [ ] Verify total cost = sum of individual costs
- [ ] Button is enabled
- [ ] No console errors

---

**System Status**: ✅ OPERATIONAL  
**Last Tested**: February 2025  
**Version**: 1.0.0

