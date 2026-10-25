// Capture Menu website: English / Arabic, the try-it demo (Alt + C or a controller's Create / View),
// scroll reveals and the official PlayStation and Xbox marks.

const T = {
  en: {
    skip: "Skip to content",
    all_releases: "All releases",
    final_p: "Free for Windows 10 and 11. Setup takes about a minute.",
    faq_p: "Something else? <a href=\"https://github.com/Amjz03/capture-menu/issues\">Open an issue on GitHub</a>.",
    f_p: "Saving is one part. The rest of the app is built for what you do next with the clip, with a controller or a mouse.",
    k_close: "close",
    k_save: "save a length",
    k_pick: "pick",
    k_move: "move",
    works_with: "Works with",
    nav_try: "Try it", nav_features: "Features", nav_faq: "FAQ", download_short: "Download",
    kicker: "Free and open source, for Windows 10 and 11",
    h1: "The PS5 Create button, <span>on your PC.</span>",
    lede: "Capture Menu keeps the last 30 minutes of any game. Press once to pick what to save. Press twice to save the last 30 seconds.",
    download: "Download for Windows", github: "Source on GitHub",
    fine: "About 50 MB. No account, no ads. Setup installs OBS and FFmpeg for you.",
    ago: "30 min ago", now: "now", more_pads: "and most other controllers",
    
    try_h: "Try the menu",
    try_p: "This is the real menu, rebuilt in the page. Press Alt + C once to open it, then move with the arrows or the mouse and pick with Enter. Press twice to save the last 30 seconds. A controller plugged into this computer works too.",
    page_hint: "Click or press Esc to go back",
    buf_q: "How much do you want to keep?",
    try_hint: "Press Alt + C, or click here",
    press_once: "Press once", press_twice: "Press twice",
    pad_none: "No controller found. Plug one in and press any button.",
    pad_on: "Controller found: {name}. Press Create / View.",
    alt_picker: "The Save recent gameplay row over Red Dead Redemption 2, with Last 30m picked", alt_library: "The Captures page: a sidebar of games and a grid of clips and screenshots", alt_viewer: "The viewer playing a Red Dead Redemption 2 clip, with Trim, Share and Favorite", alt_trim: "Trimming a clip on a timeline of frames", alt_settings: "The Settings page: resolution, frame rate, quality and replay length", alt_rec: "Red Dead Redemption 2 at night with a small REC 12:34 timer in the corner", alt_game: "Call of Duty on a snowy rooftop, the game the menu opens over",
    whats_new: "What's new", released: "Version {v} · {date}",
    rec_note: "Keeping the last 30 min", anywhere: "Press it anywhere on this page",
    how_h: "How it works", privacy: "Privacy",
    s1_h: "Play", s1_p: "It quietly keeps the last 30 minutes of your game, on any screen, with any graphics card.",
    s2_h: "Press", s2_p: "Once for the menu over your game: save 15 seconds up to 30 minutes, screenshot or record. Twice to save the last 30 seconds.",
    s3_h: "Keep", s3_p: "Every game gets its own folder. Watch it, trim it to the frame, share it to Discord or your phone.",
    f_h: "Everything after the press",
    t1_h: "Pick how much to keep", t1_p: "The last 15 seconds, 1, 3, 5, 15 or 30 minutes, or everything. With the mouse, the keys or the d-pad.",
    t2_h: "Press twice, it's saved", t2_p: "The last 30 seconds, without opening anything.",
    t8_h: "Set up for your PC", t8_p: "Resolution, frame rate, quality and how much to keep, on one page.",
    t4_h: "A folder for every game", t4_p: "Found automatically. Favorites, titles, notes, sizes, sorting.",
    t5_h: "Watch it right away", t5_p: "A viewer with your voice and the game on their own tracks.",
    t6_h: "Trim to the frame", t6_p: "Then share a copy sized for Discord or your phone, straight to the clipboard.",
    t7_h: "Record for hours", t7_p: "A small REC timer while you record. Screenshots in full resolution.",
    faq_h: "Questions",
    q1: "Is it really free?", a1: "Yes. It's open source under the MIT license: no account, no ads, no watermark.",
    q2: "What does it need?", a2: "Windows 10 or 11. Setup installs OBS Studio and FFmpeg if you don't have them and sets OBS up for your PC: resolution, the best encoder for your graphics card and the 30-minute replay buffer.",
    q3: "The browser or Windows says it's unsafe", a3: "It isn't: Windows Defender finds nothing in it. Browsers and Windows warn about new apps that aren't signed yet. In Chrome or Edge, open Downloads and choose Keep (in Edge: ··· then Keep anyway). If Windows then shows \"Windows protected your PC\", click More info, then Run anyway. Code signing is on the way.",
    q4: "Will it slow my game down?", a4: "Capture Menu uses about 75 MB while it waits, and its FFmpeg work runs at low priority. The 30-minute buffer lives in OBS and uses RAM (up to about 2.9 GB at 1440p); pick a shorter buffer or lighter quality in Settings for less.",
    q5: "Does anything leave my PC?", a5: "No. It talks to OBS on your PC, and to GitHub only when you check for updates. Your clips stay with you.",
    q6: "Is it in Arabic?", a6: "Yes, the whole interface, right to left, like the PS5.",
    final_h: "Download Capture Menu",
    tm: "PlayStation and Xbox are trademarks of their owners. Capture Menu is not affiliated with Sony or Microsoft.",
    title: "Capture Menu · The PS5 Create button, on your PC",
  },
  ar: {
    skip: "تخطّ إلى المحتوى",
    all_releases: "كل الإصدارات",
    final_p: "مجاني لويندوز 10 و11. التثبيت ياخذ تقريبًا دقيقة.",
    faq_p: "عندك سؤال ثاني؟ <a href=\"https://github.com/Amjz03/capture-menu/issues\">افتح issue على GitHub</a>.",
    f_p: "الحفظ جزء واحد. باقي البرنامج مصمّم للي تسويه بالمقطع بعدها، بالكنترولر أو بالماوس.",
    k_close: "إغلاق",
    k_save: "حفظ مدة",
    k_pick: "اختيار",
    k_move: "تنقّل",
    works_with: "يشتغل مع",
    nav_try: "جرّبه", nav_features: "المميزات", nav_faq: "أسئلة", download_short: "تحميل",
    kicker: "مجاني ومفتوح المصدر، لويندوز 10 و11",
    h1: "زر Create حق PS5، <span>على الكمبيوتر.</span>",
    lede: "Capture Menu يحتفظ بآخر 30 دقيقة من أي لعبة. اضغط مرة واختر اللي تبي تحفظه. اضغط مرتين وتنحفظ آخر 30 ثانية.",
    download: "حمّله للويندوز", github: "الكود على GitHub",
    fine: "تقريبًا 50 ميجا. بدون حساب وبدون إعلانات. التثبيت يجهّز لك OBS وFFmpeg.",
    ago: "قبل 30 دقيقة", now: "الحين", more_pads: "وأغلب الكنترولرات الثانية",
    
    try_h: "جرّب القائمة",
    try_p: "هذي القائمة الحقيقية، مبنية داخل الصفحة. اضغط Alt + C مرة عشان تفتحها، وتنقّل بالأسهم أو الماوس، واختر بـ Enter. اضغط مرتين وتنحفظ آخر 30 ثانية. والكنترولر الموصّل بالكمبيوتر يشتغل بعد.",
    page_hint: "اضغط هنا أو Esc عشان ترجع",
    buf_q: "كم تبي تحفظ؟",
    try_hint: "اضغط Alt + C، أو اضغط هنا",
    press_once: "اضغط مرة", press_twice: "اضغط مرتين",
    pad_none: "ما فيه كنترولر. وصّل واحد واضغط أي زر.",
    pad_on: "لقينا الكنترولر: {name}. اضغط Create / View.",
    alt_picker: "صف حفظ اللعب الأخير فوق Red Dead Redemption 2، ومختار آخر 30 دقيقة", alt_library: "صفحة الوسائط: قائمة الألعاب على جنب وشبكة من المقاطع ولقطات الشاشة", alt_viewer: "العارض يشغّل مقطع من Red Dead Redemption 2، وفيه القص والمشاركة والمفضلة", alt_trim: "قص مقطع على شريط من الإطارات", alt_settings: "صفحة الإعدادات: الدقة وعدد الإطارات والجودة ومدة الحفظ", alt_rec: "Red Dead Redemption 2 بالليل، وفي الزاوية مؤقت REC 12:34 صغير", alt_game: "Call of Duty فوق سطح مغطّى بالثلج، واللعبة اللي تنفتح القائمة فوقها",
    whats_new: "وش الجديد", released: "الإصدار {v} · {date}",
    rec_note: "يحفظ آخر 30 دقيقة", anywhere: "اضغطه في أي مكان بالصفحة",
    how_h: "كيف يشتغل", privacy: "الخصوصية",
    s1_h: "العب", s1_p: "يحتفظ بهدوء بآخر 30 دقيقة من لعبك، على أي شاشة ومع أي كرت شاشة.",
    s2_h: "اضغط", s2_p: "مرة وتطلع القائمة فوق اللعبة: احفظ من 15 ثانية لين 30 دقيقة، أو صوّر، أو سجّل. ومرتين تحفظ آخر 30 ثانية.",
    s3_h: "احتفظ", s3_p: "كل لعبة لها مجلدها. شوفه، وقصّه بدقة الإطار، وشاركه للديسكورد أو جوالك.",
    f_h: "كل اللي بعد الضغطة",
    t1_h: "اختر كم تبي تحفظ", t1_p: "آخر 15 ثانية، أو 1 أو 3 أو 5 أو 15 أو 30 دقيقة، أو كل شي. بالماوس أو الكيبورد أو الأسهم.",
    t2_h: "اضغط مرتين وانحفظت", t2_p: "آخر 30 ثانية، بدون ما تفتح أي شي.",
    t8_h: "مضبوط على جهازك", t8_p: "الدقة، وعدد الإطارات، والجودة، وكم تبي تحفظ، كلها في صفحة وحدة.",
    t4_h: "مجلد لكل لعبة", t4_p: "يتعرف عليها تلقائيًا. مفضلة، وعناوين، وملاحظات، وأحجام، وترتيب.",
    t5_h: "شوفه على طول", t5_p: "عارض فيه صوتك وصوت اللعبة كل واحد بمساره.",
    t6_h: "قصّه بدقة الإطار", t6_p: "وبعدها شارك نسخة بحجم مناسب للديسكورد أو جوالك، على طول للحافظة.",
    t7_h: "سجّل لساعات", t7_p: "مؤقت REC صغير وأنت تسجّل. ولقطات شاشة بدقة كاملة.",
    faq_h: "أسئلة",
    q1: "صدق مجاني؟", a1: "إيه. مفتوح المصدر برخصة MIT: بدون حساب، وبدون إعلانات، وبدون علامة مائية.",
    q2: "وش يحتاج؟", a2: "ويندوز 10 أو 11. التثبيت ينزّل لك OBS Studio وFFmpeg إذا ما عندك، ويضبط OBS على جهازك: الدقة، وأفضل ترميز لكرت شاشتك، وذاكرة الـ 30 دقيقة.",
    q3: "المتصفح أو ويندوز يقول إنه غير آمن", a3: "هو آمن: Windows Defender ما يلقى فيه شي. المتصفحات وويندوز تحذّر من البرامج الجديدة اللي ما انوقّعت للحين. في كروم أو إيدج افتح التنزيلات واختر Keep (في إيدج: ··· بعدها Keep anyway). وإذا طلع لك بعدها \"Windows protected your PC\" اضغط More info وبعدها Run anyway. والتوقيع جاي قريب.",
    q4: "بيثقّل على لعبتي؟", a4: "Capture Menu ياخذ تقريبًا 75 ميجا وهو ينتظر، وشغل FFmpeg حقه بأولوية منخفضة. ذاكرة الـ 30 دقيقة في OBS وتاخذ من الرام (لين تقريبًا 2.9 جيجا على 1440p)، وتقدر تقللها من الإعدادات.",
    q5: "يطلع شي من جهازي؟", a5: "لا. يكلّم OBS اللي على جهازك، وGitHub بس لما تدوّر تحديثات. كليباتك تبقى عندك.",
    q6: "فيه عربي؟", a6: "إيه، الواجهة كاملة بالعربي ومن اليمين لليسار، مثل PS5.",
    final_h: "حمّل Capture Menu",
    tm: "PlayStation وXbox علامات تجارية لأصحابها. Capture Menu ما له علاقة بسوني أو مايكروسوفت.",
    title: "Capture Menu · زر Create حق PS5، على الكمبيوتر",
  },
};

// the official marks (Simple Icons)
const BRAND = {
  ps: "M8.984 2.596v17.547l3.915 1.261V6.688c0-.69.304-1.151.794-.991.636.18.76.814.76 1.505v5.875c2.441 1.193 4.362-.002 4.362-3.152 0-3.237-1.126-4.675-4.438-5.827-1.307-.448-3.728-1.186-5.39-1.502zm4.656 16.241l6.296-2.275c.715-.258.826-.625.246-.818-.586-.192-1.637-.139-2.357.123l-4.205 1.5V14.98l.24-.085s1.201-.42 2.913-.615c1.696-.18 3.785.03 5.437.661 1.848.601 2.04 1.472 1.576 2.072-.465.6-1.622 1.036-1.622 1.036l-8.544 3.107V18.86zM1.807 18.6c-1.9-.545-2.214-1.668-1.352-2.32.801-.586 2.16-1.052 2.16-1.052l5.615-2.013v2.313L4.205 17c-.705.271-.825.632-.239.826.586.195 1.637.15 2.343-.12L8.247 17v2.074c-.12.03-.256.044-.39.073-1.939.331-3.996.196-6.038-.479z",
  xbox: "M4.102 21.033C6.211 22.881 8.977 24 12 24c3.026 0 5.789-1.119 7.902-2.967 1.877-1.912-4.316-8.709-7.902-11.417-3.582 2.708-9.779 9.505-7.898 11.417zm11.16-14.406c2.5 2.961 7.484 10.313 6.076 12.912C23.002 17.48 24 14.861 24 12.004c0-3.34-1.365-6.362-3.57-8.536 0 0-.027-.022-.082-.042-.063-.022-.152-.045-.281-.045-.592 0-1.985.434-4.805 3.246zM3.654 3.426c-.057.02-.082.041-.086.042C1.365 5.642 0 8.664 0 12.004c0 2.854.998 5.473 2.661 7.533-1.401-2.605 3.579-9.951 6.08-12.91-2.82-2.813-4.216-3.245-4.806-3.245-.131 0-.223.021-.281.046v-.002zM12 3.551S9.055 1.828 6.755 1.746c-.903-.033-1.454.295-1.521.339C7.379.646 9.659 0 11.984 0H12c2.334 0 4.605.646 6.766 2.085-.068-.046-.615-.372-1.52-.339C14.946 1.828 12 3.545 12 3.545v.006z",
};
document.getElementById("ps-path").setAttribute("d", BRAND.ps);
document.getElementById("xbox-path").setAttribute("d", BRAND.xbox);

// ---------------------------------------------------------------- language
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode: the choice just isn't remembered */ } },
};
// ?lang=ar (or en) in the address wins, so a shared link opens in its language; then the visitor's
// last choice, then the browser's language
const asked = new URLSearchParams(location.search).get("lang");
let lang = ["ar", "en"].includes(asked) ? asked : store.get("lang") || ((navigator.language || "").toLowerCase().startsWith("ar") ? "ar" : "en");
let padName = "";

function applyLang() {
  const t = T[lang];
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.title = t.title;
  document.querySelectorAll("[data-i18n]").forEach((el) => { if (t[el.dataset.i18n]) el.textContent = t[el.dataset.i18n]; });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t[el.dataset.i18nHtml]; });
  document.querySelectorAll("[data-i18n-alt]").forEach((el) => { el.alt = t[el.dataset.i18nAlt]; });
  // the app's own screens, in the same language
  document.querySelectorAll("img[data-src-lang]").forEach((img) => { img.src = img.src.replace(/-(en|ar)\.jpg$/, `-${lang}.jpg`); });
  DEMO.setLang(lang);
  renderBuffer();
  // the app's own screens, in motion, in the same language
  document.querySelectorAll("video[data-lang-video]").forEach((video) => {
    video.poster = video.getAttribute("poster").replace(/-(en|ar)\.jpg$/, `-${lang}.jpg`);
    if (video.currentSrc && video.currentSrc.includes(`hero-${lang}`)) return;
    video.querySelectorAll("source").forEach((src) => { src.src = src.getAttribute("src").replace(/hero-(en|ar)/, `hero-${lang}`); });
    if (video.currentSrc) { video.load(); if (video.dataset.playing) video.play().catch(() => {}); }
  });
  renderRelease();
  document.getElementById("lang").textContent = lang === "ar" ? "English" : "العربية";
  updatePadStatus();
}
document.getElementById("lang").addEventListener("click", () => {
  lang = lang === "ar" ? "en" : "ar"; store.set("lang", lang);
  const url = new URL(location.href);
  lang === "ar" ? url.searchParams.set("lang", "ar") : url.searchParams.delete("lang");
  history.replaceState(null, "", url);
  applyLang();
});

// ---------------------------------------------------------------- the latest release, from GitHub
let release = null;
function renderRelease() {
  if (!release) return;
  const date = new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { day: "numeric", month: "long", year: "numeric" })
    .format(new Date(release.published_at));
  const link = document.getElementById("release-link");
  link.href = release.html_url;
  link.innerHTML = `${T[lang].released.replace("{v}", release.tag_name.replace(/^v/, "")).replace("{date}", date)} · <span>${T[lang].whats_new} <span class="arrow" aria-hidden="true">→</span></span>`;
  document.getElementById("release").hidden = false;
}
fetch("https://api.github.com/repos/Amjz03/capture-menu/releases/latest")
  .then((r) => (r.ok ? r.json() : null))
  .then((r) => { if (r && r.tag_name) { release = r; renderRelease(); } })
  .catch(() => {});   // offline or rate-limited: the line just stays hidden

// ---------------------------------------------------------------- hero: pick how much of the 30 minutes to keep
// The red slice is what gets saved, measured against the whole 30 minutes. It walks through the
// choices on its own until the visitor picks one (a chip, or a click / drag on the bar).
const BUF = [15, 30, 60, 180, 300, 900, 1800];
let bufPick = 180, bufAuto = null;
const bufChip = (s) => lang === "ar" ? (s < 60 ? `${s} ث` : `${s / 60} د`) : (s < 60 ? `${s}s` : `${s / 60}m`);
function bufWords(s) {
  if (lang === "ar") return s < 60 ? `آخر ${s} ثانية` : s === 60 ? "آخر دقيقة" : s <= 300 ? `آخر ${s / 60} دقايق` : `آخر ${s / 60} دقيقة`;
  return s < 60 ? `Last ${s} seconds` : s === 60 ? "Last minute" : `Last ${s / 60} minutes`;
}
function renderBuffer() {
  document.getElementById("buf-slice").style.width = `${2.2 + (bufPick / 1800) * 97.8}%`;   // to scale; the 2.2 % keeps 15 seconds visible
  document.getElementById("buf-pick").textContent = bufWords(bufPick);
  document.getElementById("buf-chips").innerHTML = BUF.map((s) =>
    `<button type="button" data-s="${s}" class="${s === bufPick ? "on" : ""}" aria-pressed="${s === bufPick}">${bufChip(s)}</button>`).join("");
}
function pickBuffer(s) { clearInterval(bufAuto); bufAuto = null; bufPick = s; renderBuffer(); }
document.getElementById("buf-chips").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) pickBuffer(+b.dataset.s); });
const track = document.getElementById("buf-track");
function fromTrack(e) {   // the track runs left to right, now on the right, in both languages
  const r = track.getBoundingClientRect();
  const secs = Math.max(0, ((r.right - e.clientX) / r.width * 100 - 2.2) / 97.8) * 1800;   // the same scale
  pickBuffer(BUF.reduce((a, b) => (Math.abs(b - secs) < Math.abs(a - secs) ? b : a)));
}
track.addEventListener("pointerdown", (e) => { track.setPointerCapture(e.pointerId); fromTrack(e); });
track.addEventListener("pointermove", (e) => { if (track.hasPointerCapture(e.pointerId)) fromTrack(e); });
bufAuto = setInterval(() => { bufPick = BUF[(BUF.indexOf(bufPick) + 1) % BUF.length]; renderBuffer(); }, 1800);

// ---------------------------------------------------------------- try it (demo.js): once opens, twice saves
// The same rule as the app's PressSequencer: a second press within 350 ms is a double press.
const stage = document.getElementById("stage");
let pending = null;
function press() {
  const r = stage.getBoundingClientRect();
  if (r.bottom < 80 || r.top > innerHeight - 80) stage.scrollIntoView({ behavior: "smooth", block: "center" });
  stage.classList.add("used");
  if (pending) { clearTimeout(pending); pending = null; DEMO.saveLast30(); return; }
  pending = setTimeout(() => { pending = null; DEMO.toggle(); }, 350);
}
function now(fn) { clearTimeout(pending); pending = null; stage.classList.add("used"); fn(); }
document.addEventListener("keydown", (e) => {
  DEMO.setMode("keyboard");
  if (e.altKey && (e.code === "KeyC" || e.key.toLowerCase() === "c")) { e.preventDefault(); press(); return; }
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  if (DEMO.key(e.key.length === 1 ? e.key.toLowerCase() : e.key)) e.preventDefault();
});
document.getElementById("press-once").addEventListener("click", () => now(DEMO.toggle));
document.getElementById("press-twice").addEventListener("click", () => now(DEMO.saveLast30));
stage.addEventListener("click", () => { if (!DEMO.isOpen()) now(DEMO.toggle); });

// controllers: the browser's Gamepad API, standard layout. 8 is Create (PlayStation) / View (Xbox);
// the rest drive the bar the way they do in the app.
const PAD_KEYS = { 0: "A", 1: "B", 2: "X", 3: "Y", 5: "R1", 12: "ArrowUp", 13: "ArrowDown", 14: "ArrowLeft", 15: "ArrowRight" };
let lastDown = [];
function updatePadStatus() {
  const el = document.getElementById("pad-status");
  el.textContent = padName ? T[lang].pad_on.replace("{name}", padName) : T[lang].pad_none;
  el.classList.toggle("on", !!padName);
}
window.addEventListener("gamepadconnected", (e) => { padName = e.gamepad.id.replace(/\s*\(.*\)\s*/g, " ").trim() || "Gamepad"; updatePadStatus(); poll(); });
window.addEventListener("gamepaddisconnected", () => { padName = ""; updatePadStatus(); });
function poll() {
  const pad = [...(navigator.getGamepads ? navigator.getGamepads() : [])].find(Boolean);
  if (!pad) return;
  const down = pad.buttons.map((b) => b.pressed);
  down.forEach((d, i) => {
    if (!d || lastDown[i]) return;
    DEMO.setMode(/054c|playstation|dualsense|dualshock|wireless controller/i.test(pad.id) ? "playstation" : "xbox");
    if (i === 8) press();
    else if (PAD_KEYS[i]) DEMO.key(PAD_KEYS[i]);
  });
  lastDown = down;
  requestAnimationFrame(poll);
}

// ---------------------------------------------------------------- the nav marks the section in view
const navLinks = [...document.querySelectorAll('.links a[href^="#"]')];
const spy = new IntersectionObserver((entries) => entries.forEach((e) => {
  if (!e.isIntersecting) return;
  navLinks.forEach((a) => a.classList.toggle("here", a.getAttribute("href") === `#${e.target.id}`));
}), { rootMargin: "-45% 0px -50% 0px" });
navLinks.forEach((a) => { const el = document.querySelector(a.getAttribute("href")); if (el) spy.observe(el); });

// screenshots shimmer until they've loaded
document.querySelectorAll(".features img").forEach((img) => {
  const done = () => img.classList.add("loaded");
  img.complete && img.naturalWidth ? done() : img.addEventListener("load", done, { once: true });
});

// ---------------------------------------------------------------- the hero: REC counts
// The clock is how long this page has been open: the time Capture Menu would already be keeping.
const recClock = document.getElementById("rec-clock"), opened = Date.now();
setInterval(() => {
  const sec = Math.floor((Date.now() - opened) / 1000);
  recClock.textContent = `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
}, 1000);
// the menu loop plays only while it's on screen
const lazyVideos = new IntersectionObserver((entries) => entries.forEach(({ target: v, isIntersecting }) => {
  if (isIntersecting) { v.dataset.playing = "1"; v.play().catch(() => {}); } else { delete v.dataset.playing; v.pause(); }
}), { threshold: 0.25 });
document.querySelectorAll(".lazy-video").forEach((v) => lazyVideos.observe(v));
// each screenshot casts its own soft light
document.querySelectorAll(".features figure").forEach((fig) => {
  const media = fig.querySelector("img, video"), light = document.createElement("span");
  light.className = "cast"; light.setAttribute("aria-hidden", "true");
  const sync = () => { light.style.backgroundImage = `url("${media.poster || media.currentSrc || media.src}")`; };
  media.addEventListener(media.tagName === "VIDEO" ? "loadeddata" : "load", sync); sync();
  media.before(light);
});

// ---------------------------------------------------------------- reveal on scroll
const io = new IntersectionObserver((entries) => entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }),
                                    { threshold: 0.12 });
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));

applyLang();
