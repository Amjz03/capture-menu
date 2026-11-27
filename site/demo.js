// The try-it demo: Capture Menu's Create bar, rebuilt from the app's own sizes, icons (Lucide), button
// prompts (PromptFont) and wording (assets/lang/ar.json), on a 1920 × 1080 screen scaled to fit.
// Everything the bar does works: the duration picker, screenshot, record / stop, mic, the recent
// captures, All captures, Settings, the notices, the double press, keys, mouse and controllers.

const DEMO = (() => {
  const W = {
    en: {
      game: "Call of Duty", keeping: "Keeping the last 30 min", recording: "Recording",
      save: "Save recent", save_hint: "last 30 min", shot: "Screenshot", rec: "Record", stop: "Stop  {t}",
      mic_on: "Mic on", mic_off: "Mic off", all: "All captures", settings: "Settings",
      move: "Move", select: "Select", instantly: "Save instantly", trim_latest: "Trim latest", close: "Close",
      view_latest: "View latest", choose: "Choose", save_k: "Save", pick: "Pick", back: "Back",
      caption: "Save recent gameplay", full: "Everything", last_s: "{n} sec", last_m: "{n} min", again: "Click again to save", on: "On", off: "Off", mic: "Mic", save_clip: "Save clip",
      clip_saved: "Clip saved", shot_saved: "Screenshot saved", rec_saved: "Recording saved",
      last: "Last {l}", length: "Length {l}", everything: "Everything · {l}",
      sec: "{n} sec", min: "{n} min", one_min: "1 minute",
      to_view: "{open}&nbsp; then &nbsp;{view}&nbsp; to view", trim: "Trim", view: "View", share: "Share", trimmed: "Trimmed clip saved",
      rec_started: "Recording started · open the menu and choose Stop to finish",
      mic_msg_off: "Mic off · your voice won't be recorded", mic_msg_on: "Mic on · your voice is recorded",
      clip: "Clip", clip_len: "Clip · {l}", screenshot: "Screenshot", recording_kind: "Recording",
      just_now: "just now", min_ago: "{n} min ago", mb: "MB", gb: "GB",
    },
    ar: {
      game: "Call of Duty", keeping: "يحتفظ بآخر 30 دقيقة", recording: "تسجيل",
      save: "حفظ آخر لقطة", save_hint: "آخر 30 دقيقة", shot: "لقطة شاشة", rec: "تسجيل", stop: "إيقاف  {t}",
      mic_on: "المايك يعمل", mic_off: "المايك مغلق", all: "كل المقاطع واللقطات", settings: "الإعدادات",
      move: "تنقّل", select: "اختيار", instantly: "حفظ فوري", trim_latest: "قص الأخير", close: "إغلاق",
      view_latest: "عرض الأخير", choose: "اختيار", save_k: "حفظ", pick: "اختيار سريع", back: "رجوع",
      caption: "حفظ اللعب الأخير", full: "كل اللعب المسجّل", last_s: "{n} ثانية", last_m: "{n} دقيقة", again: "اضغط مرة ثانية للحفظ", on: "يعمل", off: "مغلق", mic: "المايك", save_clip: "حفظ المقطع",
      clip_saved: "حُفظ المقطع", shot_saved: "حُفظت لقطة الشاشة", rec_saved: "حُفظ التسجيل",
      last: "آخر {l}", length: "المدة {l}", everything: "كل اللعب المسجّل · {l}",
      sec: "{n} ثانية", min: "{n} دقيقة", one_min: "دقيقة واحدة",
      to_view: "{open}&nbsp; ثم &nbsp;{view}&nbsp; للعرض", trim: "قص", view: "عرض", share: "مشاركة", trimmed: "حُفظ المقطع المقصوص",
      rec_started: "بدأ التسجيل · افتح القائمة واختر «إيقاف» لإنهائه",
      mic_msg_off: "المايك مغلق · لن يُسجَّل صوتك", mic_msg_on: "المايك يعمل · صوتك يُسجَّل",
      clip: "مقطع", clip_len: "مقطع · {l}", screenshot: "لقطة شاشة", recording_kind: "تسجيل",
      just_now: "الآن", min_ago: "قبل {n} د", mb: "ميجابايت", gb: "جيجابايت",
    },
  };
  const fill = (s, f) => s.replace(/\{(\w+)\}/g, (_, k) => f[k]);

  // Lucide icons, as the app ships them (assets/icons)
  const ICON = {
    rewind: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    camera: '<path d="M13.997 4a2 2 0 0 1 1.76 1.05l.486.9A2 2 0 0 0 18.003 7H20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1.997a2 2 0 0 0 1.759-1.048l.489-.904A2 2 0 0 1 10.004 4z"/><circle cx="12" cy="13" r="3"/>',
    record: '<circle cx="12" cy="12" r="1"/><circle cx="12" cy="12" r="10"/>',
    stop: '<circle cx="12" cy="12" r="10"/><rect x="9" y="9" width="6" height="6" rx="1"/>',
    mic: '<path d="M12 19v3"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><rect x="9" y="2" width="6" height="13" rx="3"/>',
    "mic-off": '<path d="M12 19v3"/><path d="M15 9.34V5a3 3 0 0 0-5.68-1.33"/><path d="M16.95 16.95A7 7 0 0 1 5 12v-2"/><path d="M18.89 13.23A7 7 0 0 0 19 12v-2"/><path d="m2 2 20 20"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12"/>',
    gallery: '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
    settings: '<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"/><circle cx="12" cy="12" r="3"/>',
    left: '<path d="m15 18-6-6 6-6"/>', right: '<path d="m9 18 6-6-6-6"/>',
    scissors: '<circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/>',
    play: '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>',
    share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/>',
    "gamepad": '<line x1="6" x2="10" y1="11" y2="11"/><line x1="8" x2="8" y1="9" y2="13"/><line x1="15" x2="15.01" y1="12" y2="12"/><line x1="18" x2="18.01" y1="10" y2="10"/><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z"/>',
    "file-video": '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M15.033 13.44a.647.647 0 0 1 0 1.12l-4.065 2.352a.645.645 0 0 1-.968-.56v-4.704a.645.645 0 0 1 .967-.56z"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "video": '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
    "star": '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>',
    "search": '<path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/>',
    "select": '<path d="M21 10.656V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12.344"/><path d="m9 11 3 3L22 4"/>',
    "back5": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "monitor": '<rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "phone": '<rect width="14" height="20" x="5" y="2" rx="2" ry="2"/><path d="M12 18h.01"/>',
    "export": '<path d="M12 3v12"/><path d="m17 8-5-5-5 5"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>',
    "trash": '<path d="M10 11v6"/><path d="M14 11v6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    "audio": '<path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/>',
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "drive": '<path d="M10 16h.01"/><path d="M2.212 11.577a2 2 0 0 0-.212.896V18a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5.527a2 2 0 0 0-.212-.896L18.55 5.11A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><path d="M21.946 12.013H2.054"/><path d="M6 16h.01"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    image: '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
  };
  const svg = (name, px) => `<svg width="${px}" height="${px}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[name]}</svg>`;

  // PromptFont glyphs (assets/promptfont-glyphs.json) for each input
  const G = {
    keyboard: { left: "⏴", right: "⏵", enter: "␮", 1: "１", 8: "８", t: "Ｔ", esc: "␯", alt: "␨", c: "Ｃ", v: "Ｖ" },
    playstation: { lr: "↢", a: "⇣", b: "⇢", x: "⇠", y: "⇡", r1: "↱", create: "∆" },
    xbox: { lr: "≾", a: "⇓", b: "⇒", x: "⇐", y: "⇑", r1: "↙", create: "⇺" },
  };
  const g = (ch) => `<span class="g">${ch}</span>`;

  // shortest to longest, then everything that's kept (as the app)
  const OPTIONS = [15, 30, 60, 180, 300, 900, 1800, null];
  const MB = 15.2 * 1024 * 1024;                 // what a second of 1440p / 120 weighs, about

  const $ = (id) => document.getElementById(id);
  const stage = $("stage"), pc = $("pc"), menu = $("cm-menu");
  let lang = "en", t = W.en, mode = "keyboard";
  const now = Date.now();
  // the library the bar starts with, newest first: the bar shows every game's latest captures
  const RD = "Red Dead Redemption 2";
  let caps = [
    { kind: "shot", img: "assets/app/thumb3.jpg", at: now - 6 * 60e3 },
    { kind: "clip", secs: 30, img: "assets/app/thumb1.jpg", at: now - 38 * 60e3, game: RD },
    { kind: "clip", secs: 60, img: "assets/app/thumb2.jpg", at: now - 40 * 60e3, game: RD },
  ];
  let open = false, picking = false, focus = 0, lent = null, lastChoice = 2, page = null, armed = null;
  let recStart = null, micOn = true, recTimer = null, toastTimer = null, toastHtml = null;

  // ---------------------------------------------------------------- words
  const clock = (ms) => { const s = Math.floor(ms / 1000); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
  const shortClock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const duration = (s, short) => s < 60 ? fill(t.sec, { n: s }) : (short || s !== 60 ? fill(t.min, { n: s / 60 }) : t.one_min);
  const chipLabel = (s) => s === null ? t.full : s < 60 ? fill(t.last_s, { n: s }) : fill(t.last_m, { n: s / 60 });
  const kindOf = (c) => c.kind === "shot" ? t.screenshot : c.kind === "rec" ? t.recording_kind : fill(t.clip_len, { l: duration(c.secs, true) });
  const ago = (c) => { const m = Math.floor((Date.now() - c.at) / 60e3); return m < 1 ? t.just_now : fill(t.min_ago, { n: m }); };
  const size = (c) => { const b = c.kind === "shot" ? 4.7e6 : c.secs * MB; return b >= 1024 ** 3 ? `${(b / 1024 ** 3).toFixed(1)} ${t.gb}` : `${Math.round(b / 1024 ** 2)} ${t.mb}`; };

  // ---------------------------------------------------------------- the bar
  const thumbsShown = () => caps.slice(0, 5);     // what fits beside the cards on a 1920 screen
  function items() {
    return ["save", "shot", "rec", "mic", ...thumbsShown().map((_, i) => `thumb${i}`), "all", "settings"];
  }

  function card(id, icon, label, hint = "", cls = "") {
    return `<button class="cm-card ${cls}" data-id="${id}" tabindex="-1"><span class="tile">${svg(icon, 32)}</span>
      <span class="lbl">${label}</span>${hint ? `<span class="sub">${hint}</span>` : ""}</button>`;
  }
  function thumb(c, i) {
    const badge = c.kind === "shot" ? `<b class="badge shot">${svg("image", 14)}</b>` : `<b class="badge">${shortClock(c.secs)}</b>`;
    return `<button class="cm-card cm-thumb" data-id="thumb${i}" tabindex="-1"><span class="tile" style="background-image:url(${c.img})">${badge}</span>
      <span class="lbl">${kindOf(c)}</span><span class="sub">${ago(c)}</span></button>`;
  }
  function hints() {
    const k = G.keyboard, p = G[mode] || G.xbox, pad = mode !== "keyboard";
    const range = `${g(k[1])}<span class="dash">–</span>${g(k[8])}`;
    const list = picking
      ? (pad ? [[g(p.lr), t.choose], [g(p.a), t.save_k], [g(p.b), t.back]]
             : [[g(k.left) + g(k.right), t.choose], [g(k.enter), t.save_k], [range, t.pick], [g(k.esc), t.back]])
      : (pad ? [[g(p.lr), t.move], [g(p.a), t.select], [g(p.x), t.shot], [g(p.y), t.view_latest], [g(p.r1), t.trim_latest], [g(p.b), t.close]]
             : [[g(k.left) + g(k.right), t.move], [g(k.enter), t.select], [range, t.instantly], [g(k.t), t.trim_latest], [g(k.esc), t.close]]);
    return list.map(([glyph, label]) => `<span class="hint">${glyph}<span>${label}</span></span>`).join("");
  }
  function status() {
    return recStart === null ? `<span class="green">●</span>&nbsp;&nbsp;${t.keeping}`
      : `<span class="red">●</span>&nbsp;&nbsp;<span class="ink">${t.recording}</span>&nbsp;&nbsp;${clock(Date.now() - recStart)}`;
  }
  function render() {
    const rec = recStart === null ? card("rec", "record", t.rec) : card("rec", "stop", fill(t.stop, { t: clock(Date.now() - recStart) }), "", "danger");
    const mic = micOn ? card("mic", "mic", t.mic, `<span class="green">${t.on}</span>`) : card("mic", "mic-off", t.mic, `<span class="red">${t.off}</span>`, "red-icon");
    menu.innerHTML = `<div class="cm-bar">
      <div class="cm-head"><span class="cm-game">${t.game}</span><span class="cm-status">${status()}</span></div>
      ${picking ? `<div class="cm-picker">
          <div class="cm-caption">${t.caption}&nbsp;&nbsp;&nbsp;<span>${t.game} · 30:00 / 30:00${armed !== null ? `&nbsp;&nbsp;·&nbsp;&nbsp;${t.again}` : ""}</span></div>
          <div class="cm-chips">${OPTIONS.map((s, i) => `<button class="cm-chip" data-id="chip${i}" tabindex="-1"><span>${chipLabel(s)}</span></button>`).join("")}
          <button class="cm-chip save" data-id="chip_save" tabindex="-1"><span>${t.save_clip}</span></button></div>
        </div>`
      : `<div class="cm-row">${card("save", "rewind", t.save, t.save_hint)}${card("shot", "camera", t.shot)}${rec}${mic}
          <i class="rule"></i>${thumbsShown().map(thumb).join("")}<i class="rule"></i>${card("all", "gallery", t.all)}${card("settings", "settings", t.settings)}</div>`}
      <div class="cm-foot"><div class="cm-hints">${hints()}</div><div class="cm-info" id="cm-info"></div></div>
    </div>`;
    menu.classList.toggle("picking", picking);
    paintFocus();
  }
  const navIds = () => picking ? [...OPTIONS.map((_, i) => `chip${i}`), "chip_save"] : items();
  function paintFocus() {
    const id = navIds()[focus];
    menu.querySelectorAll("[data-id]").forEach((el) => el.classList.toggle("focus", el.dataset.id === id));
    const info = $("cm-info");
    if (info) {
      const m = /^thumb(\d)$/.exec(id || "");
      info.textContent = m ? `${caps[+m[1]].game || t.game}    ${size(caps[+m[1]])}` : "";
    }
  }
  function setFocus(i) { focus = Math.max(0, Math.min(navIds().length - 1, i)); paintFocus(); }

  // ---------------------------------------------------------------- open, close, pages
  function show() {
    page = null; pc.classList.remove("paging");
    if (!open) { open = true; picking = false; focus = 0; }
    stage.classList.add("open"); render();
  }
  function hide() { open = false; picking = false; stage.classList.remove("open"); }
  function toggle() { if (P.isOpen()) { P.close(); open = false; show(); return; } open ? hide() : show(); }
  // the pages work as in the app (pages.js); Back from one comes to the bar
  function openPage(name, opts = {}) {
    hide();
    if (name === "library") P.open("gallery");
    else if (name === "settings") P.open("settings");
    else if (name === "save") P.open("save", { len: lastChoice });
    else P.open("viewer", { i: opts.i || 0, panel: name === "trim" ? "trim" : opts.panel || null });
  }
  function closePage() { P.close(); open = false; show(); }

  // ---------------------------------------------------------------- what the bar does
  function addCapture(c) { caps.unshift({ ...c, at: Date.now() }); }
  function saveClip(secs) {
    lastChoice = OPTIONS.indexOf(secs);
    hide();
    const len = secs === null ? 1800 : secs;
    addCapture({ kind: "clip", secs: len, img: "assets/game.jpg" });
    toastCapture("clip_saved", () => secs === null ? fill(t.everything, { l: clock(1800e3) }) : fill(t.last, { l: duration(secs) }), true);
  }
  function screenshot() {
    hide();
    setTimeout(() => {           // the bar is gone first, so it isn't in the picture
      const flash = $("try-flash");
      flash.classList.remove("go"); void flash.offsetWidth; flash.classList.add("go");
      addCapture({ kind: "shot", img: "assets/game.jpg" });
      toastCapture("shot_saved", () => "", false);
    }, 250);
  }
  function toggleRecord() {
    hide();
    if (recStart === null) {
      recStart = Date.now();
      $("cm-rec").classList.add("on");
      recTimer = setInterval(tick, 1000); tick();
      toastMessage("rec_started", true);
    } else {
      const secs = Math.max(1, Math.round((Date.now() - recStart) / 1000));
      recStart = null; clearInterval(recTimer);
      $("cm-rec").classList.remove("on");
      addCapture({ kind: "rec", secs, img: "assets/game.jpg" });
      toastCapture("rec_saved", () => fill(t.length, { l: clock(secs * 1000) }), true);
    }
  }
  function tick() {
    const el = $("cm-rec");
    el.querySelector("span").textContent = `REC  ${clock(Date.now() - recStart)}`;
    el.classList.toggle("dim");
    if (open && !picking) {
      menu.querySelector(".cm-status").innerHTML = status();
      const lbl = menu.querySelector('[data-id="rec"] .lbl');
      if (lbl) lbl.textContent = fill(t.stop, { t: clock(Date.now() - recStart) });
    }
  }
  function toggleMic() {
    micOn = !micOn;
    render();
    toastMessage(micOn ? "mic_msg_on" : "mic_msg_off", false);
  }
  function activate(id) {
    if (id === "save") openPage("save");
    else if (id === "shot") screenshot();
    else if (id === "rec") toggleRecord();
    else if (id === "mic") toggleMic();
    else if (id === "all") openPage("library");
    else if (id === "settings") openPage("settings");
    else if (id === "back") closePicker();
    else if (id === "chip_save") saveClip(OPTIONS[lastChoice]);
    else if (id.startsWith("thumb")) openPage("viewer", { i: +id.slice(5) });
    else if (/^chip\d$/.test(id)) saveClip(OPTIONS[+id.slice(4)]);
  }
  function closePicker() { picking = false; armed = null; render(); setFocus(0); }

  // ---------------------------------------------------------------- notices
  function present(make, ms) {
    const el = $("cm-toast");
    toastHtml = make;
    el.innerHTML = make();
    el.classList.remove("in"); void el.offsetWidth; el.classList.add("in");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("in"), ms);
  }
  // title and detail are keys and values for t, read when the notice is written (and rewritten)
  function toastCapture(title, detail, trimmable) {
    present(() => captureHtml(t[title], detail(), trimmable), 6000);
  }
  function captureHtml(title, detail, trimmable) {
    const k = G.keyboard, p = G[mode] || G.xbox;
    const open = mode === "keyboard" ? g(k.alt) + "&nbsp;" + g(k.c) : g(p.create);
    const view = mode === "keyboard" ? g(k.v) : g(p.y);
    const sub = [detail, t.game].filter(Boolean).join("  ·  ");
    return `<div class="thumbnail" style="background-image:url(assets/game.jpg)"></div>
      <div class="text"><b>${title}</b><span>${sub}</span>
      <div class="acts"><button class="trim" data-act="view" tabindex="-1">${svg("play", 14)}<span>${t.view}</span></button>
      ${trimmable ? `<button class="trim" data-act="trim" tabindex="-1">${svg("scissors", 14)}<span>${t.trim}</span></button>` : ""}
      <button class="trim" data-act="share" tabindex="-1">${svg("share", 14)}<span>${t.share}</span></button></div></div>`;
  }
  function toastMessage(key, rec) {
    present(() => {
      const [title, sub] = t[key].split(" · ");
      return `<div class="text"><b>${rec ? '<span class="red">●</span>&nbsp;&nbsp;' : ""}${title}</b>${sub ? `<span>${sub}</span>` : ""}</div>`;
    }, 3500);
  }
  $("cm-toast").addEventListener("click", (e) => {
    e.stopPropagation();
    $("cm-toast").classList.remove("in");
    const act = e.target.closest("[data-act]");
    openPage(act && act.dataset.act === "trim" ? "trim" : "viewer", { panel: act && act.dataset.act === "share" ? "share" : null });
  });

  // ---------------------------------------------------------------- mouse: hover lends the highlight, like the app
  menu.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[data-id]");
    if (!el || (picking && !el.dataset.id.startsWith("chip"))) return;
    const i = navIds().indexOf(el.dataset.id);
    if (i < 0 || i === focus) return;
    if (lent === null) lent = focus;
    setFocus(i);
  });
  menu.addEventListener("mouseout", (e) => {
    const el = e.target.closest("[data-id]");
    if (!el || el.contains(e.relatedTarget) || lent === null) return;
    setFocus(lent); lent = null;
  });
  menu.addEventListener("click", (e) => {
    e.stopPropagation();
    const el = e.target.closest("[data-id]");
    if (!el) { if (e.target === menu && e.offsetY < (picking ? 160 : 90)) hide(); return; }   // above the bar: back to the game
    lent = null;
    const i = navIds().indexOf(el.dataset.id);
    if (i >= 0) setFocus(i);
    const id = el.dataset.id;
    if (/^chip\d$/.test(id) && armed !== id) {     // a click picks a length; a second click on it saves (as the app)
      armed = id; lastChoice = +id.slice(4); render(); setFocus(navIds().indexOf(id)); return;
    }
    activate(id);
  });
  $("cm-page").addEventListener("click", (e) => { e.stopPropagation(); closePage(); });

  // ---------------------------------------------------------------- keys and pad buttons
  function key(k) {
    if (P.isOpen()) return P.key(k);
    if (!open) return false;
    const fwd = lang === "ar" ? -1 : 1;           // right to left: the arrows follow the layout
    lent = null;
    if (k === "ArrowLeft") setFocus(focus - fwd);
    else if (k === "ArrowRight") setFocus(focus + fwd);
    else if (k === "Enter" || k === " " || k === "A") activate(navIds()[focus]);
    else if (/^[1-8]$/.test(k)) saveClip(OPTIONS[+k - 1]);
    else if (picking) { if (k === "Escape" || k === "Backspace" || k === "ArrowDown" || k === "B") closePicker(); else return false; }
    else if (k === "Escape" || k === "B") hide();
    else if (k === "ArrowUp" && focus === 0) activate("save");
    else if (k === "s" || k === "X") screenshot();
    else if (k === "r") toggleRecord();
    else if (k === "v" || k === "Y") openPage("viewer");
    else if (k === "t" || k === "R1") openPage("trim");
    else if (k === "g" || k === "o") openPage("library");
    else if (k === ",") openPage("settings");
    else if (k === "m") toggleMic();
    else return false;
    return true;
  }
  function setMode(m) { if (m !== mode) { mode = m; if (open) render(); } }

  let shareDest = "discord";
  const P = makePages({
    svg, t: () => t, caps: () => caps, duration, ago,
    back: () => { open = false; show(); },
    lastDest: () => shareDest, setDest: (d) => { shareDest = d; },
    saved(len, secs, shift) {
      addCapture({ kind: "clip", secs: len, img: "assets/game.jpg" });
      toastCapture("clip_saved", () => secs === null ? fill(t.everything, { l: clock(1800e3) }) : fill(t.last, { l: duration(secs) }), true);
    },
    trimmed(len) { addCapture({ kind: "clip", secs: len, img: "assets/game.jpg" }); toastCapture("trimmed", () => fill(t.length, { l: clock(len * 1000) }), true); },
    forget(c) { const i = caps.findIndex((x) => x.at === c.at); if (i >= 0) caps.splice(i, 1); },
    message(text) { present(() => { const [a, b] = text.split(" · "); return `<div class="text"><b>${a}</b>${b ? `<span>${b}</span>` : ""}</div>`; }, 3500); },
    notice(title, sub, img) { present(() => `<div class="thumbnail" style="background-image:url(${img})"></div><div class="text"><b>${title}</b><span>${sub}</span></div>`, 6000); },
  });
  // the screen is 1920 wide, scaled to the stage
  new ResizeObserver(() => pc.style.setProperty("--k", stage.clientWidth / 1920)).observe(stage);
  setInterval(() => { if (open && !picking && !recStart) menu.querySelectorAll(".cm-thumb .sub").forEach((el, i) => { el.textContent = ago(caps[i]); }); }, 30e3);

  return {
    toggle, key, setMode, isOpen: () => open || P.isOpen(),
    saveLast30() { hide(); P.close(); addCapture({ kind: "clip", secs: 30, img: "assets/game.jpg" }); toastCapture("clip_saved", () => fill(t.last, { l: duration(30) }), true); },
    setLang(l) {
      lang = l; t = W[l]; P.setLang(l);
      if (open) render();                                  // focus, the picker and REC stay as they are
      if (toastHtml && $("cm-toast").classList.contains("in")) $("cm-toast").innerHTML = toastHtml();   // same notice, same time left
    },
  };
})();
