// Capture Menu website: English / Arabic, the try-it demo (Alt + C or a controller's Create / View),
// scroll reveals and the official PlayStation and Xbox marks.

const T = {
  en: {
    nav_install: "Install",
    faq_h: "Questions",
    q_perf_h: "Will it slow my game down?",
    q_perf_p: "OBS records on your graphics card, and the last minutes are kept on your drive, not in RAM. Capture Menu itself waits quietly in the tray.",
    q_pads_h: "Which controllers work?",
    q_pads_p: "DualSense, Xbox and most others, plus Alt + C on the keyboard. The buttons on screen match the controller in your hands.",
    q_files_h: "Where do my clips go?",
    q_files_p: "A folder for every game, found by itself. Clips and screenshots can go to different drives, and recording follows your game across monitors and TVs.",
    q_voice_h: "Is my voice recorded?",
    q_voice_p: "If you want. It goes on its own track, so you can make it louder or quieter in any clip later, or leave it out of a copy you share.",
    q_share_h: "How do I share a clip?",
    q_share_p: "Pick Phone & WhatsApp, or Discord at 10, 50 or 500 MB. A copy that fits is made and copied, ready to paste with Ctrl + V.",
    q_safe_h: "Why does my browser or Windows warn me?",
    q_safe_p: "Capture Menu isn't code-signed yet, so Windows can't show a verified publisher. Download it only from the <a href=\"https://github.com/Amjz03/capture-menu/releases/latest\">official release on GitHub</a> and follow the install steps below. A clean virus scan is a good sign, not a guarantee.",
    q_privacy_h: "Does anything leave my PC?",
    q_privacy_p: "Your clips and settings aren't sent anywhere. It talks to OBS on your PC, and asks GitHub for the latest version number to tell you about updates. This website counts visits with GoatCounter, without cookies.",
    q_free_h: "Is it really free?",
    q_free_p: "Yes. Open source under the MIT license, with no account, no ads and no watermark. In English and Arabic.",
    install_h: "Install it in a minute",
    install_p: "Windows 10 or 11. No admin rights needed.",
    i_dl_h: "Download",
    i_dl_p: "Get <a href=\"https://github.com/Amjz03/capture-menu/releases/latest/download/CaptureMenu-Setup.exe\">CaptureMenu-Setup.exe</a>, about 50 MB.",
    i_browser_h: "If your browser warns you",
    i_browser_p: "Capture Menu isn't code-signed yet, so browsers don't recognise it and may warn you. Keep the file only if it came from the <a href=\"https://github.com/Amjz03/capture-menu/releases/latest\">official release page</a>. <b>Chrome:</b> open Downloads and press <span class=\"ui\">Keep</span>. <b>Edge:</b> press <span class=\"ui\">···</span> next to the file, then <span class=\"ui\">Keep</span>, then <span class=\"ui\">Keep anyway</span>.",
    i_smartscreen_h: "If Windows says “Windows protected your PC”",
    i_smartscreen_p: "Without a signature, Windows shows the publisher as unknown. If the file came from the official release, press <span class=\"ui\">More info</span>, then <span class=\"ui\">Run anyway</span>.",
    i_install_h: "Press Install",
    i_install_p: "Setup installs OBS Studio and FFmpeg if you don't have them and sets everything up for your PC. A minute later, press <span class=\"ui\">Alt + C</span> in a game.",
    skip: "Skip to content",
    all_releases: "All releases",
    final_p: "Free for Windows 10 and 11. Setup takes about a minute.",
    f_p: "Saving is one part. The rest of the app is built for what you do next with the clip, with a controller or a mouse.",
    k_close: "close",
    k_save: "save a length",
    k_pick: "pick",
    k_move: "move",
    works_with: "Works with",
    nav_try: "Try it", nav_features: "Features", download_short: "Download",
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
    j_h: "Save it. Trim it. Share it.",
    j1_h: "Save the moment", j1_p: "Press twice, or pick how much to keep from the last 30 minutes.", j1_alt: "The Save recent gameplay row, with Last 30m picked",
    j2_h: "Trim it", j2_p: "Cut it to the frame. The original stays.", j2_alt: "Trimming a clip on a timeline of frames",
    j3_h: "Share it", j3_p: "Press Share / Export, pick Phone or Discord, and a copy that fits is ready to paste.", j3_alt: "The clip viewer, with the Share / Export button selected",
    phone_p: "Capture Menu is for Windows PCs. Try the demo here, and open this link on your computer to install it.", phone_try: "Try the demo",
    phone_copy: "Copy site link", phone_share: "Share link", phone_copied: "Link copied. Open it on your computer.",
    phone_manual: "Copy this link:", phone_failed: "Couldn't copy it. Select the link below and copy it.", phone_share_failed: "Couldn't share it. Select the link below and copy it.",
    alt_picker: "The Save recent gameplay row over Red Dead Redemption 2, with Last 30m picked", alt_library: "The Captures page: a sidebar of games and a grid of clips and screenshots", alt_settings: "The Settings page: resolution, frame rate, quality and replay length", alt_rec: "Red Dead Redemption 2 at night with a small REC 12:34 timer in the corner", alt_game: "Call of Duty on a snowy rooftop, the game the menu opens over",
    whats_new: "What's new", released: "Version {v} · {date}",
    rec_note: "Keeping the last 30 min", anywhere: "Press it anywhere on this page",
    how_h: "How it works", privacy: "Privacy",
    s1_h: "Play", s1_p: "It quietly keeps the last 30 minutes of your game, on any screen, with any graphics card.",
    s2_h: "Press", s2_p: "Once for the menu over your game, to save, take a screenshot or record. Twice to save the last 30 seconds.",
    s3_h: "Keep", s3_p: "Every clip lands in its game's folder, ready to watch, trim and share.",
    f_h: "Everything after the press",
    t1_h: "Pick how much to keep", t1_p: "The last 15 seconds, 1, 3, 5, 15 or 30 minutes, or everything. With the mouse, the keys or the d-pad.",
    t2_h: "Press twice, it's saved", t2_p: "The last 30 seconds, without opening anything.",
    t8_h: "Set up for your PC", t8_p: "Resolution, frame rate, quality and how much to keep, on one page.",
    t4_h: "A folder for every game", t4_p: "Found automatically. Favorites, titles, notes, sizes, sorting.",
    t7_h: "Record for hours", t7_p: "A small REC timer while you record. Screenshots in full resolution.",
    
    
    
    final_h: "Download Capture Menu",
    tm: "PlayStation and Xbox are trademarks of their owners. Capture Menu is not affiliated with Sony or Microsoft.",
    title: "Capture Menu · The PS5 Create button, on your PC",
  },
  ar: {
    nav_install: "التثبيت",
    faq_h: "أسئلة",
    q_perf_h: "هل يبطّئ لعبتي؟",
    q_perf_p: "OBS يسجّل بكرت الشاشة، وآخر الدقائق تُحفظ على القرص لا في الذاكرة. وCapture Menu نفسه ينتظر بهدوء بجانب الساعة.",
    q_pads_h: "أي كنترولر يعمل؟",
    q_pads_p: "DualSense وإكس بوكس وأغلب الأنواع الأخرى، ومعها Alt + C على الكيبورد. والأزرار على الشاشة تطابق الكنترولر الذي في يدك.",
    q_files_h: "أين تذهب مقاطعي؟",
    q_files_p: "مجلد لكل لعبة يعرفها تلقائيًا، ويمكنك حفظ المقاطع ولقطات الشاشة في قرصين مختلفين. والتسجيل يتبع لعبتك بين الشاشات والتلفزيونات.",
    q_voice_h: "هل يسجّل صوتي؟",
    q_voice_p: "إذا أردت. صوتك في مسار منفصل، فيمكنك رفعه أو خفضه في أي مقطع لاحقًا، أو حذفه من النسخة التي تشاركها.",
    q_share_h: "كيف أشارك مقطعًا؟",
    q_share_p: "اختر الجوال وواتساب، أو Discord بحجم 10 أو 50 أو 500 ميجابايت. نجهّز نسخة بالحجم المناسب وننسخها، جاهزة للصق بـ Ctrl + V.",
    q_safe_h: "لماذا يحذّرني المتصفح أو ويندوز؟",
    q_safe_p: "لأن Capture Menu ما زال بدون توقيع رقمي، فلا يعرض ويندوز ناشرًا موثّقًا. نزّله فقط من <a href=\"https://github.com/Amjz03/capture-menu/releases/latest\">صفحة الإصدار الرسمية على GitHub</a> وتابع خطوات التثبيت في الأسفل. ونتيجة فحص الفيروسات النظيفة علامة جيدة، لكنها ليست ضمانًا.",
    q_privacy_h: "هل يخرج شيء من جهازي؟",
    q_privacy_p: "لا نرسل مقاطعك ولا إعداداتك إلى أي مكان. البرنامج يتصل بـ OBS على جهازك، ويسأل GitHub عن رقم آخر إصدار لينبّهك بالتحديثات. وهذا الموقع يعدّ الزيارات بـ GoatCounter بدون كوكيز.",
    q_free_h: "هل هو مجاني فعلًا؟",
    q_free_p: "نعم. مفتوح المصدر برخصة MIT، بدون حساب أو إعلانات أو علامة مائية، وبالعربية والإنجليزية.",
    install_h: "ثبّته في دقيقة",
    install_p: "ويندوز 10 أو 11، وبدون صلاحيات المسؤول.",
    i_dl_h: "نزّله",
    i_dl_p: "نزّل <a href=\"https://github.com/Amjz03/capture-menu/releases/latest/download/CaptureMenu-Setup.exe\">CaptureMenu-Setup.exe</a>، وحجمه حوالي 50 ميجابايت.",
    i_browser_h: "إذا حذّرك المتصفح",
    i_browser_p: "Capture Menu ما زال بدون توقيع رقمي، لذلك قد لا تعرفه المتصفحات وتحذّرك منه. احتفظ بالملف فقط إذا نزّلته من <a href=\"https://github.com/Amjz03/capture-menu/releases/latest\">صفحة الإصدار الرسمية</a>. <b>كروم:</b> افتح التنزيلات واضغط <span class=\"ui\">الاحتفاظ</span>. <b>إيدج:</b> اضغط <span class=\"ui\">···</span> بجانب الملف، ثم <span class=\"ui\">الاحتفاظ</span>، ثم <span class=\"ui\">الاحتفاظ على أي حال</span>.",
    i_smartscreen_h: "إذا ظهرت رسالة «قام Windows بحماية الكمبيوتر»",
    i_smartscreen_p: "بدون توقيع، يعرض ويندوز الناشر على أنه غير معروف. إذا نزّلت الملف من صفحة الإصدار الرسمية، اضغط <span class=\"ui\">مزيد من المعلومات</span>، ثم <span class=\"ui\">تشغيل على أي حال</span>.",
    i_install_h: "اضغط تثبيت",
    i_install_p: "اضغط <span class=\"ui\">Install</span> في ملف التثبيت، وهو يثبّت OBS Studio وFFmpeg إذا لم يكونا عندك ويضبط كل شيء على جهازك. وبعد دقيقة، اضغط <span class=\"ui\">Alt + C</span> في أي لعبة.",
    skip: "انتقل إلى المحتوى",
    all_releases: "كل الإصدارات",
    final_p: "مجاني لويندوز 10 و11، والتثبيت يأخذ دقيقة تقريبًا.",
    f_p: "الحفظ جزء واحد. باقي البرنامج مصمّم لما تعمله بالمقطع بعدها، بالكنترولر أو بالماوس.",
    k_close: "إغلاق",
    k_save: "حفظ مدة",
    k_pick: "اختيار",
    k_move: "تنقّل",
    works_with: "يعمل مع",
    nav_try: "جرّبه", nav_features: "المميزات", download_short: "تنزيل",
    kicker: "مجاني ومفتوح المصدر، لويندوز 10 و11",
    h1: "زر Create من PS5، <span>على الكمبيوتر.</span>",
    lede: "Capture Menu يحتفظ بآخر 30 دقيقة من أي لعبة. اضغط مرة واختر ما تحفظه، أو اضغط مرتين ويحفظ آخر 30 ثانية.",
    download: "نزّله لويندوز", github: "الكود على GitHub",
    fine: "حوالي 50 ميجابايت، بدون حساب أو إعلانات. ملف التثبيت يجهّز لك OBS وFFmpeg.",
    ago: "قبل 30 دقيقة", now: "الآن", more_pads: "ومعظم الكنترولرات الأخرى",
    try_h: "جرّب القائمة",
    try_p: "هذه القائمة الحقيقية، داخل الصفحة. اضغط Alt + C مرة لتفتحها، وتنقّل بالأسهم أو بالماوس، واختر بـ Enter. اضغط مرتين ويحفظ آخر 30 ثانية. والكنترولر الموصّل بالكمبيوتر يعمل أيضًا.",
    page_hint: "اضغط هنا أو Esc للرجوع",
    buf_q: "كم تريد أن تحفظ؟",
    try_hint: "اضغط Alt + C، أو اضغط هنا",
    press_once: "اضغط مرة", press_twice: "اضغط مرتين",
    pad_none: "لا يوجد كنترولر. وصّل واحدًا واضغط أي زر.",
    pad_on: "الكنترولر جاهز: {name}. اضغط Create / View.",
    j_h: "احفظها. قصّها. شاركها.",
    j1_h: "احفظ اللقطة", j1_p: "اضغط مرتين، أو اختر كم تحفظ من آخر 30 دقيقة.", j1_alt: "صف حفظ اللعب الأخير، والمختار آخر 30 دقيقة",
    j2_h: "قصّها", j2_p: "قص الفيديو بدقة، والأصلي يبقى كما هو.", j2_alt: "قص مقطع على شريط من الفريمات",
    j3_h: "شاركها", j3_p: "اضغط «مشاركة وتصدير»، واختر الجوال أو Discord، فتجهز نسخة بالحجم المناسب جاهزة للصق.", j3_alt: "عارض المقاطع، وزر «مشاركة وتصدير» محدد",
    phone_p: "Capture Menu برنامج لكمبيوترات ويندوز. جرّب العرض هنا، وافتح الرابط على الكمبيوتر للتثبيت.", phone_try: "جرّب العرض",
    phone_copy: "انسخ رابط الموقع", phone_share: "مشاركة الرابط", phone_copied: "تم نسخ الرابط. افتحه على الكمبيوتر.",
    phone_manual: "انسخ هذا الرابط:", phone_failed: "لم ينجح النسخ. حدّد الرابط في الأسفل وانسخه.", phone_share_failed: "لم تنجح المشاركة. حدّد الرابط في الأسفل وانسخه.",
    alt_picker: "صف حفظ اللعب الأخير فوق Red Dead Redemption 2، والمختار آخر 30 دقيقة", alt_library: "صفحة المعرض: الألعاب على الجانب وشبكة من المقاطع ولقطات الشاشة", alt_settings: "صفحة الإعدادات: الدقة وعدد الفريمات والجودة ومدة الفيديو", alt_rec: "Red Dead Redemption 2 ليلًا، وفي الزاوية مؤقت REC 12:34 صغير", alt_game: "Call of Duty فوق سطح عليه ثلج، وهي اللعبة التي تفتح القائمة فوقها",
    whats_new: "ما الجديد", released: "الإصدار {v} · {date}",
    rec_note: "يحتفظ بآخر 30 دقيقة", anywhere: "اضغطه في أي مكان من الصفحة",
    how_h: "كيف يعمل", privacy: "الخصوصية",
    s1_h: "العب", s1_p: "يحتفظ بآخر 30 دقيقة من لعبك في الخلفية، على أي شاشة ومع أي كرت شاشة.",
    s2_h: "اضغط", s2_p: "مرة لتظهر القائمة فوق اللعبة، للحفظ أو تصوير الشاشة أو التسجيل. ومرتين ويحفظ آخر 30 ثانية.",
    s3_h: "احتفظ", s3_p: "كل مقطع يذهب إلى مجلد لعبته، جاهزًا للمشاهدة والقص والمشاركة.",
    f_h: "كل ما بعد الضغطة",
    t1_h: "اختر كم تحفظ", t1_p: "آخر 15 ثانية، أو 1 أو 3 أو 5 أو 15 أو 30 دقيقة، أو كل شيء. بالماوس أو الكيبورد أو أسهم الكنترولر.",
    t2_h: "اضغط مرتين ليُحفظ", t2_p: "آخر 30 ثانية، بدون فتح أي شيء.",
    t8_h: "مضبوط على جهازك", t8_p: "الدقة وعدد الفريمات والجودة ومدة الفيديو، كلها في صفحة واحدة.",
    t4_h: "مجلد لكل لعبة", t4_p: "يعرفها تلقائيًا، مع المفضلة والعناوين والملاحظات والأحجام والترتيب.",
    t7_h: "سجّل لساعات", t7_p: "مؤقت REC صغير وقت التسجيل، ولقطات شاشة بدقة كاملة.",
    
    
    
    final_h: "نزّل Capture Menu",
    tm: "PlayStation وXbox علامتان تجاريتان لمالكيهما، ولا علاقة لـ Capture Menu بسوني أو مايكروسوفت.",
    title: "Capture Menu · زر Create من PS5، على الكمبيوتر",
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
  const manual = document.getElementById("manual-input");
  if (manual && manual.value) manual.value = siteLink();
  if (copyStatus) copyStatus.textContent = "";
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
  if (lang === "ar") return s < 60 ? `آخر ${s} ثانية` : s === 60 ? "آخر دقيقة" : s <= 600 ? `آخر ${s / 60} دقائق` : `آخر ${s / 60} دقيقة`;
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
  // the demo's keys work from anywhere, except on another control: Enter on a link or a question is theirs
  const other = e.target.closest?.("a, button, summary, input, select, textarea");
  if (other && !other.closest("#try")) return;      // the demo's own buttons (Press once / twice) keep driving it
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

// ---------------------------------------------------------------- visitors and downloads (GoatCounter)
// Page views are counted by GoatCounter's script, without cookies. Two events on top:
// "new-device" once per browser (a flag in localStorage, no ID is sent), so it counts devices, not
// visits; and "download" for every click on a Setup.exe link (GitHub counts the downloads themselves).
function count(path, title) {
  const send = (tries) => {
    if (window.goatcounter && window.goatcounter.count) { window.goatcounter.count({ path, title, event: true }); return true; }
    if (tries) setTimeout(() => send(tries - 1), 1000);   // its script loads after this one
    return false;
  };
  send(10);
}
if (!store.get("seen")) {
  store.set("seen", "1");
  if (store.get("seen")) count("new-device", "New device");   // only where it's remembered: private windows that forget it aren't counted every time
}
document.addEventListener("click", (e) => {
  if (e.target.closest('a[href$="CaptureMenu-Setup.exe"]')) count("download", "Download Setup.exe");
});

// ---------------------------------------------------------------- on a phone: the link, for the computer
// The site's own address (never the .exe), in the visitor's language. Copy says so when it worked;
// when it can't, the link shows in a field to copy by hand. Share only where the browser has it.
const SITE = "https://amjz03.github.io/capture-menu/";
// A phone or tablet, and never Windows: a touch screen on a Windows PC (or a Surface in tablet mode)
// can install Capture Menu, so it gets the normal download. iPadOS says "Macintosh", so a Mac
// with touch points counts as a tablet.
function isPhoneVisitor({ ua, platform, touchPoints }) {
  if (/windows/i.test(platform) || /Windows/.test(ua)) return false;
  if (/Android|iPhone|iPad|iPod/.test(ua)) return true;
  return /Macintosh/.test(ua) && touchPoints > 0;     // an iPad asking for the desktop site (Macs have no touch)
}
document.documentElement.classList.toggle("phone", isPhoneVisitor({
  ua: navigator.userAgent, platform: (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "",
  touchPoints: navigator.maxTouchPoints || 0,
}));
const siteLink = () => SITE + (lang === "ar" ? "?lang=ar" : "");
const copyStatus = document.getElementById("copy-status");
function showManual() {
  const input = document.getElementById("manual-input");
  input.value = siteLink();
  document.getElementById("manual-link").hidden = false;
  input.focus({ preventScroll: true }); input.select();
}
document.getElementById("copy-link").addEventListener("click", async () => {
  document.getElementById("manual-link").hidden = true;
  try {
    if (!navigator.clipboard || !window.isSecureContext) throw new Error("no clipboard");
    await navigator.clipboard.writeText(siteLink());
    copyStatus.textContent = T[lang].phone_copied;
  } catch {
    copyStatus.textContent = T[lang].phone_failed;
    showManual();
  }
});
const shareBtn = document.getElementById("share-link");
shareBtn.hidden = !navigator.share;
shareBtn.addEventListener("click", async () => {
  try { await navigator.share({ title: "Capture Menu", text: T[lang].phone_p, url: siteLink() }); }
  catch (e) { if (e.name !== "AbortError") { copyStatus.textContent = T[lang].phone_share_failed; showManual(); } }   // closing the share sheet isn't a failure
});

// a link to a question (the footer's Privacy) opens it
const openAsked = () => { const d = location.hash && document.querySelector(`details${location.hash}`); if (d) d.open = true; };
addEventListener("hashchange", openAsked); openAsked();

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
