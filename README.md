# Capture Menu: a PS5-style Create button for Windows

**[Download](https://github.com/Amjz03/capture-menu/releases/latest)** · [Install in 3 steps](#install)

Press **Alt + C** while gaming or anywhere on the desktop. A bar appears along the bottom of the screen, like the PS5 Create menu, so the game stays visible above it:

- **Create:** Save recent, Screenshot, Record
- **Recent:** your latest captures with their length, plus All captures

| Key | Action |
|---|---|
| ← → | Move between tiles (hovering with the mouse works too) |
| Enter | Select |
| ↑ or Enter on **Save recent** | Opens the PS5-style row: Full video, Last 15s, 30s, 1m, 3m, 5m, 15m, 30m |
| 1–8 | Save that option instantly (1 = Full video, 2 = Last 15s, …) |
| S / R | Screenshot / start or stop recording |
| V | View the latest capture |
| T | Trim the latest capture |
| M | Mic on / off |
| O | Open the gallery |
| Esc | Close (clicking back into the game closes it too) |

**With a controller.** Press **Create** on a DualSense (the small button left of the touchpad), just like on the PS5. Xbox and most other controllers work too.

| Button (DualSense / Xbox) | In the bar | In the viewer | While trimming |
|---|---|---|---|
| D-pad or left stick | Move / pick a duration | ← → skip 5 sec | ← → skip 5 sec |
| ✕ / A | Select | Play / pause | Save as new clip |
| ◯ / B | Back / close | Close | Cancel |
| ▢ / X | Screenshot | Trim | Set start |
| △ / Y | View latest | Delete | Set end |
| L1 R1 / LB RB | | Newer / older | Preview |

The on-screen hints follow whatever you're holding: ✕ ◯ ▢ △ for a PlayStation controller, A B X Y for Xbox, and keys as soon as you touch the keyboard.

Change the button in **Settings**, or in `config.json` with `controller_button`: `create`, `ps`, `options`, `touchpad`, `mute`, `share` (Xbox Series), `view`, or a combo like `l1+r1`.
If your game already uses that button (some use Create/View for the map), set `controller_hold_ms` to `400`: then only a press-and-hold opens the bar, and a quick tap still goes to the game.

> Steam opens Big Picture on the PS button, so `ps` only works when Steam isn't running or its Guide button chord is turned off.

**A folder per game, like the PS5.** Capture Menu checks which game (or app) is on screen when you press the hotkey and saves there automatically:

```
Videos\Clips\
├── Cyberpunk 2077\
├── Elden Ring\
├── Valorant\
└── Desktop\        ← captures taken outside a game
```

The menu shows the detected name next to the title. A recording goes to the game it **started** in, even if you stop it from somewhere else.

**Check it right away, like the PS5.** After every capture a notification shows its thumbnail. Open the menu: the **Recent** row has your last 4 captures. Click one, or press **V** for the latest, to open the viewer:

| Key | In the viewer |
|---|---|
| Space | Play / pause |
| ← → | Skip 5 seconds |
| A / D | Newer / older capture |
| T | Trim |
| Del | Delete (press twice; it goes to the Recycle Bin) |
| Esc | Close |

Two small buttons next to them show the file in its folder and open it in your own video player.

If the built-in player can't show a clip's picture (for example AV1 without GPU decoding), Capture Menu notices within about 2 seconds and plays a light 720p preview copy instead. Your original clip is untouched.

**Trim, like the PS5.** Press **T** (or ✂ Trim). A filmstrip of the clip appears with two blue handles:

| Key | While trimming |
|---|---|
| Drag the handles | Set start and end (the video shows that frame) |
| I / O | Set start / end at the playhead |
| P | Preview just the selection |
| Enter | Save as a new clip (the original stays) |
| Esc | Cancel |

You can also pick **Replace original**, which keeps the trimmed part and sends the full clip to the Recycle Bin. Trims are cut frame-exact on the GPU (NVENC) in the same format as the original, so they look the same.

**Save recent gameplay** shows how much is recorded right now, e.g. `19:20 / 30:00`. Options longer than that are dimmed; picking one saves everything recorded so far. The row remembers your last choice.

**Picked too short?** Open the menu again and pick a longer duration. The new clip still contains the earlier moment, and **both clips are kept**. Nothing is ever deleted for you.

**Share it.** In the viewer press **E** (Options on the controller, or the Share button):

| Option | What you get |
|---|---|
| Copy file | The capture itself on the clipboard: paste it anywhere with Ctrl+V |
| Phone & WhatsApp | MP4 (H.264, up to 1080p) that plays on every phone |
| Discord · 10 / 50 / 500 MB | Shrunk to fit Discord's limit (free / Nitro Basic / Nitro). Long clips drop to 720p or 480p; a clip too long for the limit asks you to trim it first |
| Without my voice | Shown when the clip has your voice on its own track (see below): the copy keeps the game sound only |

Converted copies go into a `Shared` folder inside the game's folder and are **copied to the clipboard**, so you paste them straight into Discord or WhatsApp Desktop. Your original stays as it is.

**Trim right after saving.** The save notification is clickable: click it to open the capture, or its **Trim** button to go straight to trimming. In the bar, **T** (R1 on the controller) trims the latest capture.

**Titles and notes.** In the viewer press **N** (or Rename) to give a capture a title, like "Clutch 1v4 on the bridge", and a note. The title shows in the viewer, the Recent row and the gallery, and names the copies you share. The file itself keeps its name.

**Favorites.** Press **F** in the viewer (D-pad ↑ on the controller) to star a capture. Stars show on the thumbnails and in the gallery's ★ Favorites list.

**Gallery, like the PS5 Media Gallery.** "All captures" in the bar (or **O**) opens every capture: All, ★ Favorites, then each game with its count and size. Arrows move, Enter opens the viewer, **[ ]** (L1 / R1) switches game, **F** (△ / Y) stars.

- **Sizes and sorting:** every capture and game shows its size. **S** (or "Sort") switches between Newest and **Largest**, which also puts the biggest games first, so you can see what's filling the drive.
- **Delete several at once:** **Space** (▢ / X on the controller, or Ctrl+click) marks captures, **Ctrl+A** marks the whole list, then **Del** (Options / Menu). The first press asks you to confirm and says if favorites are included; the second sends them to the Recycle Bin and tells you how much space was freed. Esc clears the selection.

**Mic button.** The **Mic** tile in the bar (or **M**) mutes or unmutes your microphone in OBS. It turns red when it's off.

**Your voice on its own track.** With `voice_track` on (default), recordings carry 3 audio tracks: everything, game only, and your mic only. Players play the first one, so clips sound normal; "Without my voice" uses the game-only one. To write extra tracks, OBS's Simple mode needs its quality preset instead of a fixed bitrate, so the buffer is capped by size (about 2.9 GB for 30 minutes at 1440p). In very detailed scenes it may hold a little less than 30 minutes. Set `"voice_track": false` to go back to the fixed 8000 Kbps (~1.8 GB).

**Storage warning.** When your captures pass `storage_warn_gb` (200 GB by default) or the drive has less than 20 GB free, you get a notice and an amber line in the bar. Nothing is deleted for you.

**Monitor and TV.** Capture Menu follows the game. The bar, the notifications and the viewer open on the screen your game is on. And when a game fills a screen (fullscreen or borderless), OBS is switched to record that screen within about 2 seconds, scaled to your recording resolution (a 4K TV fits the 1440p canvas). A notification says "Recording this screen · SAMSUNG". Alt-tabbing to Discord or a browser on the other screen doesn't move it. If you switch Windows to "TV only" (Win + P), the capture moves to the TV as well.

Keep in mind: the replay buffer holds whatever was being captured at the time. If you move the game from the monitor to the TV, the minutes before the move show the monitor.

---

## Always on, out of the way
Capture Menu starts with Windows and runs in the background. It has no window and no taskbar button. When the PC starts, a notice in the top-right says **Capture Menu is running** and how to open it. Its icon sits in the tray next to the clock: click it to open the bar, or right-click it for the gallery, Settings or Quit. On Windows 11 the icon is moved out of the hidden ^ area once; if you hide it again later, it stays hidden. OBS starts minimized to the tray too, without its first-run wizard.

Only one copy runs at a time: starting it again does nothing. If something needs attention at start-up (OBS not running, the shortcut taken by another app), that same notice says so instead of opening a window.

## Install
1. Download **`CaptureMenu.zip`** from the [latest release](https://github.com/Amjz03/capture-menu/releases/latest).
2. Right-click it → **Extract All** → **Extract**.
3. Open the extracted folder and double-click **`Setup.cmd`**. Leave the window open until it says **All set!** (a few minutes the first time).

That's it: press **Alt + C** in a game. You can delete the zip and the extracted folder afterwards.

> **"Windows protected your PC"?** Click **More info → Run anyway**. Windows shows this for any app that isn't from the Store.

Setup does everything else by itself:
- installs Python, OBS Studio and FFmpeg (skips what you already have)
- copies Capture Menu to `%LOCALAPPDATA%\Programs\CaptureMenu`, so it keeps working wherever you downloaded it
- turns on OBS's WebSocket with a random password and saves it to `config.json`
- adds Capture Menu to the Start menu and to Windows startup, and starts it
- checks that everything is ready and tells you exactly what to fix if something isn't

**Updating:** download the new zip and run its `Setup.cmd` the same way. Your settings are kept.

**Removing:** double-click **`Uninstall.cmd`** (in the extracted folder or in `%LOCALAPPDATA%\Programs\CaptureMenu`). Your captures, OBS and FFmpeg stay.

The first time it runs, Capture Menu **sets up OBS for your PC by itself** and restarts OBS once:
   - your main screen's resolution at **60 FPS**
   - the best encoder for your graphics card (RTX 40/50: **AV1**, older NVIDIA: HEVC, AMD/Intel: their hardware encoder)
   - a bitrate that suits the resolution (8000 Kbps AV1 at 1440p)
   - the **30-minute** replay buffer, MP4 recordings, and a **Display Capture** source

   You'll see "Setting up OBS · 2560×1440 · 60 FPS · NVENC AV1 8000 Kbps", then "OBS is ready". If OBS offers its Auto-Configuration Wizard, choose **No**.

It runs again only if something changes (a new main monitor or graphics card). Turn it off with `"obs_auto_setup": false`.

### Optional: a standalone .exe
After Setup, double-click **`build_exe.bat`** once. It builds `dist\CaptureMenu\CaptureMenu.exe`, which runs without Python. Run `Setup.cmd` in that folder once so it starts with Windows; it starts OBS by itself.

### Manual OBS setup (only if the automatic one can't)
1. **Sources → + → Display Capture.**
2. **Settings → Video:** Base and Output `2560x1440`, FPS `60`.
3. **Settings → Output** (Simple): Video Encoder `Hardware (NVENC, AV1)`, Video Bitrate `8000`, Recording Quality `Same as stream`, Recording Format `MP4`, **Enable Replay Buffer**, Maximum Replay Time `1800`.
4. **Tools → WebSocket Server Settings:** enable it, and copy the password into `obs_password` in `config.json`.

## Little touches, like the PS5

- **REC timer while you record.** A manual recording shows a small red **REC 12:34** in a corner of the game's screen, like the PS5. Clicks go through it, it never takes focus from the game, and it never shows up in your captures. Pick the corner, or turn it off, in Settings.
- **Double-press to save.** Press the hotkey or **Create** twice quickly: the last **30 seconds** are saved straight away, no menu. A single press opens the bar (after a short 0.35 s wait to tell the two apart). Change the length with `double_press_seconds`, or `0` to turn it off.
- **Sound.** A soft chime when a clip is saved, a shutter click for screenshots, a short tone when recording starts. Replace the files in `assets\sounds` with your own `.wav` if you like, or set `"sounds": false`.
- **Vibration.** The controller gives a short buzz when a capture is saved and when recording starts, only while you're using the controller. `"rumble": false` turns it off.

## How much RAM does it use?
OBS keeps the buffer in RAM. Usage ≈ bitrate × length. For 2K / 60 FPS:

| Buffer length | AV1 8000 Kbps (recommended) | HEVC 12000 Kbps (similar quality) |
|---|---|---|
| 10 min | ~0.6 GB | ~0.9 GB |
| 20 min | ~1.2 GB | ~1.8 GB |
| 30 min | ~1.8 GB | ~2.7 GB |

With **voice on its own track** (the default), OBS records at a constant quality instead of a fixed bitrate, so busy scenes can use more than the table shows. The Settings page shows an estimate for your choices. To use less RAM, pick a shorter buffer, a lower resolution or the **Light** quality there.

**Capture Menu itself** uses about 75 MB while it waits for the hotkey. The video player loads only when you open a clip, and it's let go a minute after you close the viewer. When nothing has been open for a while, its idle memory goes back to Windows. ffmpeg (thumbnails, trims, share copies) runs at below-normal priority, so it never takes CPU time from your game.

Clip files use AV1. VLC, Chrome and Discord play them out of the box; the Windows Photos app needs the free "AV1 Video Extension" from the Microsoft Store. Some phone apps (like WhatsApp) may not accept AV1. If you share clips there a lot, use HEVC instead.

## Settings page

Open it from the **Settings** tile at the end of the bar (or **,** on the keyboard, or the tray icon → Settings). Move with ↑ ↓ (or the d-pad), change a value with ← →, press **S** (Triangle / Y) to save, **Esc** (Circle / B) to cancel without saving. **Restore defaults** puts everything back to the original setup.

- **Recording:** resolution (Native, 1440p, 1080p, 720p), frame rate (30, 60, 120), quality (Light, Balanced, High, Max), video format (Auto, AV1, HEVC, H.264), replay buffer length (5 to 60 min), voice on its own track, follow the game's screen, recording indicator (top left, top right or off).
- **Controls:** keyboard shortcut (press Enter, then the new keys), controller button, press or hold, double-press to save, rumble, sounds.
- **Library:** captures folder, storage warning.
- **General:** start with Windows.

The bottom of the page shows how much RAM the replay buffer will use with what you picked. Saving restarts Capture Menu in a second. If you changed a recording setting, it also updates OBS and restarts it once. Video format never asks for more than your graphics card can do: AV1 on an older card falls back to HEVC.

The defaults are the original setup: native resolution, 60 FPS, Balanced (AV1 8000 Kbps at 1440p), a 30 min buffer, voice on its own track.

## Settings file (`config.json`)

The Settings page writes here. You can also edit it by hand while Capture Menu is closed.

| Setting | What it does |
|---|---|
| `resolution` / `fps` / `quality` / `video_codec` | Recording settings, as on the Settings page |
| `buffer_minutes` | Replay buffer length in minutes |
| `start_with_windows` | Start Capture Menu when you sign in |
| `hotkey` | The shortcut, e.g. `alt+c`, `ctrl+shift+f8` or `f9` |
| `durations_seconds` | The durations shown in the menu, in seconds |
| `clips_dir` | Where clips are saved. Leave it empty to use `Videos\Clips` |
| `game_names` | Fix a game's folder name if it's detected wrong (see below) |
| `controller_button` | Controller button (or combo) that opens the bar |
| `controller_hold_ms` | Hold time before it opens; `0` = on press |
| `capture_follow_game` | `true`: OBS records the screen your game is on. `false`: never touch the capture |
| `obs_display_source` | Name of the OBS Display Capture source to switch. Empty = the first one |
| `obs_auto_setup` | `true`: set OBS up for this PC on first run |
| `double_press_seconds` | Seconds saved by a double press; `0` = off |
| `sounds` / `rumble` | Sound cues / controller vibration on save |
| `storage_warn_gb` | Warn when captures use more than this; `0` = never |
| `voice_track` | Record your voice on its own audio track (see above) |

### Fixing a game's folder name
The name comes from the game's exe. If a game shows up with an odd name (like `Shipping` or a long window title), add it to `game_names` using the name of its exe file:

```json
"game_names": {
  "r5apex.exe": "Apex Legends",
  "FortniteClient-Win64-Shipping.exe": "Fortnite"
}
```

To find the exe name: open Task Manager while the game runs, right-click the game → **Go to details**.

## Notes
- **Using the NVIDIA app's Instant Replay too?** Turn it off (`Alt + Z` → Settings → Instant Replay) so you don't record twice.
- **2K needs a 2K monitor.** If your screen is 1080p, recording at 1440p won't add any detail. Use `1920x1080` and `10000 Kbps` instead.
- **Menu doesn't show over a game?** Set the game's display mode to **Borderless** or **Windowed Fullscreen**.
- The menu and notifications **don't appear in your recordings**.
- **Trimming** doesn't re-encode, so it's instant and lossless. The clip may start a second or two earlier than requested.

## Credits
- Button prompts: **PromptFont** by Shinmera (Yukari Hafner), available at https://shinmera.com/promptfont. SIL Open Font License 1.1 (`assets/PROMPTFONT-LICENSE.txt`). PlayStation and Xbox trademarks belong to their owners.
- Interface icons: **Lucide** (https://lucide.dev). ISC License (`assets/LUCIDE-LICENSE.txt`).
