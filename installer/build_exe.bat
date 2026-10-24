@echo off
rem Builds dist\CaptureMenu\CaptureMenu.exe (no Python needed to run it), then
rem Output\CaptureMenu-Setup.exe if Inno Setup 6 is installed. Releases do this on GitHub.
cd /d "%~dp0.."
py -3 -m pip install --disable-pip-version-check -q -r requirements.txt pyinstaller
py -3 -m PyInstaller --noconfirm --windowed --name CaptureMenu --icon assets\icon.ico --add-data "assets;assets" --collect-submodules capturemenu --collect-all sdl2dll --collect-all obsws_python capture_menu.py
if errorlevel 1 goto :end
echo.
echo Built: dist\CaptureMenu\CaptureMenu.exe

set /p VERSION=<VERSION
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
  echo Install Inno Setup 6 to also build CaptureMenu-Setup.exe: https://jrsoftware.org/isinfo.php
  goto :end
)
"%ISCC%" /Q /DAppVersion=%VERSION:v=% installer\installer.iss
if errorlevel 1 goto :end
echo Built: Output\CaptureMenu-Setup.exe

:end
pause
