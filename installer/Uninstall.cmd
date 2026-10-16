@echo off
rem Removes Capture Menu: stops it, deletes its shortcuts and its folder.
rem Your captures (Videos\Clips), OBS and FFmpeg are kept.
cd /d "%TEMP%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
echo.
echo Press any key to close this window.
pause >nul
