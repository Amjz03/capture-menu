# Changelog

## 0.0.4 · 2026-10-16

- Fixed: installing an update could stop with "DeleteFile failed; Access is denied" on VCRUNTIME140.dll. OBS, started by Capture Menu, had picked up Capture Menu's own copy of that file and kept it open. Programs Capture Menu starts now get Windows' normal libraries, and Setup closes OBS (like clicking ✕) and waits for it before replacing files; Capture Menu starts it again afterwards.

## 0.0.3 · 2026-10-16

- **Volume bars.** The Sound panel in the viewer has two simple bars, Your voice and Game, in % (100% = as recorded, 0% = muted, your voice up to 400%). Drag them or use the arrows.
- **Updates from inside the app.** Settings → General → Updates (or the tray icon) checks GitHub for a new version and installs it when you press again. Nothing updates by itself.
- **Arabic that reads naturally.** Every text rewritten in everyday wording, with consistent names: مقطع، لقطة شاشة، تسجيل، معرض الوسائط; sizes in ميجا / جيجا.
- **Freezes leave a trace.** If the interface stops responding for 6 seconds, where it was stuck goes into crash.log, so a freeze that can't be reproduced can still be fixed. The viewer logs each clip it opens.
- Fixed: the viewer could freeze when you closed a video (Windows: "not responding"). The controller reader turned on Windows controller interfaces that the video player then waited on forever. PlayStation and Xbox controllers still work.
- **Controller notices.** A short notice when a controller connects or disconnects.
- Fixed: a startup error when OBS wasn't ready yet to report its screens.
- **Back, everywhere.** The viewer, the gallery, Settings and the Save recent row have a Back button. It goes one step back: an open panel first, then to where you came from (the bar or the gallery). Esc and ◯ / B do the same, and the hints say Back.

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
