# Changelog

## 0.0.10 · 2026-10-17

- **Starts the moment you sign in.** Capture Menu now starts from a Task Scheduler task that runs right at sign-in, instead of Windows' startup list, which waits half a minute or more and sometimes skipped it. Updating sets it up on its own; Settings → Start with Windows turns it on and off.
- **No more "Run in Safe Mode?" from OBS after a restart.** When Windows restarted while OBS was still closing, OBS asked about Safe Mode the next time and recorded nothing until you answered. Capture Menu now clears what OBS left behind before starting it.

## 0.0.9 · 2026-10-17

- **Starts with Windows every time.** Capture Menu now starts from Windows' startup list in the registry instead of the Startup folder, which Windows sometimes skips at sign-in, so it didn't come back after a restart. Updating moves it over on its own; Settings → Start with Windows works as before.
- **Clearer Settings.** Each section sits on its own card, every value lines up in one column, choices show ‹ › on every row so it's clear they can change, and folders, the shortcut and updates end with › like a button.
- Fixed: in Arabic, Settings' names and descriptions started in the middle of the row instead of on the right, and so did captions in the gallery.

## 0.0.8 · 2026-10-17

- **Less RAM while you play.** Once everything has been closed for a minute or two, the bar, the viewer, the gallery and Settings let go of their screen-sized windows (about 15 MB each at 1440p, 33 MB at 4K) and Qt's cache of drawn pictures, and the viewer drops the last screenshot it showed. After a session of browsing, Capture Menu goes back to about 70 MB instead of 120 MB. Pages still open instantly. The gallery keeps two screens of tiles instead of 160 tiles.

## 0.0.7 · 2026-10-17

- **HDR.** Settings → HDR: **Auto** records in HDR (10-bit, Rec.2100 PQ, AV1 or HEVC) while Windows HDR is on for your main screen. Trims stay HDR; shared copies, thumbnails and previews are turned into normal colours, tuned to look like the built-in player, so they don't come out grey on phones or Discord. **Off** always records normal colours.
- **Glass.** The viewer, the gallery and Settings sit on frosted glass: the game shows through behind them, blurred and dimmed, like the PS5. It's Windows' own acrylic blur, so it costs the game nothing; where Windows can't do it the pages stay solid as before.
- **A calmer viewer.** The video sits in its own card with play, the timeline, sound on / off and "only the video" built in. Under it, four big buttons show the controller button that does each one: ▢ Trim, L3 Adjust audio, Options Share / Export, △ More. Favorite, Show in folder, Open in your video player and Delete moved into **More** (△ / M); △ no longer deletes, and Delete still needs a second press.
- **Adjust audio** shows your voice and the game as two cards, each with a volume bar and a **Mute** switch (M / △).
- **Share / Export** is three cards (Format, Your voice, Size limit) and one Export & copy button, instead of a row of presets.
- **Rename** opens a small dialog over the video, with the note tucked away until you add one.
- Fixed: on a 1920×1080 screen some viewer buttons lost the end of their names.
- **More** in the viewer is a titled panel with the same big icon buttons; the star turns yellow once favorited.
- **Select in the gallery.** A Select button at the top: then a click picks captures instead of opening them, every tile shows a circle that fills in, and the top bar becomes Select all · Delete · Cancel. ▢ / Space and Ctrl+click still pick right away.

## 0.0.6 · 2026-10-17

- When Windows Security protects the Videos folder, nothing needs changing: Capture Menu says once, calmly, where your captures are saved instead (`C:\Users\<you>\Capture Menu`), without asking you to change Windows' settings. Settings → Clips folder shows the folder actually in use.

## 0.0.5 · 2026-10-17

- Fixed: Capture Menu crashed on start ("The system cannot find the file specified: …\Videos\Clips") on PCs where Windows Security's Controlled folder access (ransomware protection) blocks unknown apps from Videos. It now starts anyway, saves captures in `C:\Users\<you>\Capture Menu` for the time being, points OBS there too, and says how to allow CaptureMenu.exe and obs64.exe so Videos can be used. Your chosen folder is kept and used again as soon as it's allowed.
- Fixed: with two screens, Settings, the gallery or the viewer could open on the other screen, and Back could jump again. The app now stays on the screen the bar opened on until you close it; opening it again (Create, the hotkey, the tray) picks the game's screen again. Notices shown while a page is open appear on that page's screen.

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
