@echo off
echo ============================================================
echo   SafeTrack AI - Initialize Super Admin Account
echo ============================================================
echo.
echo This seeds the admin account using SUPER_ADMIN_EMAIL and
echo SUPER_ADMIN_PASSWORD from backend/.env
echo.
echo Make sure the backend is running first (start-backend.bat)
echo.
pause

curl -X POST http://localhost:8000/api/admin/init-super-admin
echo.
echo Done. Admin credentials: admin@safetrack.ai / 123456
