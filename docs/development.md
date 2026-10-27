# Development

Back to the [README](../README.md).

Capture Menu is a Python package built on [PySide6](https://doc.qt.io/qtforpython-6/), [OBS Studio](https://obsproject.com/) through its WebSocket, [SDL2](https://www.libsdl.org/) for controllers and [FFmpeg](https://ffmpeg.org/) for thumbnails, trims and share copies.

```
capture_menu.py      thin launcher (source and PyInstaller entry point)
capturemenu/          application package
  app.py              startup
  runtime.py          paths (source or built exe) and logging
  preferences.py      defaults, config.json and state.json
  language.py         translations, RTL and time labels
  windows.py          display/window integration, process launch and startup registration
  obs_client.py       OBS WebSocket, encoder plans and OBS process helpers
  media.py            FFmpeg, trimming, previews, export and audio processing
  catalog.py          capture names, sizes, folders and storage helpers
  capture_controller.py  capture/library operations and background work
  input_devices.py    keyboard, controller navigation, input mode and sounds
  updates.py          release lookup, verified download and installer handoff
  version.py          release version (stamped by the workflow)
  ui_theme.py         styles, drawing helpers and window appearance
  ui_widgets.py       reusable controls and timeline
  ui_*.py             menu, viewer, gallery, settings and notifications
  diagnostics.py      crash logging and freeze detection
config.json          default settings
assets/              icon, sounds, button-prompt font, interface icons
installer/           Setup.exe (Inno Setup), the Python-version setup and uninstall scripts, build_exe.bat
tests/               feature tests
tools/               screenshot renders for the docs, benchmarks
docs/                images for this README
```

**Run from source:** double-click `installer\Setup.cmd`. It installs Python 3.12, the libraries, OBS and FFmpeg, and installs the app from this folder (run it again after changes). Or run `py -3 capture_menu.py` directly with the libraries from `requirements.txt`.

**Tests** are plain scripts that print `PASS` lines: `py -3 tests\test_trim.py <repo folder> <scratch folder>`. Set `QT_QPA_PLATFORM=offscreen` to keep their windows off your screen. `py -3 tests\run_release_tests.py` runs the set the release workflow requires. Importing `capturemenu.app` has no side effects; only `app.main()` starts the app.

**Build:** `installer\build_exe.bat` makes `dist\CaptureMenu\CaptureMenu.exe`, and `Output\CaptureMenu-Setup.exe` when [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed.

**Release:** change `VERSION` (e.g. to `v0.0.2`) and `APP_VERSION` in `capturemenu/version.py` to match on `main`, and push (the release tests check they agree). GitHub Actions builds `CaptureMenu-Setup.exe` and the Python `CaptureMenu.zip` on Windows and publishes them. Changes are listed in [CHANGELOG.md](../CHANGELOG.md).

**winget:** `installer\winget` holds the manifests for `Amjz03.CaptureMenu`. For a new release, set the version, the installer URL and its SHA-256 (shown on the release's asset), run `winget validate --manifest installer\winget`, and submit them to [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) (for example with `wingetcreate update Amjz03.CaptureMenu`).

**Promo video:** `tools\render_promo.py` renders a 16:9 and a 9:16 video from the app's real screens.
