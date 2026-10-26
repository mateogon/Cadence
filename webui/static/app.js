"use strict";
/* Cadence web reader prototype. Python side: webui/api.py (pywebview js_api). */

const VIEWS = [["study", "Study"], ["page", "Page"], ["focus", "Focus"], ["rsvp", "One word"]];
const S = {
  screen: "library", settings: null, books: [], book: null, ch: 0, data: null,
  starts: [], ends: [], spans: [], words: [], paraOf: [], cur: -1,
  textEl: null, focusPara: null, userScrollUntil: 0, pop: null, drawer: false,
  lag: [], lastReport: 0, lastSave: 0, debug: false,
};
const audio = new Audio();
audio.preload = "auto";
audio.preservesPitch = true;
audio.webkitPreservesPitch = true;

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const icon = (id, size) => `<svg class="i"${size ? ` style="width:${size}px;height:${size}px"` : ""}><use href="#${id}"/></svg>`;
const api = () => window.pywebview.api;
function clock(sec) { sec = Math.max(0, Math.floor(sec || 0)); const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60; return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(s).padStart(2, "0")}`; }
function hue(text) { let h = 0; for (const c of String(text)) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h % 360; }
function coverStyle(book) { return book.cover_url ? `background-image:url('${esc(book.cover_url)}')` : `background:linear-gradient(160deg,hsl(${hue(book.title)} 70% 70%),hsl(${(hue(book.title) + 30) % 360} 55% 38%))`; }
const ACCENTS = { a: "US English", b: "UK English", e: "Spanish", f: "French", h: "Hindi", i: "Italian", j: "Japanese", p: "Portuguese", z: "Chinese" };
function voiceLabel(voice, backend) {
  // Kokoro IDs look like af_heart: language, gender, name.
  const m = /^([a-z])([fm])_(.+)$/.exec(voice || "");
  if (backend !== "kokoro" || !m) return { name: voice || "—", detail: "" };
  return { name: m[3].replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()), detail: `${ACCENTS[m[1]] || ""} · ${m[2] === "f" ? "female" : "male"}` };
}
function toast(text) { const t = document.createElement("div"); t.className = "toast"; t.textContent = text; document.body.appendChild(t); setTimeout(() => t.remove(), 3500); }
async function call(name, ...args) { try { return await api()[name](...args); } catch (e) { toast(e.message || String(e)); throw e; } }

// ------------------------------------------------------------------ settings

function applySettings() {
  const s = S.settings, root = document.documentElement;
  root.dataset.theme = s.theme;
  root.style.setProperty("--fs", s.font_size + "px");
  root.style.setProperty("--lh", s.line_height);
  audio.playbackRate = s.playback_speed;
  audio.volume = s.volume;
}
let saveSettingsTimer = null;
function setSetting(changes, rerender = false) {
  Object.assign(S.settings, changes);
  applySettings();
  clearTimeout(saveSettingsTimer);
  saveSettingsTimer = setTimeout(() => call("save_settings", changes).catch(() => {}), 300);
  if (rerender) renderReader(); else refreshControls();
}

// ------------------------------------------------------------------ library

async function showLibrary() {
  savePosition(true);
  audio.pause();
  S.screen = "library";
  S.books = await call("books");
  const cards = S.books.map((b) => {
    const pct = b.chapters ? Math.round(100 * Math.max(0, b.current_chapter - 1) / b.chapters) : 0;
    const status = b.ready < b.chapters ? `${b.ready} of ${b.chapters} chapters ready` : b.current_chapter ? `Chapter ${b.current_chapter} of ${b.chapters}` : `${b.chapters} chapters · not started`;
    return `<button class="tile" data-open="${esc(b.id)}"><div class="cv" style="${coverStyle(b)}">${b.cover_url ? "" : esc(b.title)}</div>
      <div class="t">${esc(b.title)}</div><div class="a">${esc(b.author)}</div>
      ${b.current_chapter ? `<div class="pbar"><i style="width:${pct}%"></i></div>` : ""}<div class="st">${esc(status)}</div></button>`;
  }).join("");
  $("#app").innerHTML = `<div class="head"><div class="brand"><span class="logo">${icon("book", 15)}</span>Cadence</div><div class="ttl"></div><span class="muted small">Web reader prototype</span><button class="ib" data-act="theme-cycle" title="Theme">${icon(S.settings.theme === "dark" ? "sun" : "moon", 18)}</button></div>
    <div class="lib"><div class="wrap"><h1>Library</h1><div class="muted">${S.books.length} books</div>
    ${S.books.length ? `<div class="grid">${cards}</div>` : `<div class="empty">No books yet. Import one with the Qt app for now.</div>`}</div></div>`;
}

// ------------------------------------------------------------------ book & chapter loading

async function openBook(id) {
  S.book = await call("book", id);
  const chapters = S.book.chapters;
  let index = Math.max(0, S.book.resume_chapter - 1);
  if (!chapters[index]?.ready) index = Math.max(0, chapters.findIndex((c) => c.ready));
  S.screen = "reader";
  await loadChapter(index, (S.book.resume_ms[chapters[index].stem] || 0) / 1000, false);
}

async function loadChapter(index, startAt = 0, autoplay = false) {
  const chapter = S.book.chapters[index];
  if (!chapter?.ready) { toast("This chapter is not ready yet."); return; }
  savePosition(true);
  S.ch = index;
  S.data = await call("chapter", S.book.id, chapter.stem);
  buildText(S.data.tokens);
  audio.src = S.data.audio_url;
  audio.playbackRate = S.settings.playback_speed;
  await new Promise((resolve) => { audio.addEventListener("loadedmetadata", resolve, { once: true }); audio.load(); });
  audio.currentTime = Math.min(startAt, Math.max(0, audio.duration - 0.5));
  S.cur = -1;
  renderReader();
  syncTo(audio.currentTime, true);
  if (autoplay) audio.play();
}

function buildText(tokens) {
  // Tokens include whitespace; a token with a newline ends a paragraph.
  const root = document.createElement("div");
  root.className = "reading";
  let p = document.createElement("p"), paraIndex = 0, timed = 0, paraHasWords = false;
  S.starts = []; S.ends = []; S.spans = []; S.words = []; S.paraOf = [];
  const paragraphs = [p];
  const flush = () => { if (paraHasWords) { root.appendChild(p); p = document.createElement("p"); paragraphs.push(p); paraIndex++; paraHasWords = false; } };
  for (const [word, start, end] of tokens) {
    if (!word.trim()) { if (word.includes("\n")) flush(); else if (paraHasWords) p.appendChild(document.createTextNode(" ")); continue; }
    const span = document.createElement("span");
    span.className = "w";
    span.textContent = word;
    if (start !== null) {
      span.dataset.k = timed++;
      S.starts.push(start); S.ends.push(end); S.spans.push(span); S.words.push(word); S.paraOf.push(paraIndex);
    }
    p.appendChild(span);
    paraHasWords = true;
  }
  flush();
  // A short first paragraph without final punctuation is the chapter heading.
  const first = root.firstElementChild;
  if (first && first.textContent.length <= 80 && !/[.!?,;]$/.test(first.textContent.trim())) first.classList.add("h");
  S.textEl = root;
  S.paragraphs = [...root.children];
}

// ------------------------------------------------------------------ sync

function indexAt(t) {
  const a = S.starts;
  if (!a.length || t < a[0]) return a.length ? 0 : -1;
  let lo = 0, hi = a.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (a[mid] <= t) lo = mid; else hi = mid - 1; }
  return lo;
}

function syncTo(t, jump = false) {
  const i = indexAt(t - S.settings.sync_offset_ms / 1000);
  if (i < 0 || i === S.cur) return;
  const prev = S.cur;
  S.spans[prev]?.classList.remove("on");
  S.spans[i].classList.add("on");
  S.cur = i;
  onWordChange(i, prev, jump || i !== prev + 1);
}

function tick() {
  requestAnimationFrame(tick);
  if (S.screen !== "reader" || !S.starts.length) return;
  if (!audio.paused) {
    const t = audio.currentTime - S.settings.sync_offset_ms / 1000;
    const i = indexAt(t);
    if (i !== S.cur && i === S.cur + 1 && S.cur >= 0) S.lag.push((t - S.starts[i]) * 1000);
    syncTo(audio.currentTime);
    const now = performance.now();
    if (now - S.lastReport > 10000 && S.lag.length >= 30) reportSync();
    if (now - S.lastSave > 5000) savePosition();
    // WebKit sometimes stalls on the last frame without firing "ended".
    if (audio.duration && audio.currentTime >= audio.duration - 0.05) {
      S.atEndSince = S.atEndSince || now;
      if (now - S.atEndSince > 500) chapterEnded();
    } else S.atEndSince = 0;
  }
  refreshTime();
}

function stats(values) {
  const v = [...values].sort((x, y) => x - y), q = (p) => v[Math.min(v.length - 1, Math.floor(p * v.length))];
  return { n: v.length, median_ms: +q(0.5).toFixed(1), p95_ms: +q(0.95).toFixed(1), max_ms: +v[v.length - 1].toFixed(1) };
}
function reportSync() {
  S.lastReport = performance.now();
  const s = stats(S.lag);
  api().report_sync({ view: S.settings.view, rate: audio.playbackRate, ...s }).catch(() => {});
  if (S.debug) $("#dbg").textContent = `highlight lag after word start\nview ${S.settings.view} · rate ${audio.playbackRate}×\nn ${s.n}  median ${s.median_ms} ms\np95 ${s.p95_ms} ms  max ${s.max_ms} ms`;
}

function onWordChange(i, prev, jump) {
  const view = S.settings.view;
  if (view === "rsvp") return showRsvpWord(i);
  if (view === "focus") {
    const para = S.spans[i].closest("p");
    if (para !== S.focusPara) { S.focusPara?.classList.remove("cur"); para.classList.add("cur"); S.focusPara = para; }
    markLater(i, prev, jump);
    const stage = $(".stage"), r = para.getBoundingClientRect(), b = stage.getBoundingClientRect();
    stage.scrollBy({ top: r.top + r.height / 2 - (b.top + b.height * 0.45), behavior: jump ? "auto" : "smooth" });
    return;
  }
  if (performance.now() < S.userScrollUntil) return;
  const stage = $(".stage"), w = S.spans[i];
  if (!stage || !w) return;
  const r = w.getBoundingClientRect(), b = stage.getBoundingClientRect();
  if (jump || r.top < b.top + b.height * 0.2 || r.bottom > b.top + b.height * 0.72)
    stage.scrollBy({ top: r.top - (b.top + b.height * 0.36), behavior: jump ? "auto" : "smooth" });
}

function markLater(i, prev, jump) {
  // Focus view dims the words after the current one inside the current paragraph.
  if (jump) { S.spans.forEach((s, k) => s.classList.toggle("later", k > i)); return; }
  S.spans[i]?.classList.remove("later");
}

function showRsvpWord(i) {
  const raw = S.words[i], core = raw.replace(/^[“"‘'(\[]+|[”"’',.;:!?)\]…]+$/g, "") || raw;
  const lead = raw.indexOf(core), o = core.length <= 1 ? 0 : core.length <= 5 ? 1 : core.length <= 9 ? 2 : core.length <= 13 ? 3 : 4;
  const el = $("#rsvpWord");
  if (!el) return;
  el.innerHTML = esc(raw.slice(0, lead + o)) + `<span class="o">${esc(raw[lead + o] || "")}</span>` + esc(raw.slice(lead + o + 1));
  el.style.left = "0px";
  const span = el.querySelector(".o"), guide = el.parentElement.clientWidth * 0.4;
  el.style.left = guide - (span.offsetLeft + span.offsetWidth / 2) + "px";
  let s = i; while (s > 0 && !/[.!?…]["”’)]*$/.test(S.words[s - 1])) s--;
  let e = i; while (e < S.words.length - 1 && !/[.!?…]["”’)]*$/.test(S.words[e]) && e - s < 60) e++;
  $("#rsvpCtx").innerHTML = S.words.slice(s, e + 1).map((t, k) => `<span class="${s + k < i ? "past" : s + k === i ? "on" : ""}">${esc(t)}</span>`).join(" ");
}

function savePosition(force = false) {
  if (!S.book || !S.data) return;
  const now = performance.now();
  if (!force && now - S.lastSave < 5000) return;
  S.lastSave = now;
  const chapter = S.book.chapters[S.ch];
  const ms = Math.round(audio.currentTime * 1000);
  S.book.resume_ms[chapter.stem] = ms;
  api().save_position(S.book.id, chapter.stem, ms, chapter.number).catch(() => {});
}

// ------------------------------------------------------------------ rendering

function switcher() {
  return `<div class="seg">${VIEWS.map(([id, label]) => `<button class="${S.settings.view === id ? "on" : ""}" data-view="${id}">${label}</button>`).join("")}</div>`;
}
function header(extra = "") {
  const ch = S.book.chapters[S.ch];
  return `<div class="head"><button class="ib" data-act="library" title="Library (Esc)">${icon("left")}</button>
    ${S.settings.view === "study" ? `<div class="brand"><span class="logo">${icon("book", 15)}</span>Cadence</div>` : ""}
    <div class="ttl"><b>${esc(S.book.title)}</b> · ${esc(ch.title)}</div>${switcher()}
    <button class="ib" data-act="theme-cycle" title="Theme: ${THEME_LABEL[S.settings.theme]} (T)">${icon(S.settings.theme === "dark" ? "sun" : "moon", 18)}</button>${extra}</div>`;
}
function playerHtml(compact = false) {
  const ch = S.book.chapters[S.ch], hasPrev = S.book.chapters.slice(0, S.ch).some((c) => c.ready), hasNext = S.book.chapters.slice(S.ch + 1).some((c) => c.ready);
  const controls = `<div class="ctl"><button data-act="prev-ch" ${hasPrev ? "" : "disabled"} title="Previous chapter">${icon("prev", 18)}</button>
      <button data-act="back" title="Back 15 s (←)">${icon("b15", 20)}</button><button class="play" data-act="play" title="Play / pause (space)">${icon(audio.paused ? "play" : "pause", 20)}</button>
      <button data-act="fwd" title="Forward 15 s (→)">${icon("f15", 20)}</button><button data-act="next-ch" ${hasNext ? "" : "disabled"} title="Next chapter">${icon("next", 18)}</button></div>`;
  const scrub = `<div class="scrub"><span id="tEl">0:00</span><input type="range" id="seek" min="0" max="1000" value="0" aria-label="Position"><span id="tRem">0:00</span></div>`;
  const speed = `<button class="sp" data-act="speed" title="Speed">${S.settings.playback_speed}×</button>`;
  const volume = `<div class="vol"><button data-act="mute" title="Mute (M)">${icon(volumeIcon(), 18)}</button><input type="range" id="vol" min="0" max="100" value="${Math.round(S.settings.volume * 100)}" aria-label="Volume"></div>`;
  if (compact) return `<div class="player">${controls}${scrub}<div class="ctl">${volume}${speed}</div></div>`;
  return `<div class="player"><div class="np"><div class="mini" style="${coverStyle(S.book)}"></div><div><b>${esc(ch.title)}</b><small>${esc(S.book.title)}</small></div></div>
    <div class="mid">${controls}${scrub}</div><div class="rt">${volume}${speed}</div></div>`;
}
function volumeIcon() { return audio.muted || S.settings.volume === 0 ? "volx" : S.settings.volume < 0.5 ? "vol1" : "vol2"; }
function chaptersHtml() {
  const ready = S.book.chapters.filter((c) => c.ready).length;
  return `<div class="h"><b>${esc(S.book.title)}</b><div class="muted small">${S.book.chapters.length} chapters · ${ready} ready</div></div>` +
    S.book.chapters.map((c, k) => `<button class="ch ${k === S.ch ? "cur" : ""}" data-ch="${k}" ${c.ready ? "" : "disabled"}>
      ${c.ready ? `<span class="ok">${icon("check", 10)}</span>` : `<span class="wait"></span>`}<span class="t">${esc(c.title)}</span><span class="s">${c.seconds ? clock(c.seconds) : "waiting"}</span></button>`).join("");
}
function appearanceHtml() {
  const s = S.settings;
  const theme = (id, bg, fg, border = "") => `<button data-set-theme="${id}" class="${s.theme === id ? "on" : ""}" style="background:${bg};color:${fg};${border}"><span>Aa</span><small>${THEME_LABEL[id]}</small></button>`;
  return `<div class="box"><div class="lbl">Theme</div><div class="themes">${theme("light", "#fff", "#111", "border-color:#e4e4e7")}${theme("sepia", "#f8f1e3", "#4a3a2a")}${theme("dark", "#151517", "#eee")}</div>
      <div class="steps"><span class="muted">Text size</span><div class="seg"><button data-act="size" data-v="-1">A−</button><button data-act="size" data-v="1">A+</button></div></div>
      <div class="steps"><span class="muted">Line spacing</span><div class="seg"><button data-act="lh" data-v="-0.1">−</button><button data-act="lh" data-v="0.1">+</button></div></div></div>
    <div class="box"><div class="lbl">Sync adjust<span id="offV">${s.sync_offset_ms > 0 ? "+" : ""}${s.sync_offset_ms} ms</span></div>
      <input class="range" type="range" id="offset" min="-300" max="300" step="10" value="${s.sync_offset_ms}">
      <div class="muted small">Moves the highlight earlier (−) or later (+) than the voice.</div></div>`;
}

function renderReader() {
  const view = S.settings.view, app = $("#app");
  S.focusPara = null;
  S.spans.forEach((s) => s.classList.remove("later"));
  S.paragraphs?.forEach((p) => p.classList.remove("cur"));
  if (view === "study") {
    app.innerHTML = `<div class="study">${header()}<aside class="chlist">${chaptersHtml()}</aside>
      <main class="stage"><div class="sheet" id="host"></div></main>
      <aside class="insp"><div class="box"><div class="lbl">Voice<span>${S.book.backend === "kokoro" ? "Kokoro" : "Supertonic"}</span></div><b>${esc(voiceLabel(S.book.voice, S.book.backend).name)}</b><div class="muted small">${esc(voiceLabel(S.book.voice, S.book.backend).detail || S.book.language || "")}</div><div class="muted small">${S.book.backend === "kokoro" ? "Word timing from the voice" : "Word timing from WhisperX"}</div></div>${appearanceHtml()}</aside>
      ${playerHtml()}</div>`;
  } else if (view === "page") {
    app.innerHTML = `<div class="pagev">${header(`<button class="ib" data-act="drawer" title="Chapters">${icon("list")}</button><button class="ib" data-act="pop" title="Appearance">${icon("aa")}</button>`)}
      <main class="stage"><div class="col" id="host"></div></main>${playerHtml(true)}
      ${S.drawer ? `<aside class="drawer">${chaptersHtml()}</aside>` : ""}${S.pop ? `<div class="pop">${appearanceHtml()}</div>` : ""}</div>`;
  } else if (view === "focus") {
    app.innerHTML = `<div class="focusv">${header()}<main class="stage"><div class="col" id="host"></div></main><div class="dock">${playerHtml(true)}</div></div>`;
  } else {
    app.innerHTML = `<div class="rsvpv">${header(`<button class="ib" data-act="pop" title="Appearance">${icon("aa")}</button>`)}
      <div class="stage"><div class="frame"><div class="word" id="rsvpWord"></div></div></div><div class="ctx" id="rsvpCtx"></div><div class="dock">${playerHtml(true)}</div>
      ${S.pop ? `<div class="pop">${appearanceHtml()}</div>` : ""}</div>`;
  }
  const host = $("#host");
  if (host) host.appendChild(S.textEl);
  $(".stage")?.addEventListener("wheel", () => { S.userScrollUntil = performance.now() + 4000; }, { passive: true });
  bindRanges();
  if (S.cur >= 0) { const k = S.cur; S.cur = -1; S.spans[k]?.classList.remove("on"); syncTo(audio.currentTime, true); }
  if (S.debug) showDebug(true);
}

function bindRanges() {
  const seek = $("#seek");
  if (seek) {
    seek.addEventListener("input", () => { S.seeking = true; $("#tEl").textContent = clock(seek.value / 1000 * audio.duration); });
    seek.addEventListener("change", () => { audio.currentTime = seek.value / 1000 * audio.duration; S.seeking = false; syncTo(audio.currentTime, true); });
  }
  const vol = $("#vol");
  if (vol) vol.addEventListener("input", () => { audio.muted = false; setSetting({ volume: Number(vol.value) / 100 }); });
  const offset = $("#offset");
  if (offset) offset.addEventListener("input", () => { setSetting({ sync_offset_ms: Number(offset.value) }); $("#offV").textContent = `${offset.value > 0 ? "+" : ""}${offset.value} ms`; });
}

function refreshTime() {
  if (!audio.duration) return;
  const el = $("#tEl"), rem = $("#tRem"), seek = $("#seek");
  if (el && !S.seeking) el.textContent = clock(audio.currentTime);
  if (rem) rem.textContent = "−" + clock((audio.duration - audio.currentTime) / audio.playbackRate);
  if (seek && !S.seeking) seek.value = Math.round(1000 * audio.currentTime / audio.duration);
}
function refreshControls() {
  document.querySelectorAll("[data-act=play]").forEach((b) => (b.innerHTML = icon(audio.paused ? "play" : "pause", 20)));
  document.querySelectorAll("[data-act=speed]").forEach((b) => (b.textContent = S.settings.playback_speed + "×"));
  document.querySelectorAll("[data-act=mute]").forEach((b) => (b.innerHTML = icon(volumeIcon(), 18)));
  document.querySelectorAll("#vol").forEach((r) => (r.value = audio.muted ? 0 : Math.round(S.settings.volume * 100)));
  document.querySelectorAll("[data-act=theme-cycle]").forEach((b) => { b.innerHTML = icon(S.settings.theme === "dark" ? "sun" : "moon", 18); b.title = `Theme: ${THEME_LABEL[S.settings.theme]} (T)`; });
  document.querySelectorAll("[data-set-theme]").forEach((b) => b.classList.toggle("on", b.dataset.setTheme === S.settings.theme));
}
function showDebug(on) {
  S.debug = on;
  $("#dbg")?.remove();
  if (on) { const d = document.createElement("div"); d.id = "dbg"; d.className = "dbg"; d.textContent = "measuring highlight lag…"; document.body.appendChild(d); }
}

// ------------------------------------------------------------------ actions

const THEME_LABEL = { light: "Light", sepia: "Sepia", dark: "Dark" };
const THEMES = ["light", "sepia", "dark"];
const SPEEDS = [0.8, 1, 1.1, 1.25, 1.5, 1.75, 2];
const actions = {
  library: () => showLibrary(),
  play: () => (audio.paused ? audio.play() : audio.pause()),
  back: () => { audio.currentTime = Math.max(0, audio.currentTime - 15); syncTo(audio.currentTime, true); },
  fwd: () => { audio.currentTime = Math.min(audio.duration - 0.1, audio.currentTime + 15); syncTo(audio.currentTime, true); },
  speed: () => setSetting({ playback_speed: SPEEDS[(SPEEDS.indexOf(S.settings.playback_speed) + 1) % SPEEDS.length] }),
  "prev-ch": () => { for (let k = S.ch - 1; k >= 0; k--) if (S.book.chapters[k].ready) return loadChapter(k, 0, !audio.paused); },
  "next-ch": () => { for (let k = S.ch + 1; k < S.book.chapters.length; k++) if (S.book.chapters[k].ready) return loadChapter(k, 0, !audio.paused); },
  size: (el) => setSetting({ font_size: Math.max(14, Math.min(36, S.settings.font_size + Number(el.dataset.v))) }),
  lh: (el) => setSetting({ line_height: Math.round(Math.max(1.3, Math.min(2.2, S.settings.line_height + Number(el.dataset.v))) * 10) / 10 }),
  mute: () => { audio.muted = !audio.muted; if (!audio.muted && S.settings.volume === 0) setSetting({ volume: 0.6 }); refreshControls(); },
  "theme-cycle": () => setSetting({ theme: THEMES[(THEMES.indexOf(S.settings.theme) + 1) % THEMES.length] }),
  pop: () => { S.pop = !S.pop; S.drawer = false; renderReader(); },
  drawer: () => { S.drawer = !S.drawer; S.pop = false; renderReader(); },
};

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act],[data-view],[data-set-theme],[data-ch],[data-open],.reading .w[data-k]");
  if (!el || el.disabled) return;
  if (el.dataset.open) return openBook(el.dataset.open);
  if (el.dataset.view) { S.pop = false; S.drawer = false; return setSetting({ view: el.dataset.view }, true); }
  if (el.dataset.setTheme) return setSetting({ theme: el.dataset.setTheme });
  if (el.dataset.ch) { S.drawer = false; return loadChapter(Number(el.dataset.ch), (S.book.resume_ms[S.book.chapters[el.dataset.ch].stem] || 0) / 1000, !audio.paused); }
  if (el.dataset.k !== undefined) { audio.currentTime = S.starts[Number(el.dataset.k)] + S.settings.sync_offset_ms / 1000 + 0.001; syncTo(audio.currentTime, true); return; }
  actions[el.dataset.act]?.(el);
});
document.addEventListener("keydown", (e) => {
  if (S.screen !== "reader" || e.target.closest?.("input:not([type=range]),textarea")) return;
  if (e.key === " ") { e.preventDefault(); actions.play(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); e.shiftKey ? actions["prev-ch"]() : actions.back(); }
  else if (e.key === "ArrowRight") { e.preventDefault(); e.shiftKey ? actions["next-ch"]() : actions.fwd(); }
  else if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); audio.muted = false; setSetting({ volume: Math.round(Math.max(0, Math.min(1, S.settings.volume + (e.key === "ArrowUp" ? 0.1 : -0.1))) * 10) / 10 }); }
  else if (e.key.toLowerCase() === "m" && !e.metaKey) actions.mute();
  else if (e.key.toLowerCase() === "t" && !e.metaKey) actions["theme-cycle"]();
  else if (e.key === "Escape") { if (S.pop || S.drawer) { S.pop = S.drawer = false; renderReader(); } else showLibrary(); }
  else if (["1", "2", "3", "4"].includes(e.key)) setSetting({ view: VIEWS[Number(e.key) - 1][0] }, true);
  else if (e.key.toLowerCase() === "d" && !e.metaKey) showDebug(!S.debug);
});
audio.addEventListener("play", () => { S.lastSave = performance.now(); refreshControls(); });
audio.addEventListener("pause", () => { refreshControls(); savePosition(true); });
function chapterEnded() {
  if (S.advancing) return;
  S.advancing = true;
  savePosition(true);
  // Keep listening: continue with the next chapter that is ready.
  const next = S.book.chapters.findIndex((c, k) => k > S.ch && c.ready);
  (next >= 0 ? loadChapter(next, 0, true) : Promise.resolve(audio.pause())).finally(() => { S.advancing = false; S.atEndSince = 0; });
}
audio.addEventListener("ended", chapterEnded);
window.addEventListener("beforeunload", () => savePosition(true));

async function start() {
  S.settings = await call("settings");
  applySettings();
  await showLibrary();
  requestAnimationFrame(tick);
}
if (window.pywebview?.api) start(); else window.addEventListener("pywebviewready", start);
