"""Capture recording, library metadata and background operations."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from datetime import datetime
from obsws_python.error import OBSSDKRequestError
from pathlib import Path
import ctypes
import hashlib
import json
import os
import shutil
import threading
import time

from . import catalog, language, media, obs_client, preferences, runtime, windows


# ---------------------------------------------------------------- logic

class Controller(QtCore.QObject):
    toast = QtCore.Signal(str, str)        # text, kind: info / ok / error
    captured = QtCore.Signal(str, str)     # detail line, path of the new capture
    trimmed = QtCore.Signal(str)           # path of a freshly trimmed clip
    remixed = QtCore.Signal(str)           # path of a clip whose voice / game levels changed
    recording = QtCore.Signal(bool)        # manual recording started / stopped
    shared = QtCore.Signal(str, str)       # detail line, path of the share-ready copy
    copy_file = QtCore.Signal(str)         # put this file on the clipboard (main thread)
    storage = QtCore.Signal(dict)          # {"used_gb", "free_gb", "over", "low"}
    library_changed = QtCore.Signal()
    status = QtCore.Signal(dict)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.obs = obs_client.Obs(cfg)
        self.best_encoder: str | None = None     # found during OBS setup; Settings uses it
        self.screen_px: tuple[int, int] | None = None
        # A folder Windows won't let us use (Controlled folder access, a missing drive) never stops the
        # app: captures go to FALLBACK_CLIPS_DIR for now, and `blocked` says which folder was refused.
        # Nothing is written to config.json, so the chosen folder is used again once it's allowed.
        self.blocked: Path | None = None
        self.clips_dir = Path(cfg["clips_dir"])
        if not catalog.usable_folder(self.clips_dir):
            self.blocked, self.clips_dir = self.clips_dir, catalog.FALLBACK_CLIPS_DIR
            self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.shots_dir = Path(cfg["screenshots_dir"]) if cfg.get("screenshots_dir") else self.clips_dir
        if self.shots_dir != self.clips_dir and not catalog.usable_folder(self.shots_dir):
            self.blocked = self.blocked or self.shots_dir
            self.shots_dir = self.clips_dir
        # where captures live: the clips folder, plus the screenshots folder when it's somewhere else
        self.roots = [self.clips_dir] + ([self.shots_dir] if self.clips_dir not in
                                         (self.shots_dir, *self.shots_dir.parents) else [])
        self._busy = threading.Lock()
        self._healing = threading.Lock()       # one replay-buffer repair at a time
        self._heal_failed_at = -1e9
        self._gpu_restart_at = -1e9
        obs_client.BUFFER_DIR.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir = self.clips_dir / ".thumbs"
        self.thumbs_dir.mkdir(exist_ok=True)
        if runtime.IS_WINDOWS:
            for hide in (self.thumbs_dir, obs_client.BUFFER_DIR.parent):
                ctypes.windll.kernel32.SetFileAttributesW(str(hide), 0x02)  # hidden
        self.previews_dir = self.thumbs_dir / "previews"
        self.previews_dir.mkdir(exist_ok=True)
        self.recent: list[Path] = self._scan_recent()
        self._lengths_file = self.thumbs_dir / "lengths.json"
        self._lengths_lock = threading.Lock()
        self.lengths: dict[Path, float | None] = self._load_lengths()
        self._warned: set[str] = set()
        self.last_storage: dict = {}
        threading.Thread(target=self._remake_hdr_thumbs, daemon=True).start()

    def _remake_hdr_thumbs(self):
        """Until 0.0.16 OBS's HDR clips weren't taken for HDR, so their thumbnails and previews came
        out grey and washed out. Once per clips folder: make those again in normal colours."""
        done = self.thumbs_dir / "hdr-thumbs-v2"
        if done.exists():
            return
        try:
            fixed = False
            for p in self.all_captures():
                if media.is_hdr(p):
                    (self.thumbs_dir / (hashlib.md5(str(p).encode()).hexdigest() + ".jpg")).unlink(missing_ok=True)
                    self.preview_path(p).unlink(missing_ok=True)
                    media.make_thumb(p, self.thumbs_dir)
                    fixed = True
            done.touch()
            if fixed:
                runtime.safe_emit(self.library_changed)
        except Exception:
            runtime.log.exception("could not remake the HDR thumbnails")

    def preview_path(self, path: Path) -> Path:
        return self.previews_dir / (hashlib.md5(str(path).encode()).hexdigest() + ".mp4")

    def all_captures(self) -> list[Path]:
        files = {p for root in self.roots for p in root.rglob("*")   # a set: one folder may hold the other
                 if p.suffix.lower() in catalog.MEDIA_EXTS and not catalog.SKIP_DIRS & set(p.parts)}
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def _scan_recent(self, limit: int = 30) -> list[Path]:
        return self.all_captures()[:limit]

    # ---- favorites (kept in state.json, relative to the clips folder)
    def _fav_key(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.clips_dir))
        except ValueError:
            return str(path)

    def favorites(self) -> set[str]:
        return set(preferences.load_state().get("favorites", []))

    def is_favorite(self, path: Path) -> bool:
        return self._fav_key(path) in self.favorites()

    # ---- titles and notes (also in state.json; the file name never changes)
    def meta(self, path: Path) -> dict:
        return preferences.load_state().get("meta", {}).get(self._fav_key(path), {})

    def title_of(self, path: Path) -> str | None:
        return self.meta(path).get("title")

    def set_meta(self, path: Path, title: str, note: str):
        state = preferences.load_state()
        all_meta = state.setdefault("meta", {})
        entry = {k: v.strip() for k, v in (("title", title), ("note", note)) if v.strip()}
        if entry:
            all_meta[self._fav_key(path)] = entry
        else:
            all_meta.pop(self._fav_key(path), None)
        preferences.save_state(state)
        self.library_changed.emit()

    def toggle_favorite(self, path: Path) -> bool:
        state = preferences.load_state()
        favs = set(state.get("favorites", []))
        key = self._fav_key(path)
        favs.symmetric_difference_update({key})
        state["favorites"] = sorted(favs)
        preferences.save_state(state)
        self.library_changed.emit()
        return key in favs

    # ---- voice and game levels of one clip (the clip keeps its separate game and mic tracks)
    def mix_of(self, path: Path) -> tuple[int, int]:
        """Voice and game loudness of a clip in %, 100 = as recorded."""
        state, key = preferences.load_state(), self._fav_key(path)
        if key in state.get("levels", {}):
            m = state["levels"][key]
            return int(m.get("voice", 100)), int(m.get("game", 100))
        old = state.get("mix", {}).get(key)   # 0.0.2 kept dB; same loudness, nearest step
        if old:
            pct = lambda db: int(round(100 * 2 ** (db / 10) / media.LEVEL_STEP) * media.LEVEL_STEP)
            return pct(old.get("voice", 0)), pct(old.get("game", 0))
        return 100, 100

    def set_mix(self, path: Path, voice: int, game: int):
        self._bg(self._set_mix, path, voice, game)

    def _set_mix(self, path: Path, voice: int, game: int):
        tmp = path.with_name(path.name + ".part")   # not a capture, so the gallery never lists it
        try:
            media.remix_audio(path, voice, game, tmp)
            st = path.stat()
            os.replace(tmp, path)
            os.utime(path, (st.st_atime, st.st_mtime))     # same place in Recent and the gallery
            self.preview_path(path).unlink(missing_ok=True)   # a 720p preview copy has the old sound
            state = preferences.load_state()
            key = self._fav_key(path)
            state.get("mix", {}).pop(key, None)
            levels = state.setdefault("levels", {})
            if (voice, game) != (100, 100):
                levels[key] = {"voice": voice, "game": game}
            else:
                levels.pop(key, None)
            preferences.save_state(state)
            self.toast.emit(language.tr("Sound saved · your voice {voice} · game {game}",
                               voice=media.level_text(voice), game=media.level_text(game)), "ok")
        finally:
            tmp.unlink(missing_ok=True)
            self.remixed.emit(str(path))   # the viewer reloads the clip, saved or not

    # ---- storage warning (nothing is ever deleted automatically)
    def check_storage(self):
        def run():
            used = sum(catalog.folder_size_gb(root) for root in self.roots)
            free = shutil.disk_usage(self.clips_dir).free / 1024 ** 3
            limit = float(self.cfg.get("storage_warn_gb") or 0)
            info = {"used_gb": used, "free_gb": free, "limit_gb": limit,
                    "over": bool(limit) and used > limit, "low": free < 20}
            self.last_storage = info
            self.storage.emit(info)
            for flag, text in (("over", language.tr("Captures use {used} GB, over your {limit} GB limit"
                                           " · delete some in the gallery", used=f"{used:.0f}", limit=f"{limit:.0f}")),
                               ("low", language.tr("Only {free} GB free on this drive · delete some captures",
                                          free=f"{free:.0f}"))):
                if info[flag] and flag not in self._warned:
                    self._warned.add(flag)
                    self.toast.emit(text, "error")
                elif not info[flag]:
                    self._warned.discard(flag)
        threading.Thread(target=run, daemon=True).start()

    # ---- share & copy
    def share(self, src: Path, preset: str, without_voice: bool):
        self._bg(self._share, src, preset, without_voice, exclusive=False)

    def _share(self, src: Path, preset: str, without_voice: bool):
        info = media.SHARE_PRESETS[preset]
        folder = src.parent / "Shared"
        folder.mkdir(exist_ok=True)
        name = catalog.safe_filename(self.title_of(src) or "") or src.stem
        out = folder / f"{name}_{preset}{'_novoice' if without_voice else ''}.mp4"
        last = [-10]

        def progress(pct):
            if pct - last[0] >= 10:   # a notice every 10 %, not every frame
                last[0] = pct
                self.toast.emit(language.tr("Preparing for {target} · {pct}%", target=language.tr(info["label"]), pct=pct), "info")
        progress(0)
        size = media.export_for_share(src, out, info["size_mb"], without_voice, progress)
        self.copy_file.emit(str(out))
        media.make_thumb(out, self.thumbs_dir)
        voice = language.tr(" · without your voice") if without_voice else ""
        self.shared.emit(f"{language.tr(info['label'])} · {size:.1f} MB{voice}", str(out))

    def copy(self, path: Path):
        if media.is_hdr(path):   # Discord, WhatsApp and most players show HDR grey and washed out
            self.share(path, "phone", False)
            return
        self.copy_file.emit(str(path))
        self.toast.emit(language.tr("Copied · paste it with Ctrl+V · {name}", name=path.name), "ok")

    # ---- microphone
    def toggle_mic(self):
        def run():
            muted = self.obs.mic_muted()
            if muted is None:
                self.toast.emit(language.tr("No microphone in OBS · add one under Settings → Audio"), "error")
                return
            self.obs.set_mic_muted(not muted)
            self.toast.emit(language.tr("Mic off · your voice won't be recorded") if not muted else
                            language.tr("Mic on · your voice is recorded"), "info")
            self.refresh_status()
        self._bg(run, exclusive=False)

    def recent_items(self) -> list[Path]:
        self.recent = [p for p in self.recent if p.exists()]
        return self.recent

    def thumb(self, path: Path) -> Path | None:
        t = self.thumbs_dir / (hashlib.md5(str(path).encode()).hexdigest() + ".jpg")
        return t if t.exists() else None

    def _load_lengths(self) -> dict:
        """Clip lengths measured before, still valid if the file hasn't changed since."""
        try:
            saved = json.loads(self._lengths_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        lengths = {}
        for path, (mtime, seconds) in saved.items():
            p = Path(path)
            try:
                if p.stat().st_mtime == mtime:
                    lengths[p] = seconds
            except OSError:
                pass
        return lengths

    def save_lengths(self):
        with self._lengths_lock:
            data = {}
            for p, secs in list(self.lengths.items()):
                try:
                    data[str(p)] = [p.stat().st_mtime, secs]
                except OSError:
                    pass
            self._lengths_file.write_text(json.dumps(data), encoding="utf-8")

    def length_of(self, path: Path) -> float | None:
        """Cached clip length in seconds (None until known)."""
        return self.lengths.get(path)

    def _done(self, text: str, path: Path):
        media.make_thumb(path, self.thumbs_dir)
        if path.suffix.lower() != ".png":
            self.lengths[path] = media.media_duration(path)
            self.save_lengths()
        self.recent.insert(0, path)
        self.captured.emit(text, str(path))
        self.check_storage()

    def delete(self, path: Path) -> bool:
        """Moves a capture to the Recycle Bin."""
        for _ in range(3):   # a file just written can be locked for a moment (antivirus, search indexer)
            try:
                moved = QtCore.QFile.moveToTrash(str(path))
            except Exception:
                runtime.log.exception("could not recycle %s", path)
                return False
            if isinstance(moved, tuple):
                moved = moved[0]
            if moved or not path.exists():
                break
            time.sleep(0.3)
        if not moved:
            return False  # never turn a failed recycle operation into permanent deletion
        try:
            if self.is_favorite(path):
                self.toggle_favorite(path)
            if self.meta(path):
                self.set_meta(path, "", "")
            if t := self.thumb(path):
                t.unlink(missing_ok=True)
            self.preview_path(path).unlink(missing_ok=True)
        except Exception:
            runtime.log.exception("capture recycled, but could not clean up metadata/cache for %s", path)
        self.recent = [p for p in self.recent if p != path]
        return True

    def delete_many(self, paths: list[Path]) -> tuple[int, int]:
        """Recycle Bin for several captures; returns (how many, bytes moved)."""
        done = freed = 0
        for p in paths:
            size = catalog.file_size(p)
            if self.delete(p):
                done, freed = done + 1, freed + size
        self.check_storage()
        return done, freed

    def trim(self, src: Path, start_ms: int, end_ms: int, replace: bool):
        self._bg(self._trim, src, start_ms, end_ms, replace)

    def _trim(self, src: Path, start_ms: int, end_ms: int, replace: bool):
        out = src.parent / f"Clip_{self._stamp()}_trim{src.suffix}"
        mode = media.trim_clip(src, start_ms, end_ms, out)
        length = language.clock((end_ms - start_ms))
        if self.meta(src):
            m = self.meta(src)
            self.set_meta(out, m.get("title", ""), m.get("note", ""))
        kept_original = replace and not self.delete(src)
        note = "" if mode == "precise" else language.tr(" · fast cut")
        self._done(language.tr("Length {length}", length=length) + note, out)
        self.trimmed.emit(str(out))
        if kept_original:
            self.toast.emit(language.tr("Trim saved, but the original could not be moved to the Recycle Bin"), "error")

    @staticmethod
    def reveal(path: Path):
        if runtime.IS_WINDOWS:   # written out by hand: Explorer needs /select,"path"; "/select,path" opens Documents
            windows.launch_outside(f'explorer /select,"{path}"')
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path.parent)))

    @staticmethod
    def open_external(path: Path):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    def folder_for(self, game: str, root: Path | None = None) -> Path:
        folder = (root or self.clips_dir) / game
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    # OBS calls and trimming run in the background so the menu never freezes
    def _bg(self, fn, *args, exclusive: bool = True):
        def run():
            if exclusive and not self._busy.acquire(blocking=False):
                self.toast.emit(language.tr("Hang on, still saving the last clip…"), "info")
                return
            try:
                fn(*args)
            except obs_client.ObsOffline:
                self.toast.emit(language.tr("Can't reach OBS · make sure it's running, then try again"), "error")
            except Exception as e:
                runtime.log.exception("action failed")
                self.toast.emit(language.tr("Something went wrong: {error}", error=e), "error")
            finally:
                if exclusive:
                    self._busy.release()
        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _stamp() -> str:
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # ---- status
    def refresh_status(self):
        def run():
            try:
                rec = self._recording()
                active = self.obs.buffer_active()
                keep = int(self.cfg["buffer_minutes"]) * 60
                held = self._last_run(self._segments()) if active else []
                st = {"online": True, "buffer": active, "buffer_seconds": keep,
                      "buffered_ms": int(min(time.time() - held[0][1], keep) * 1000) if held else 0,
                      "recording": bool(rec), "record_ms": int((time.time() - rec["since"]) * 1000) if rec else 0,
                      "mic_muted": self.obs.mic_muted()}
            except Exception:
                st = {"online": False}
            self.status.emit(st)
        threading.Thread(target=run, daemon=True).start()

    def apply_mic(self):
        """The microphone picked in Settings. Only once it was picked here, so a microphone chosen
        in OBS itself is left alone until then."""
        wanted = self.cfg.get("mic_device", "default")
        state = preferences.load_state()
        if not state.get("mic_picked") or state.get("mic_device") == wanted:
            return
        if self.obs.mic_devices() is None:
            return      # no microphone in OBS (yet): try again next start
        if self.obs.set_mic_device(wanted):
            runtime.log.info("microphone: %s", wanted)
        state["mic_device"] = wanted
        preferences.save_state(state)

    def auto_setup(self, width: int, height: int):
        """First run (or a new monitor/GPU): configure OBS for this PC, then restart it once."""
        encoder = obs_client.pick_encoder(obs_client.gpu_names(), preferences.load_state().get("failed_encoders", []))
        self.best_encoder = encoder
        version = self.obs.raw("GetVersion").get("obsVersion", "0")
        # OBS records at the main screen's size, so that screen's HDR decides (a game on another
        # screen is converted by OBS either way)
        hdr = self.cfg.get("hdr", "auto") == "auto" and windows.windows_hdr()
        plan = obs_client.obs_plan(self.cfg, width, height, encoder, version, hdr,
                        windows.sdr_white() if windows.windows_hdr() else None)
        runtime.log.info("OBS plan: %s (Windows HDR %s)", plan["summary"], "on" if hdr else "off")
        # (OBS records into BUFFER_DIR in AppData, which Controlled folder access doesn't block)
        done = plan["summary"] + " · on disk"    # until 0.0.34 the last minutes were in RAM: set up again
        state = preferences.load_state()
        if state.get("obs_setup") == done:
            self.obs.set_colours(plan["force_sdr"], plan["vivid"])   # live: keeps the colours up to date
            return
        if self._recording():
            return   # never interrupt a recording; try again next start
        self.toast.emit(language.tr("Setting up OBS · {summary}", summary=plan["summary"]), "info")
        self.obs.stop_ram_buffer()
        changed = self.obs.apply_plan(plan)
        if changed:
            self.restart_obs()     # OBS loads the new settings when it starts
        # heal_buffer gets the buffer running whatever went wrong (a restart that didn't happen, an
        # encoder this PC can't run) and says so itself when it can't
        if self.heal_buffer():
            self.toast.emit(language.tr("OBS is ready · {summary}", summary=plan["summary"]), "ok")
        state = preferences.load_state()       # heal_buffer may have noted a failed encoder
        state["obs_setup"] = done
        preferences.save_state(state)

    def restart_obs(self) -> bool:
        """Closes OBS the polite way (like clicking ✕) and starts it again with the buffer on.
        True once the buffer runs. If OBS won't close (an error box it's waiting on), it's ended."""
        path = obs_client.obs_exe_path() or obs_client.find_obs_exe()
        if not path:
            return False
        if obs_client.obs_running():
            try:
                self.obs.stop_buffer()    # or OBS asks whether to stop recording before it closes
            except Exception:
                pass
            media.run_quiet(["taskkill", "/IM", "obs64.exe"])
            for _ in range(80):
                time.sleep(0.25)
                if not obs_client.obs_running():
                    break
            else:
                runtime.log.warning("OBS didn't close; ending it")
                media.run_quiet(["taskkill", "/F", "/IM", "obs64.exe"])
                time.sleep(2)
                if obs_client.obs_running():
                    return False
        obs_client.launch_obs(path)
        if not self._wait_for_obs():
            return False
        try:
            return self.obs.start_buffer()
        except obs_client.BufferDisabled:
            return False

    def _wait_for_obs(self) -> bool:
        """OBS takes a few seconds to answer once started (longer at sign-in)."""
        for _ in range(60):
            time.sleep(0.5)
            try:
                self.obs.call("get_version")
                return True
            except Exception:
                continue
        return False

    # ---- OBS records the whole time Capture Menu runs, whatever happens to it
    HEAL_PAUSE = 120      # after a repair that didn't work, the background check waits this long

    def heal_buffer(self) -> bool:
        """Gets OBS recording the last minutes, whatever it takes, so a new PC needs nothing done by
        hand: 1. start it; 2. if OBS isn't in Simple output mode, switch it and restart OBS;
        3. restart OBS as it is (a graphics driver that was updated or reset under it);
        4. if it still won't start, the encoder can't run on this PC: step down (the card's H.264,
        then the CPU's x264) and remember it, so setup doesn't pick it again. Never restarts OBS
        while it streams. A manual recording survives a restart (its files stay; the gap is a
        moment). True once it runs. Says once when it can't, not at every try."""
        if not self._healing.acquire(blocking=False):
            return False                      # already being repaired
        try:
            try:
                if self.obs.start_buffer():
                    self._heal_failed_at = -1e9
                    return True
                disabled = False
            except obs_client.BufferDisabled:
                disabled = True
            if self.obs.streaming():
                runtime.log.warning("the last minutes won't record, but OBS is streaming: not restarting it")
                return self._heal_failed()
            runtime.log.warning("the last minutes won't record: %s", "OBS isn't in Simple output mode" if disabled
                                else "the recording didn't start")
            if disabled:
                self.obs.set_profile([("Output", "Mode", "Simple"), ("SimpleOutput", "RecRB", "false")])
            if self.restart_obs():
                self._heal_failed_at = -1e9
                if disabled:
                    self.toast.emit(language.tr("Turned on the OBS replay buffer"), "ok")
                return True
            encoder = self.obs.profile_value("SimpleOutput", "RecEncoder") or self.best_encoder or "x264"
            for fallback in obs_client.fallback_encoders(encoder):
                self._note_failed_encoder(encoder)
                runtime.log.warning("encoder %s didn't start; trying %s", encoder, fallback)
                video = self.obs.raw("GetVideoSettings")
                bitrate = obs_client.pick_bitrate(fallback, video.get("outputWidth", 1920), video.get("outputHeight", 1080),
                                                  video.get("fpsNumerator", 60), self.cfg.get("quality", "balanced"))
                self.obs.set_profile([("SimpleOutput", "StreamEncoder", fallback), ("SimpleOutput", "RecEncoder", fallback),
                                      ("SimpleOutput", "VBitrate", str(bitrate))])
                if self.restart_obs():
                    self.best_encoder = fallback
                    self._heal_failed_at = -1e9
                    self.toast.emit(language.tr("Your graphics card couldn't record, so OBS now uses {encoder}",
                                                encoder=fallback.replace("_", " ").upper()), "ok")
                    return True
                encoder = fallback
            return self._heal_failed()
        finally:
            self._healing.release()

    def _heal_failed(self) -> bool:
        if self._heal_failed_at < 0:          # the first try that failed: say it once
            self.toast.emit(language.tr("OBS can't start recording · open OBS to see why"), "error")
        self._heal_failed_at = time.monotonic()
        return False

    def _note_failed_encoder(self, encoder: str):
        state = preferences.load_state()
        failed = state.get("failed_encoders", [])
        if encoder not in failed and encoder != "x264":
            state["failed_encoders"] = failed + [encoder]
            preferences.save_state(state)

    def _watch_buffer(self):
        """Every minute, in the background, while Capture Menu runs: OBS is running (started again
        if it was closed or crashed), really recording (restarted if the graphics driver reset under
        it or the recording stopped growing) and recording the last minutes (heal_buffer). Old
        minutes are deleted, and a drive running out of room is said once. After a repair that
        failed, HEAL_PAUSE goes by before the next."""
        runtime.touch_alive()
        if self._healing.locked():
            return

        def run():
            try:
                self._prune()
                self._check_buffer_drive()
                if time.monotonic() - self._heal_failed_at < self.HEAL_PAUSE:
                    return
                if runtime.IS_WINDOWS and not obs_client.obs_running():
                    runtime.log.warning("OBS isn't running; starting it")
                    if not obs_client.start_obs() or not self._wait_for_obs():
                        return
                if why := self._obs_stuck():
                    self._restart_stuck(why)
                if not self.obs.buffer_active():
                    self.heal_buffer()
            except obs_client.ObsOffline:
                pass
            except Exception:
                runtime.log.exception("replay buffer check failed")
        threading.Thread(target=run, daemon=True).start()

    def _obs_stuck(self) -> str | None:
        """Why OBS records nothing though it says it records: the graphics driver reset under it, or
        the recording stopped growing (an encoder that hung). None when it's fine."""
        if self._obs_lost_gpu():
            return "gpu"
        written = self.obs.recorded_bytes()
        before, self._last_written = getattr(self, "_last_written", None), written
        return "frozen" if written is not None and written == before else None

    def _restart_stuck(self, why: str):
        if self.obs.streaming():
            runtime.log.warning("OBS records nothing (%s), but it's streaming: not restarting it", why)
            return
        if time.monotonic() - self._gpu_restart_at < self.HEAL_PAUSE or not self._healing.acquire(blocking=False):
            return
        try:
            self._gpu_restart_at = time.monotonic()
            self._last_written = None
            runtime.log.warning("OBS records nothing (%s); restarting it", why)
            if self.restart_obs():
                self.toast.emit(language.tr("OBS stopped recording after a graphics driver reset, so I restarted it")
                                if why == "gpu" else
                                language.tr("OBS stopped recording, so I restarted it"), "info")
        finally:
            self._healing.release()

    # DXGI device removed / hung / reset: OBS logs one of these every few seconds once the graphics
    # driver reset under it (a driver crash or update), and records nothing until it restarts
    GPU_LOST = (b"0x887A0005", b"0x887A0006", b"0x887A0007")

    @classmethod
    def _obs_lost_gpu(cls) -> bool:
        logs = Path(os.environ.get("APPDATA", str(Path.home()))) / "obs-studio" / "logs"
        try:
            log = max(logs.glob("*.txt"), key=lambda p: p.stat().st_mtime)
            with open(log, "rb") as f:
                f.seek(max(0, log.stat().st_size - 4096))
                tail = f.read()
        except (OSError, ValueError):
            return False
        return any(code in tail for code in cls.GPU_LOST)

    BUFFER_FREE_GB = 5        # OBS stops recording when the drive is full

    def _check_buffer_drive(self):
        try:
            free = shutil.disk_usage(obs_client.BUFFER_DIR).free / 1024 ** 3
        except OSError:
            return
        if free < self.BUFFER_FREE_GB and "buffer_drive" not in self._warned:
            self._warned.add("buffer_drive")
            self.toast.emit(language.tr("Only {free} GB free on {drive} · Capture Menu needs room there for the "
                                        "last minutes", free=f"{free:.0f}", drive=obs_client.BUFFER_DIR.drive), "error")
        elif free >= self.BUFFER_FREE_GB:
            self._warned.discard("buffer_drive")

    # ---- the last minutes, on disk: the files OBS splits its recording into (obs_client.BUFFER_DIR)
    SEGMENT_EXTS = {".mp4", ".mkv", ".mov", ".flv", ".ts"}
    GAP = 5      # seconds between two files: OBS stopped in between (a restart), so they don't join on

    @classmethod
    def _segments(cls) -> list[tuple[Path, float, float]]:
        """(file, started, ended) in wall-clock time, oldest first; the last one may be in progress."""
        segs = []
        try:
            for p in obs_client.BUFFER_DIR.iterdir():
                if p.suffix.lower() in cls.SEGMENT_EXTS:
                    st = p.stat()
                    segs.append((p, getattr(st, "st_birthtime", st.st_ctime), st.st_mtime))
        except OSError:
            pass
        return sorted(segs, key=lambda s: s[1])

    @classmethod
    def _last_run(cls, segs: list) -> list:
        """The files since OBS last started recording."""
        for i in range(len(segs) - 1, 0, -1):
            if segs[i][1] - segs[i - 1][2] > cls.GAP:
                return segs[i:]
        return segs

    @staticmethod
    def _since(segs: list, since: float | None) -> tuple[list[Path], float]:
        """The files that hold everything after `since` (None: all), and how far into the first that is."""
        keep = [s for s in segs if since is None or s[2] > since]
        return [s[0] for s in keep], max(0.0, since - keep[0][1]) if keep and since else 0.0

    def _finished_segments(self) -> list:
        """Has OBS close the file it's writing (it goes on in a new one at the next keyframe), so
        everything up to now can be read. Returns the finished files."""
        asked = time.time()
        self.obs.split()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            segs = self._segments()
            if len(segs) > 1 and segs[-1][1] >= asked - 0.5:
                return segs[:-1]
            time.sleep(0.2)
        raise TimeoutError("OBS didn't start a new file")

    def _prune(self):
        """Deletes the files older than the longest clip (and than a recording that's running)."""
        keep_from = time.time() - int(self.cfg["buffer_minutes"]) * 60
        if rec := self._recording():
            keep_from = min(keep_from, rec["since"])
        for p, _, ended in self._segments()[:-1]:
            if ended < keep_from:
                try:
                    p.unlink()
                except OSError:
                    pass

    @staticmethod
    def _recording() -> dict | None:
        """The manual recording running: {"since": wall-clock time, "game"} (kept across restarts)."""
        return preferences.load_state().get("recording")

    def start_following(self):
        """Every 2 s: make sure OBS records the screen picked in Settings, or else the monitor a
        fullscreen game is on."""
        self._following = threading.Lock()
        self._follow_timer = QtCore.QTimer(self, interval=2000, timeout=self._follow_tick)
        self._follow_timer.start()

    def _follow_tick(self):
        screen = windows.chosen_screen(self.cfg.get("capture_screen", "follow"))
        if screen is not None:     # a screen picked in Settings: always that one
            info = {"rect": windows.screen_px_rect(screen), "fullscreen": True}
        else:
            info = windows.foreground_screen()
            if not info or info["own"]:
                return
        # ask OBS only when the game's screen changed, or every 10 s to catch a vanished monitor
        key = (info["rect"], info["fullscreen"])
        now = time.monotonic()
        if key == getattr(self, "_follow_last", None) and now - getattr(self, "_follow_at", 0) < 10:
            return
        if not self._following.acquire(blocking=False):
            return
        self._follow_last, self._follow_at = key, now

        def run():
            try:
                # a fullscreen game moves the capture; anything else only fixes a capture
                # that points at a monitor that's gone (e.g. switched to "TV only")
                name = self.obs.capture_monitor(info["rect"], only_if_missing=not info["fullscreen"])
                if name:
                    runtime.log.info("capture moved to %s", name)
                    self.toast.emit(language.tr("Recording this screen · {name}", name=name), "info")
            except obs_client.ObsOffline:
                pass
            except OBSSDKRequestError as e:
                if e.code != 207:    # 207: OBS is still starting; the next check (2 s later) works
                    runtime.log.exception("could not follow the game's screen")
            except Exception:
                runtime.log.exception("could not follow the game's screen")
            finally:
                self._following.release()
        threading.Thread(target=run, daemon=True).start()

    def startup(self, screen_size: tuple[int, int] | None = None):
        self.screen_px = screen_size

        def run():
            runtime.touch_alive()
            if runtime.IS_WINDOWS and not obs_client.obs_running() and obs_client.start_obs():
                self._wait_for_obs()
            self.check_storage()
            for p in self.recent[:8]:  # thumbnails and lengths for the Recent row
                media.make_thumb(p, self.thumbs_dir)
                if p.suffix.lower() != ".png" and p not in self.lengths:
                    self.lengths[p] = media.media_duration(p)
            self.save_lengths()
            try:
                self.apply_mic()
                self.obs.set_mic_muted(not self.cfg.get("mic_on", True))   # Settings → Record your microphone
            except obs_client.ObsOffline:
                pass
            except Exception:
                runtime.log.exception("couldn't pick the microphone in OBS")
            if screen_size and self.cfg.get("obs_auto_setup", True):
                try:
                    self.auto_setup(*screen_size)
                except obs_client.ObsOffline:
                    pass
                except Exception:
                    runtime.log.exception("OBS auto setup failed")
                    self.toast.emit(language.tr("Couldn't set up OBS automatically · see README for the manual steps"),
                                    "error")
            try:
                self._prune()
                if not self.obs.buffer_active():
                    self.heal_buffer()      # started at every start: it says so only when it can't
            except obs_client.ObsOffline:
                self.toast.emit(language.tr("OBS isn't running. Start it to use Capture Menu"), "error")
            except Exception:
                runtime.log.exception("couldn't start the replay buffer")
                self.toast.emit(language.tr("OBS can't start recording · open OBS to see why"), "error")
            self.refresh_status()   # e.g. a recording still running after a restart
            runtime.log.info("start-up done")
        threading.Thread(target=run, daemon=True).start()
        self._buffer_watch = QtCore.QTimer(self, interval=60_000, timeout=self._watch_buffer)
        self._buffer_watch.start()

    # ---- save what just happened
    def save_clip(self, seconds: int | None, game: str = windows.DESKTOP):
        self._bg(self._save_clip, seconds, game)

    def _save_clip(self, seconds: int | None, game: str):
        if not self.obs.buffer_active():
            if self.heal_buffer():
                self.toast.emit(language.tr("The replay buffer was off, so I turned it on. "
                                   "Clips are collected from now on"), "error")
            return      # heal_buffer said why when it couldn't
        self.toast.emit(language.tr("Saving…"), "info")
        segs = self._last_run(self._finished_segments())
        files, inpoint = self._since(segs, None if seconds is None else segs[-1][2] - seconds)
        suffix = "all" if seconds is None else f"{seconds}s"
        out = self.folder_for(game) / f"Clip_{self._stamp()}_{suffix}{files[0].suffix}"
        media.join(files, inpoint, out)
        length = media.media_duration(out) or float(seconds or 0)
        detail = (language.tr("Everything · {length}", length=language.clock(int(length * 1000)))
                  if seconds is None or length < seconds - 1
                  else language.tr("Last {length}", length=language.duration_label(seconds)))
        self._done(detail, out)

    # ---- manual recording
    def toggle_record(self, game: str = windows.DESKTOP):
        self._bg(self._toggle_record, game, exclusive=False)

    def _toggle_record(self, game: str):
        """Recording uses the same files as the last minutes: Start notes the time, Stop joins
        everything since then (kept until then)."""
        rec = self._recording()
        if not rec:
            if not self.obs.buffer_active() and not self.heal_buffer():
                return      # heal_buffer said why
            preferences.save_state(preferences.load_state() | {"recording": {"since": time.time(), "game": game}})
            self.recording.emit(True)
            self.toast.emit(language.tr("Recording started · open the menu and choose Stop to finish"), "rec")
            return
        segs = self._finished_segments()
        files, inpoint = self._since(segs, rec["since"])
        dest = self.folder_for(rec.get("game") or game) / f"Recording_{self._stamp()}{files[0].suffix}"
        media.join(files, inpoint, dest)
        state = preferences.load_state()
        state.pop("recording", None)
        preferences.save_state(state)
        self.recording.emit(False)
        length = media.media_duration(dest) or 0
        self._done(language.tr("Length {length}", length=language.clock(int(length * 1000))), dest)

    # ---- screenshot
    def screenshot(self, game: str = windows.DESKTOP):
        self._bg(self._screenshot, game, exclusive=False)

    def _screenshot(self, game: str):
        path = self.folder_for(game, self.shots_dir) / f"Screenshot_{self._stamp()}.png"
        self.obs.screenshot(path)
        media.wait_until_written(path, timeout=5)
        self._done("", path)

    def open_folder(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.clips_dir)))
