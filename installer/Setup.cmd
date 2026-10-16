@echo off
rem One-click setup for Capture Menu
if not exist "%~dp0setup.ps1" (
  echo.
  echo   Please extract the zip first:
  echo   right-click CaptureMenu.zip, choose "Extract All", then run Setup.cmd
  echo   from the extracted folder.
  echo.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
echo.
pause
