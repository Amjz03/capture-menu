@echo off
rem Start OBS with replay buffer, then the capture menu
tasklist /FI "IMAGENAME eq obs64.exe" | find /I "obs64.exe" >nul
if errorlevel 1 (
  start "" /d "C:\Program Files\obs-studio\bin\64bit" obs64.exe --startreplaybuffer --minimize-to-tray --disable-shutdown-check
  timeout /t 5 /nobreak >nul
)
if "%1"=="exe" (
  start "" "%~dp0CaptureMenu.exe"
) else (
  start "" pyw "%~dp0capture_menu.py"
)
