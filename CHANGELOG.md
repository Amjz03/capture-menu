# Changelog

## 0.0.29 · 2026-10-24

- **Rename right in the title, no window.** Rename turns the viewer's title into the text field where it is, with the note under it. Enter saves, Esc or ◯ cancels. If Windows keeps the keyboard on another window (it can, after a controller press), the line under the field says to click the name first; a click always brings the typing here.

## 0.0.28 · 2026-10-24

- **Show in folder opens the right folder.** For games with spaces in their name (Red Dead Redemption 2, Call of Duty), File Explorer opened Documents instead of the capture's folder. It now opens the game's folder with the capture selected.
- **Rename says what to do.** The box now reads "Type a new name, then press Enter", the name field has a pencil in it, and the current name is selected in blue so it's clear typing replaces it. With a controller, the hints show ⏎ Save too.

## 0.0.27 · 2026-10-24

- **Rename takes your typing after a controller press.** Pressing Rename with ✕ opened the box, but Windows kept the keyboard on the game, so nothing you typed showed up. The viewer now takes the keyboard when the box opens.
- **Show in folder and Open in your video player get Capture Menu out of the way.** The viewer (and the gallery behind it) closes first, so the folder or the player isn't covered. The gallery's own folder button does the same.

## 0.0.26 · 2026-10-23

- **The D-pad reaches the buttons along the top of the gallery and Settings too.** In the gallery, ↑ from the top row of captures goes to Back, Sort, Select, the folder and Close, and ← → walk them; the side of the grid leads to the games list, and ↓ comes back down. In Settings, ↑ from the first setting goes to Back, Restore defaults, Cancel and Save, and ↓ goes back to the setting you came from. ✕ presses what's highlighted.
- **A clearer highlight on white buttons.** Save, Export & copy and the other main buttons get a ring when highlighted instead of looking slightly smaller.

## 0.0.25 · 2026-10-23

- **Move around the viewer with the controller, like a mouse.** The D-pad moves a highlight over everything on screen (Back, Rename, newer / older, Close, Play, the seek bar, sound, full screen and every action button), and ✕ presses what's highlighted. On the seek bar, ← → move through the video. A clip starts on Play and a screenshot on Share. L1 / R1, □, △, Options, L3 and ◯ still work as shortcuts, and the keyboard keeps its own keys.
- ↑ and ↓ no longer stand for Favorite and Share in the viewer: they move the highlight. Favorite is the star button, or F on the keyboard.

## 0.0.24 · 2026-10-23

- **No More button in the viewer.** Favorite, Show in folder, Open in your video player and Delete are small icon buttons at the end of the main row, so they're one click away (their names show when you point at them). With a controller, △ moves the highlight onto them; on the keyboard, M. Delete still needs a second press, and Rename stays next to the title.

## 0.0.23 · 2026-10-23

- **Back in the viewer goes back.** A capture opened by clicking its notice (or the notice's Trim button) had nowhere to go back to, so Back closed everything and dropped you into the game. Back now goes to the Create bar, the same as opening it with Create then △.

## 0.0.22 · 2026-10-23

- **The Create bar and the gallery look like 0.0.20 again**, with these refinements:
- **Clearer text.** Grey text is brighter and the small text is a size larger: button names and hints in the bar, capture titles and details in the gallery, notices, the viewer and Settings descriptions. Easier to read from the couch.
- **A tidier gallery.** Same games list on the side, but the captures now share the width evenly in larger tiles (4 across on a 1080p screen), with bigger titles under them.
- **Smoother motion.** Notices fade in as they slide in, and fade out instead of vanishing. In the gallery, the tile you leave shrinks back smoothly while the new one grows.

## 0.0.21 · 2026-10-23

- **The Create bar is laid out like the PS5's.** A solid night-blue band along the bottom: your latest captures at the start, Save recent, Screenshot and Record as round buttons in the middle of the screen, and Mic, All captures and Settings as smaller round buttons at the end. The focused button grows into a white circle and only it shows its name, like on the PS5. Keys, controller and mouse work as before.
- **The gallery is laid out like the PS5's Media Gallery.** All, Favorites and each game are tabs across the top (still switched with L1 / R1 or [ ]), with Sort and Select beside them. Captures fill the width in a tight grid of larger tiles, each with its title and details written on the picture, the length at the top left and the favourite star at the top right. The current tile grows on top of its neighbours.

## 0.0.20 · 2026-10-23

- **Looks and feels more like the PS5.** The whole interface moves to the PS5's night blue: the glass behind pages, the Create bar, notices and Settings cards. The focused tile now grows into place with a white ring and a soft glow, smoothly, and settles back when you move on, in the Create bar, the Save recent row and the gallery. Tiles, cards and buttons are larger and rounder, titles are bigger, and switches that are on turn PlayStation blue.
- **Smooth motion.** The Create bar slides up when it opens and notices slide in from the edge of the screen, like the PS5's.
- **A clearer REC indicator.** The recording timer is a little larger, with a soft red glow on the dot.

## 0.0.19 · 2026-10-23

- **Clips and screenshots look like Windows' own screenshots.** With Windows HDR on, OBS turned the HDR screen into normal colours itself, which lifted the blacks (black came out dark grey) and dimmed the whites (white came out at 81 %): everything looked grey and flat. Capture Menu now has Windows do that conversion (OBS's Display Capture → Force SDR), the same one the Snipping Tool uses, so blacks are black and whites are white. Colours → Natural now matches Windows exactly; Soft, Vivid and Max add colour on top. HDR clips (HDR → Auto) are unchanged.

## 0.0.18 · 2026-10-23

- **Pick how colourful.** Settings → Recording → Colours now has four levels for an HDR screen recorded in normal colours: **Natural** (as OBS records it), **Soft** (×1.3 colour), **Vivid** (×1.6, the default) and **Max** (×2). The change shows up in OBS as soon as you save.

## 0.0.17 · 2026-10-23

- **More colourful Vivid.** Colours → Vivid now boosts colour and contrast more (saturation ×1.6, contrast ×1.1, up from ×1.3 and ×1.06) when an HDR screen is recorded in normal colours. It's applied to OBS at every start, so the new look shows up right after updating.

## 0.0.16 · 2026-10-23

- **HDR clips look right in your library.** HDR clips recorded by OBS weren't recognised as HDR, so their thumbnails, previews, shared copies and copies came out grey and washed out. They're recognised now, and the first start after updating remakes the thumbnails of the HDR clips you already have, in normal colours.

## 0.0.15 · 2026-10-23

- **Copied HDR clips keep their colours.** Discord, WhatsApp and most video players show HDR clips grey and washed out. Copy now puts a normal-colour copy of an HDR clip on the clipboard (made like Share → Phone & WhatsApp, full quality, saved in the game's Shared folder), so it looks right wherever you paste it. Normal clips are copied as they are.

## 0.0.14 · 2026-10-23

- **Pick the colours.** Settings → Recording → Colours: **Vivid** (the default) adds a little colour and contrast when an HDR screen is recorded in normal colours; **Natural** keeps the colours exactly as OBS records them. HDR clips (HDR → Auto) are never changed.

## 0.0.13 · 2026-10-23

- **Richer colours with Windows HDR on.** Recording an HDR screen in normal colours left the game looking flat next to what you see while playing. Capture Menu now adds a light colour correction (a bit more colour and contrast) to OBS's display capture in that case, so clips and screenshots look closer to the game. It's removed again when HDR clips are on or Windows HDR is off.

## 0.0.12 · 2026-10-23

- **No more washed-out captures with Windows HDR on.** With HDR set to Off (or H.264), OBS turns an HDR screen into normal colours assuming 300-nit white, but Windows usually shows normal content dimmer, so clips and screenshots came out grey and dull. Capture Menu now gives OBS the same white level as Windows' "SDR content brightness" slider, so captures look like your screen. Changing the slider sets OBS up again on the next start.

## 0.0.11 · 2026-10-17

- **Pick the recording screen.** Settings → Devices → Recording screen: **Follow the game** (the default, as before) or any of your screens by name, like `LG TV · 3840×2160`. A picked screen is always recorded, wherever the game is; while it isn't connected, the game's screen is. If you had turned off "Follow the game's screen", it becomes your main screen.
- **Pick the microphone.** Settings → Devices → Microphone: **Same as Windows** (the default) or any microphone OBS can record, shown by its device name. A microphone you chose in OBS itself is kept until you pick one here.
- **Hover only lends the highlight.** Moving the mouse over Settings, the bar or the Save recent row lights up what's under it only while it's there; when the mouse leaves, the highlight goes back. A click or a key keeps it. Hovering in Settings no longer scrolls the page.

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
