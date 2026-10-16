# Changelog

## 0.0.2 · 2026-10-16

- **Arabic.** The whole interface is translated and mirrored right to left. Settings → General → Language: same as Windows, English or العربية. Translations live in `assets/lang/`, so adding a language is one JSON file.
- **Your voice louder or quieter, per clip.** In the viewer press V (L3) for Sound: change how loud your voice and the game are in that clip, listen to 12 seconds first, then save. The separate voice and game tracks are kept, so it can always be changed back.
- **Screenshots folder.** Settings → Library now has a clips folder and a screenshots folder; screenshots stay with the clips unless you pick another one. The gallery shows both.

## 0.0.1 · 2026-10-16

First public build.

- **Capture bar** on Alt + C or the controller's Create button: save recent gameplay (15 s to 30 min), screenshot, record, mic on/off.
- **Per-game folders**, a viewer with frame-exact trim, titles and notes, favorites, and a gallery with sizes, sorting and multi-delete.
- **Share copies** for phones and Discord (10 / 50 / 500 MB), with or without your voice.
- **Follows the game's screen** across monitors and TVs, a REC timer, double-press to save, sounds and controller rumble.
- **Settings page** for recording quality, buffer length, shortcuts and controls.
- **One-click install:** `CaptureMenu-Setup.exe` installs the app with its icon, plus OBS Studio and FFmpeg, connects OBS and sets it up for the PC. Uninstall from Windows Settings → Apps.
- Fixed: OBS auto-setup no longer fails on a fresh OBS where the replay buffer is off.
- Fixed: clips save right after install, even before FFmpeg is on the PATH.
