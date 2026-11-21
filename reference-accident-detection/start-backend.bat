@echo off
echo ============================================================
echo   SafeTrack AI - Backend Server
echo ============================================================
echo.

cd /d "%~dp0backend"

set PYTHONPATH=%~dp0backend

echo Starting FastAPI backend on http://localhost:8000
echo Swagger docs: http://localhost:8000/docs
echo.
echo NOTE: Requires firebase-key.json in the backend/ folder.
echo       Download it from Firebase Console - Project Settings - Service Accounts
echo.

"c:\Users\Annish\OneDrive\Desktop\final-capstone\.venv\Scripts\uvicorn.exe" app.main:app --reload --port 8000
