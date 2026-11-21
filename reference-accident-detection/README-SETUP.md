# SafeTrack AI — Setup Guide

## Prerequisites already satisfied ✅
- Python 3.8.10 venv at `C:\Users\Annish\OneDrive\Desktop\final-capstone\.venv` with all packages
- Node.js 22 + npm with all frontend packages in `frontend/road-safety-ui/node_modules`
- Both `.env` files created with your credentials
- YOLO model at `detection/yolov8n.pt`

---

## ⚠️ ONE THING YOU MUST DO FIRST — Firebase Key

The backend needs `backend/firebase-key.json` to function.

**Steps:**
1. Go to [Firebase Console](https://console.firebase.google.com)
2. Select project **accident-80ec3**
3. Project Settings → Service Accounts tab
4. Click **Generate new private key** → Download JSON
5. Rename the downloaded file to `firebase-key.json`
6. Place it at: `reference-accident-detection/backend/firebase-key.json`

---

## Running the Project

### Terminal 1 — Backend
```
double-click: start-backend.bat
```
Or manually:
```bat
cd backend
set PYTHONPATH=%CD%
C:\Users\Annish\OneDrive\Desktop\final-capstone\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```
Backend URL: http://localhost:8000  
Swagger docs: http://localhost:8000/docs

### Terminal 2 — Frontend
```
double-click: start-frontend.bat
```
Or manually:
```bat
cd frontend\road-safety-ui
npm run dev
```
Frontend URL: http://localhost:5173

---

## Initialize Admin Account (first time only)

After starting the backend, run:
```
double-click: init-admin.bat
```
Or: `POST http://localhost:8000/api/admin/init-super-admin`

**Admin login:** `admin@safetrack.ai` / `123456`

---

## Features

| Feature | Route | Notes |
|---------|-------|-------|
| Login / Register | `/login` | Firebase Auth |
| User Dashboard | `/overview` | Incident history |
| Live Stream | `/stream` | WebSocket + YOLOv8 spatial tracking |
| Video Upload | `/upload` | Cloudinary → YOLO detection |
| Behavior Analytics | `/analytics` | Charts from Firestore |
| Predictive Routing | `/predictive-routing` | Leaflet map |
| Safety Simulator | `/simulator` | |
| Billing / Razorpay | `/billing` | Test mode |
| Admin Dashboard | `/admin/dashboard` | Admin only |
| Model Config | `/admin/config` | Tune YOLO thresholds |
| Dispatch | `/admin/dispatch` | Emergency dispatch |
| Incident Map | `/admin/incident-map` | Live map |
| Reports Queue | `/admin/reports` | PDF reports |
| User Management | `/admin/users` | RBAC |

---

## Environment Files

- **Backend:** `backend/.env`
- **Frontend:** `frontend/road-safety-ui/.env`

---

## Architecture

```
Browser → React (Vite :5173)
            ↓ REST / WebSocket
FastAPI (:8000)
  ├── Firebase Admin (Firestore + Auth)
  ├── YOLO v8n (live webcam + video upload)
  ├── Gemini API (legacy reports)
  ├── Groq + ReportLab (PDF insurance reports)
  ├── Twilio (SMS alerts)
  ├── Gmail SMTP (email alerts)
  └── Razorpay (payment)
```
