@echo off
echo ============================================================
echo   SafeTrack AI - Frontend Dev Server
echo ============================================================
echo.

cd /d "%~dp0frontend\road-safety-ui"

echo Starting Vite dev server...
echo Frontend will be at: http://localhost:5173
echo.

npm run dev
