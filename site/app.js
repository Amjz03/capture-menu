// Capture Menu website: English / Arabic, the try-it demo (Alt + C or a controller's Create / View),
// scroll reveals and the official PlayStation and Xbox marks.

const T = {
  en: {
    nav_try: "Try it", nav_features: "Features", nav_faq: "FAQ", download_short: "Download",
    kicker: "Free · Open source · Windows 10 & 11",
    h1: "The <em>PS5 Create button</em>, on your PC.",
    lede: "Capture Menu keeps the last 30 minutes of any game. Press once to pick what to save. Press twice to save the last 30 seconds, instantly.",
    download: "Download for Windows", github: "View on GitHub",
    fine: "About 50 MB · No account · No ads · Sets up OBS and FFmpeg for you",
    ago: "30 min ago", now: "now", more_pads: "and most other controllers",
    try_eyebrow: "Try it right here",
    try_h: 'Press <span class="key key-inline">Alt</span> + <span class="key key-inline">C</span>',
    try_p: "Once opens the menu. Twice saves the last 30 seconds. A controller plugged into this computer works too: press Create or View.",
    try_hint: "Press Alt + C, or use the buttons below",
    press_once: "Press once", press_twice: "Press twice",
    pad_none: "No controller found. Plug one in and press any button.",
    pad_on: "Controller found: {name}. Press Create / View.",
    s1_h: "Play", s1_p: "It quietly keeps the last 30 minutes of your game, on any screen, with any graphics card.",
    s2_h: "Press", s2_p: "Once for the menu over your game: save 15 seconds up to 30 minutes, screenshot or record. Twice to save the last 30 seconds.",
    s3_h: "Keep", s3_p: "Every game gets its own folder. Watch it, trim it to the frame, share it to Discord or your phone.",
    f_eyebrow: "Everything in one button", f_h: "Made like a console. Built for PC.",
    t1_h: "Pick how much to keep", t1_p: "The last 15 seconds, 1, 3, 5, 15 or 30 minutes, or everything. With the mouse, the keys or the d-pad.",
    t2_h: "Press twice, it's saved", t2_p: "The last 30 seconds, without opening anything.",
    t3_h: "Every controller", t3_p: "PlayStation / Xbox / most others, with button hints that match your pad.",
    t4_h: "A folder for every game", t4_p: "Found automatically. Favorites, titles, notes, sizes, sorting.",
    t5_h: "Watch it right away", t5_p: "A viewer with your voice and the game on their own tracks.",
    t6_h: "Trim to the frame", t6_p: "Then share a copy sized for Discord or your phone, straight to the clipboard.",
    t7_h: "Record for hours", t7_p: "A small REC timer while you record. Screenshots in full resolution.",
    faq_h: "Good questions",
    q1: "Is it really free?", a1: "Yes. It's open source under the MIT license: no account, no ads, no watermark.",
    q2: "What does it need?", a2: "Windows 10 or 11. Setup installs OBS Studio and FFmpeg if you don't have them and sets OBS up for your PC: resolution, the best encoder for your graphics card and the 30-minute replay buffer.",
    q3: "Windows says \"Windows protected your PC\"", a3: "Windows shows that for apps that aren't signed yet. Click More info, then Run anyway. Code signing is on the way.",
    q4: "Will it slow my game down?", a4: "Capture Menu uses about 75 MB while it waits, and its FFmpeg work runs at low priority. The 30-minute buffer lives in OBS and uses RAM (up to about 2.9 GB at 1440p); pick a shorter buffer or lighter quality in Settings for less.",
    q5: "Does anything leave my PC?", a5: "No. It talks to OBS on your PC, and to GitHub only when you check for updates. Your clips stay with you.",
    q6: "Is it in Arabic?", a6: "Yes, the whole interface, right to left, like the PS5.",
    final_h: "Never miss the play again.",
    tm: "PlayStation and Xbox are trademarks of their owners. Capture Menu is not affiliated with Sony or Microsoft.",
    title: "Capture Menu · The PS5 Create button, on your PC",
  },
  ar: {
    nav_try: "جرّبه", nav_features: "المميزات", nav_faq: "أسئلة", download_short: "تحميل",
    kicker: "مجاني · مفتوح المصدر · ويندوز 10 و11",
    h1: "<em>زر Create حق PS5</em>، على الكمبيوتر.",
    lede: "Capture Menu يحتفظ بآخر 30 دقيقة من أي لعبة. اضغط مرة واختر اللي تبي تحفظه. اضغط مرتين وتنحفظ آخر 30 ثانية على طول.",
    download: "حمّله للويندوز", github: "شوفه على GitHub",
    fine: "تقريبًا 50 ميجا · بدون حساب · بدون إعلانات · يجهّز لك OBS وFFmpeg",
    ago: "قبل 30 دقيقة", now: "الحين", more_pads: "وأغلب الكنترولرات الثانية",
    try_eyebrow: "جرّبه هنا",
    try_h: 'اضغط <span dir="ltr"><span class="key key-inline">Alt</span> + <span class="key key-inline">C</span></span>',
    try_p: "مرة تفتح القائمة. مرتين تحفظ آخر 30 ثانية. وإذا عندك كنترولر موصّل بالكمبيوتر يشتغل بعد: اضغط Create أو View.",
    try_hint: "اضغط Alt + C، أو استخدم الأزرار تحت",
    press_once: "اضغط مرة", press_twice: "اضغط مرتين",
    pad_none: "ما فيه كنترولر. وصّل واحد واضغط أي زر.",
    pad_on: "لقينا الكنترولر: {name}. اضغط Create / View.",
    s1_h: "العب", s1_p: "يحتفظ بهدوء بآخر 30 دقيقة من لعبك، على أي شاشة ومع أي كرت شاشة.",
    s2_h: "اضغط", s2_p: "مرة وتطلع القائمة فوق اللعبة: احفظ من 15 ثانية لين 30 دقيقة، أو صوّر، أو سجّل. ومرتين تحفظ آخر 30 ثانية.",
    s3_h: "احتفظ", s3_p: "كل لعبة لها مجلدها. شوفه، وقصّه بدقة الإطار، وشاركه للديسكورد أو جوالك.",
    f_eyebrow: "كل شي في زر واحد", f_h: "مصمّم مثل الكونسول. مبني للكمبيوتر.",
    t1_h: "اختر كم تبي تحفظ", t1_p: "آخر 15 ثانية، أو 1 أو 3 أو 5 أو 15 أو 30 دقيقة، أو كل شي. بالماوس أو الكيبورد أو الأسهم.",
    t2_h: "اضغط مرتين وانحفظت", t2_p: "آخر 30 ثانية، بدون ما تفتح أي شي.",
    t3_h: "كل الكنترولرات", t3_p: "بلايستيشن / إكس بوكس / وأغلب الثانية، والأزرار على الشاشة تطابق يدك.",
    t4_h: "مجلد لكل لعبة", t4_p: "يتعرف عليها تلقائيًا. مفضلة، وعناوين، وملاحظات، وأحجام، وترتيب.",
    t5_h: "شوفه على طول", t5_p: "عارض فيه صوتك وصوت اللعبة كل واحد بمساره.",
    t6_h: "قصّه بدقة الإطار", t6_p: "وبعدها شارك نسخة بحجم مناسب للديسكورد أو جوالك، على طول للحافظة.",
    t7_h: "سجّل لساعات", t7_p: "مؤقت REC صغير وأنت تسجّل. ولقطات شاشة بدقة كاملة.",
    faq_h: "أسئلة مهمة",
    q1: "صدق مجاني؟", a1: "إيه. مفتوح المصدر برخصة MIT: بدون حساب، وبدون إعلانات، وبدون علامة مائية.",
    q2: "وش يحتاج؟", a2: "ويندوز 10 أو 11. التثبيت ينزّل لك OBS Studio وFFmpeg إذا ما عندك، ويضبط OBS على جهازك: الدقة، وأفضل ترميز لكرت شاشتك، وذاكرة الـ 30 دقيقة.",
    q3: "ويندوز يقول \"Windows protected your PC\"", a3: "ويندوز يطلع هالرسالة للبرامج اللي ما انوقّعت للحين. اضغط More info وبعدها Run anyway. والتوقيع جاي قريب.",
    q4: "بيثقّل على لعبتي؟", a4: "Capture Menu ياخذ تقريبًا 75 ميجا وهو ينتظر، وشغل FFmpeg حقه بأولوية منخفضة. ذاكرة الـ 30 دقيقة في OBS وتاخذ من الرام (لين تقريبًا 2.9 جيجا على 1440p)، وتقدر تقللها من الإعدادات.",
    q5: "يطلع شي من جهازي؟", a5: "لا. يكلّم OBS اللي على جهازك، وGitHub بس لما تدوّر تحديثات. كليباتك تبقى عندك.",
    q6: "فيه عربي؟", a6: "إيه، الواجهة كاملة بالعربي ومن اليمين لليسار، مثل PS5.",
    final_h: "لا تفوّتك اللقطة مرة ثانية.",
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
let lang = store.get("lang") || ((navigator.language || "").toLowerCase().startsWith("ar") ? "ar" : "en");
let padName = "";

function applyLang() {
  const t = T[lang];
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.title = t.title;
  document.querySelectorAll("[data-i18n]").forEach((el) => { if (t[el.dataset.i18n]) el.textContent = t[el.dataset.i18n]; });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t[el.dataset.i18nHtml]; });
  // the app's own screens, in the same language
  document.querySelectorAll("img[data-src-lang]").forEach((img) => { img.src = img.src.replace(/-(en|ar)\.jpg$/, `-${lang}.jpg`); });
  document.getElementById("try-bar").src = `assets/bar-${lang}.png`;
  document.getElementById("try-toast").src = `assets/toast30-${lang}.png`;
  const video = document.getElementById("hero-video");
  video.poster = `assets/picker-${lang}.jpg`;
  if (!video.currentSrc.endsWith(`hero-${lang}.mp4`)) { video.querySelector("source").src = `assets/hero-${lang}.mp4`; video.load(); video.play().catch(() => {}); }
  document.getElementById("lang").textContent = lang === "ar" ? "EN" : "ع";
  updatePadStatus();
}
document.getElementById("lang").addEventListener("click", () => { lang = lang === "ar" ? "en" : "ar"; store.set("lang", lang); applyLang(); });

// ---------------------------------------------------------------- try it: once opens, twice saves
// The same rule as the app's PressSequencer: a second press within 350 ms is a double press.
const stage = document.getElementById("stage");
let pending = null, toastTimer = null;
function press() {
  if (pending) { clearTimeout(pending); pending = null; saveLast30(); return; }
  pending = setTimeout(() => { pending = null; toggleMenu(); }, 350);
}
function toggleMenu() { stage.classList.remove("saved"); stage.classList.toggle("open"); }
function saveLast30() {
  stage.classList.remove("open");
  const flash = document.getElementById("try-flash");
  flash.classList.remove("go"); void flash.offsetWidth; flash.classList.add("go");
  stage.classList.add("saved");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => stage.classList.remove("saved"), 3200);
}
document.addEventListener("keydown", (e) => {
  if (e.altKey && (e.code === "KeyC" || e.key.toLowerCase() === "c")) { e.preventDefault(); press(); }
  else if (e.key === "Escape") stage.classList.remove("open");
});
document.getElementById("press-once").addEventListener("click", () => { clearTimeout(pending); pending = null; toggleMenu(); });
document.getElementById("press-twice").addEventListener("click", () => { clearTimeout(pending); pending = null; saveLast30(); });
stage.addEventListener("click", () => { clearTimeout(pending); pending = null; toggleMenu(); });

// controllers: the browser's Gamepad API; in the standard layout button 8 is Create (PlayStation) / View (Xbox)
let lastDown = false;
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
  const down = !!(pad.buttons[8] && pad.buttons[8].pressed);
  if (down && !lastDown) press();
  lastDown = down;
  requestAnimationFrame(poll);
}

// ---------------------------------------------------------------- reveal on scroll
const io = new IntersectionObserver((entries) => entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }),
                                    { threshold: 0.12 });
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));

applyLang();
