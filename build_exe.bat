@echo off
rem Optional: builds a standalone CaptureMenu.exe (no Python needed to run it afterwards).
rem Run this once on Windows after Setup.cmd. The result is in dist\CaptureMenu\.
cd /d "%~dp0"
py -3 -m pip install --disable-pip-version-check -q pyinstaller
py -3 -m PyInstaller --noconfirm --windowed --name CaptureMenu --add-data "assets;assets" --collect-all sdl2dll --collect-all obsws_python capture_menu.py
if errorlevel 1 goto :eof
copy /y config.json dist\CaptureMenu\ >nul
echo.
echo Built: dist\CaptureMenu\CaptureMenu.exe  (run Setup.cmd in that folder once to make it start with Windows)
copy /y setup.ps1 dist\CaptureMenu\ >nul
copy /y Setup.cmd dist\CaptureMenu\ >nul
pause
