"use strict";
/* BuzzTorrent TV: remote-control UI for the living-room TV.
   Talks to the BuzzTorrent server on the PC. Inside the Android TV app, window.BuzzTV
   is a small native bridge (open OTT apps, Google TV search, external player). */

const $ = (s, el = document) => el.querySelector(s);
const BRIDGE = window.BuzzTV || null;
// What this computer is called on screen: the server writes "PC" or "Mac" into <html data-host>
const PC = document.documentElement.dataset.host || "PC";
document.querySelectorAll(".pc").forEach((el) => { el.textContent = PC; });
const APP_VERSION = (() => { try { return (BRIDGE && BRIDGE.appVersion && BRIDGE.appVersion()) || "browser"; } catch { return "older app"; } })();

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  el.append(...kids.flat().filter((k) => k != null && k !== false));
  return el;
}

const store = {
  get(k, d) { try { const v = localStorage.getItem("tv." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("tv." + k, JSON.stringify(v)); } catch { /* storage off */ } },
};

const TABS = [["movies", "Movies"], ["tv", "TV Shows"], ["music", "Music"], ["all", "Everything"]];
const LANGS = [["any", "All languages"], ["hi", "Hindi"], ["bho", "Bhojpuri"], ["bn", "Bengali"], ["ur", "Urdu"],
  ["ta", "Tamil"], ["te", "Telugu"], ["mr", "Marathi"], ["pa", "Punjabi"], ["en", "English"]];
const LANG_NAME = Object.fromEntries(LANGS);
const ROWS = [["popular", "Most popular"], ["trending", "Trending this week"], ["newest", "Recently added"]];
const GENRES = [["any", "All genres"], ["action", "Action"], ["comedy", "Comedy"], ["drama", "Drama"], ["horror", "Horror"],
  ["thriller", "Thriller"], ["romance", "Romance"], ["scifi", "Sci-fi"], ["animation", "Animation"],
  ["documentary", "Documentary"], ["family", "Family & kids"], ["crime", "Crime"], ["war", "War"], ["western", "Western"],
  ["mythology", "Mythology & devotional"]];
const GENRE_NAME = Object.fromEntries(GENRES);
const genreOn = () => ["movies", "tv"].includes(state.cat) && state.genre !== "any";
const CAT_NOUN = { movies: "Film", tv: "TV", music: "Music", books: "Book", games: "Game", software: "Software" };
const VERDICT = { safe: "Safe", caution: "Caution", danger: "Risky", unknown: "Unrated" };

const state = {
  cat: store.get("cat", "movies"),
  lang: store.get("lang", "any"),
  genre: store.get("genre", "any"),
  query: "",
  stack: [],          // open overlays, top last
  focusBack: [],      // element to refocus when each overlay closes
  playlist: null,
  view: 0,            // bumps on every new view so late responses are dropped
  byId: new Map(),    // results shown so far, for commands from the phone remote
};
if (!TABS.some(([id]) => id === state.cat) && state.cat !== "foryou") state.cat = "movies";
/* The ♥ For you tab isn't a source category: searches made from it cover everything */
const searchCat = () => state.qcat || (state.cat === "foryou" ? "all" : state.cat);
if (!LANG_NAME[state.lang]) state.lang = "any";

/* ------------------------------------------------------------------ api */
class Offline extends Error {}
class NeedPair extends Error {}

async function api(path, body) {
  const opts = body === undefined ? { credentials: "same-origin", cache: "no-store" } : {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-BuzzTorrent": "1" }, body: JSON.stringify(body),
  };
  let res;
  try { res = await fetch(path, opts); } catch { throw new Offline(`Can't reach BuzzTorrent on your ${PC}`); }
  let data;
  try { data = await res.json(); } catch { throw new Error(`The ${PC} answered with an error (${res.status})`); }
  if (res.status === 401 && data.pair) { showPair(); throw new NeedPair("pair first"); }
  if (res.status === 403 && data.locked) { leaveAdult("The private section locked itself"); }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function toast(msg, kind = "") {
  const t = h("div", { class: `toast ${kind}`, role: "status", text: msg });
  $("#toasts").append(t);
  setTimeout(() => t.remove(), 4200);
}
const spinner = () => h("span", { class: "spin", "aria-hidden": "true" });
const qs = (o) => new URLSearchParams(o).toString();

function fmtSize(b) {
  if (!b) return "";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return `${b >= 10 || i < 2 ? Math.round(b) : b.toFixed(1)} ${u[i]}`;
}
function fmtTime(s) {
  if (!isFinite(s)) return "0:00";
  s = Math.max(0, Math.floor(s));
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = String(s % 60).padStart(2, "0");
  return hh ? `${hh}:${String(mm).padStart(2, "0")}:${ss}` : `${mm}:${ss}`;
}
const playable = (r) => (r.sources || []).includes("Internet Archive");

/* ------------------------------------------------------------ chrome */
const adult = { shown: false, unlocked: false };
function renderChips() {
  const tabs = [...TABS, ["foryou", "♥ For you"], ...(adult.shown ? [["adult", "🔒 18+"]] : [])];
  const chips = tabs.map(([id, label]) => h("button", {
    type: "button", class: "chip", "aria-pressed": String(id === state.cat), text: label,
    onclick: () => {
      if (id === "adult" && !adult.unlocked) { askAdultPin(); return; }
      state.cat = id;
      if (id !== "adult") store.set("cat", id);           // the private tab is never remembered
      renderChips(); refresh();
    },
  }));
  if (state.cat === "adult") chips.push(h("button", { type: "button", class: "chip", text: "Lock", onclick: lockAdult }));
  $("#tabs").replaceChildren(...chips);
  $("#langs").replaceChildren(...LANGS.map(([id, label]) => h("button", {
    type: "button", class: "chip", "aria-pressed": String(id === state.lang), text: label,
    onclick: () => { state.lang = id; store.set("lang", id); renderChips(); refresh(); },
  })));
  // Genres: for films and TV, on the home rows (searching by title covers every genre)
  const showGenres = ["movies", "tv"].includes(state.cat) && !state.query;
  $("#genres").hidden = !showGenres;
  if (showGenres) {
    $("#genres").replaceChildren(...GENRES.map(([id, label]) => h("button", {
      type: "button", class: "chip", "aria-pressed": String(id === state.genre), text: label,
      onclick: () => { state.genre = id; store.set("genre", id); renderChips(); renderHome(false); },
    })));
  }
}
const refresh = () => (state.query ? runSearch(state.query, false) : renderHome(false));

/* PC ⇄ Mac. The TV / headset app remembers every computer it was paired with (window.BuzzTV
   .computers()); the header shows them as a toggle, and one press switches to the other one
   (its pairing is kept, so there's no PIN again). Plain browsers have no bridge: no toggle. */
const HOST_NAME = { mac: "Mac", windows: "PC", linux: "PC" };
const HOST_ICON = { mac: "💻", windows: "🖥", linux: "🖥" };
function savedComputers() {
  if (!BRIDGE || !BRIDGE.computers) return null;
  try {
    const c = JSON.parse(BRIDGE.computers());
    if (!c || !Array.isArray(c.list)) return null;
    const seen = {};
    for (const x of c.list) {                 // "PC", "Mac", and "PC 2" if there are two PCs
      const base = HOST_NAME[x.os] || (x.url === c.active ? PC : "Computer");
      seen[base] = (seen[base] || 0) + 1;
      x.label = seen[base] > 1 ? `${base} ${seen[base]}` : base;
      x.icon = HOST_ICON[x.os] || "🖥";
    }
    return c;
  } catch { return null; }
}
function switchComputer(x) {
  toast(`Connecting to your ${x.label}…`);
  // let the toast paint first: the bridge waits up to a few seconds for a computer that's off
  setTimeout(() => {
    let r = "bad";
    try { r = BRIDGE.switchTo(x.url); } catch { /* older app */ }
    if (r === "offline") toast(`Your ${x.label} didn't answer. Is BuzzTorrent running on it, on this Wi-Fi?`, "bad");
    else if (r !== "ok") toast(`Couldn't switch to your ${x.label}`, "bad");
  }, 60);
}
function renderHostSwitch() {
  const box = $("#hostSwitch");
  const c = savedComputers();
  if (!c || !c.list.length) { box.hidden = true; return; }
  const btns = c.list.map((x) => {
    const on = x.url === c.active;
    return h("button", {
      type: "button", class: "chip host", "aria-pressed": String(on), text: `${x.icon} ${x.label}`,
      title: x.url.replace("http://", ""),
      onclick: () => (on ? toast(`Connected to your ${x.label} (${x.url.replace("http://", "")})`) : switchComputer(x)),
    });
  });
  if (c.list.length === 1 && BRIDGE.addComputer) {
    const other = PC === "Mac" ? "PC" : "Mac";
    btns.push(h("button", { type: "button", class: "chip host add", text: `＋ ${other}`,
      title: `Pair this app with your ${other} too`, onclick: () => BRIDGE.addComputer() }));
  }
  box.replaceChildren(...btns);
  box.hidden = false;
}

function offlineView(err) {
  const main = $("#main");
  const btns = [h("button", { type: "button", class: "act primary", text: "Try again", onclick: () => refresh() })];
  const saved = err instanceof Offline && savedComputers();
  for (const x of (saved ? saved.list : []).filter((x) => x.url !== saved.active)) {
    btns.push(h("button", { type: "button", class: "act", text: `Switch to your ${x.label}`, onclick: () => switchComputer(x) }));
  }
  if (BRIDGE && BRIDGE.resetServer) {
    btns.push(h("button", { type: "button", class: "act", text: `Choose another ${PC}`, onclick: () => BRIDGE.resetServer() }));
  }
  main.replaceChildren(h("div", { class: "status big" },
    h("div", { text: err instanceof Offline ? `Can't reach BuzzTorrent on your ${PC}.` : err.message }),
    h("div", { class: "d-note", text: err instanceof Offline ? `Make sure the ${PC} is on and BuzzTorrent is running.` : "" }),
    h("div", { class: "d-actions center" }, btns)));
  btns[0].focus();
}

/* ------------------------------------------------------------- cards */
function placeholder(title) { return h("div", { class: "ph", text: (title || "").slice(0, 48) }); }

function card(r) {
  let img = null;
  if (r.thumb) {
    img = h("img", { src: r.thumb, alt: "", loading: "lazy" });
    img.addEventListener("error", () => img.replaceWith(placeholder(r.title)), { once: true });
  }
  // seeds: more seeds stream faster, so they're shown on every torrent
  const seeds = !playable(r) && r.seeders != null ? `${r.seeders} seeds` : "";
  const meta = [seeds, r.year, seeds ? "" : CAT_NOUN[r.category], fmtSize(r.size)]
    .filter(Boolean).join(" · ");
  const q = r.quality?.label;
  state.byId.set(r.id, r);
  return h("button", { type: "button", class: "card", "data-id": r.id, onclick: () => openDetail(r) },
    h("div", { class: "thumb" }, img || placeholder(r.title),
      h("span", { class: `badge ${r.verdict}`, text: VERDICT[r.verdict] || r.verdict }),
      playable(r) ? h("span", { class: "badge play", text: "▶ Free" }) : null,
      q ? h("span", { class: `badge q q-${q.toLowerCase()}`, text: q }) : null),
    h("div", { class: "card-t", dir: "auto", text: r.title }),
    h("div", { class: "card-m", text: meta }));
}

/* -------------------------------------------------------------- home */
function renderHome(focusFirst = true) {
  state.query = "";
  if (["movies", "tv"].includes(state.cat) && $("#genres").hidden) renderChips();
  $("#q").value = "";
  const view = ++state.view;
  const main = $("#main");
  if (state.cat === "adult") {
    main.replaceChildren(h("div", { class: "status big" }, "🔒 Private section. Nothing is saved: no Continue watching, no watchlist, no history.",
      h("div", { class: "d-note", text: "Search with the box at the top." })));
    if (focusFirst) $("#q").focus();
    return;
  }
  if (state.cat === "foryou") return renderForYou(main, view, focusFirst);
  main.replaceChildren(h("p", { class: "phone-hint" }, "📱 Search from your phone: open ",
    h("b", { text: `${location.host}/remote` }), " on a phone on the same Wi-Fi"));
  const recent = historyRow();
  if (recent) main.append(recent);
  // Rows load in parallel; focus lands on the topmost row with cards, once every row above it is done
  let focused = !focusFirst;
  const tryFocus = () => {
    if (focused || view !== state.view) return;
    for (const el of main.querySelectorAll("section.row, [data-pending]")) {
      if (el.dataset.pending || el.querySelector(".spin")) return;
      const first = el.querySelector(".row-track .card");
      if (first) { focused = true; first.focus({ preventScroll: true }); return; }
    }
  };
  const addRow = (parent, label, loader, makeCard = card, empty = null) => {
    const track = h("div", { class: "row-track" }, h("div", { class: "status" }, spinner(), "Loading…"));
    const sec = h("section", { class: "row" }, h("h2", { text: label }), track);
    parent.append(sec);
    loader().then((items) => {
      if (view !== state.view) return;
      if (!items.length) {
        if (empty === null) sec.remove();
        else track.replaceChildren(h("div", { class: "status", text: empty }));
      } else {
        track.replaceChildren(...items.map(makeCard));
      }
      tryFocus();
    }).catch((err) => {
      if (view !== state.view || err instanceof NeedPair) return;
      if (err instanceof Offline) return offlineView(err);
      track.replaceChildren(h("div", { class: "status", text: err.message }));
      tryFocus();
    });
  };

  if (!genreOn()) addRow(main, "Continue watching", () => api("/api/tv/continue").then((d) => d.items), continueCard);
  if (!genreOn()) addRow(main, "Your watchlist", () => api("/api/tv/watchlist").then((d) => {
    for (const a of (d.alerts || []).slice(0, 3)) toast(`🔔 ${a.text}`, "ok");
    if ((d.alerts || []).length) api("/api/tv/alerts/seen", {}).catch(() => {});
    return d.items.filter((w) => state.cat === "all" || w.category === state.cat || state.cat === "movies" && w.category === "all");
  }), watchCard);
  if (state.lang === "any" && !genreOn()) {
    // Indian classics rows; the box holds their place while the shelf list loads
    const box = h("div", { "data-pending": "1" });
    main.append(box);
    api("/api/tv/shelves?" + qs({ cat: state.cat })).then((d) => {
      if (view !== state.view) return;
      d.shelves.forEach((sh) => addRow(box, sh.label, () => api("/api/tv/shelf?" + qs({ source: sh.source, id: sh.id }))
        .then((x) => x.results.filter((r) => r.verdict !== "danger"))));
    }).catch(() => {}).finally(() => { delete box.dataset.pending; tryFocus(); });
  }
  const g = genreOn() ? state.genre : "any";
  ROWS.forEach(([sort, label]) => addRow(main, g === "any" ? label : `${label} · ${GENRE_NAME[g]}`,
    () => api("/api/browse?" + qs({ cat: state.cat, sort, lang: state.lang, genre: g, page: 1, family: 1 }))
      .then((d) => d.results.filter((r) => r.verdict !== "danger")),
    card, g === "any" ? "Nothing here yet for this language." : "Nothing in this genre for this language yet."));
}

function continueCard(c) {
  const pct = c.dur ? Math.min(100, Math.round((c.pos / c.dur) * 100)) : 0;
  const fill = h("span", { class: "cw-fill" });
  fill.style.width = `${pct}%`;
  let img = null;
  if (c.thumb && c.thumb.startsWith("/api/")) {
    img = h("img", { src: c.thumb, alt: "", loading: "lazy" });
    img.addEventListener("error", () => img.replaceWith(placeholder(c.title)), { once: true });
  }
  return h("button", { type: "button", class: "card", onclick: () => resumeItem(c) },
    h("div", { class: "thumb" }, img || placeholder(c.title),
      c.quality ? h("span", { class: "badge q", text: c.quality }) : null,
      h("span", { class: "cw-bar" }, fill)),
    h("div", { class: "card-t", dir: "auto", text: c.name ? `${c.title} · ${c.name}` : c.title }),
    h("div", { class: "card-m", text: `${c.key.startsWith("lib:") ? `On your ${PC} · ` : ""}${fmtTime(c.pos)} of ${fmtTime(c.dur)}` }));
}

function watchCard(w) {
  let img = null;
  if (w.thumb && w.thumb.startsWith("/api/")) {
    img = h("img", { src: w.thumb, alt: "", loading: "lazy" });
    img.addEventListener("error", () => img.replaceWith(placeholder(w.title)), { once: true });
  }
  const best = w.best ? qualityLabel(w.best) : "";
  return h("button", { type: "button", class: "card", onclick: () => {
    if (TABS.some(([id]) => id === w.category)) { state.cat = w.category; store.set("cat", w.category); renderChips(); }
    runSearch(w.title);
  } },
  h("div", { class: "thumb" }, img || placeholder(w.title),
    w.new ? h("span", { class: "badge new", text: "NEW" }) : null,
    w.free ? h("span", { class: "badge play", text: "▶ Free" }) : null,
    best ? h("span", { class: "badge q", text: best }) : null),
  h("div", { class: "card-t", dir: "auto", text: w.title }),
  h("div", { class: "card-m", text: w.new ? "Better copy found" : "On your watchlist" }));
}
/* ------------------------------------------------------------ for you */
/* Your video jockey: rows built on the PC from the titles you ♥ (see buzz/taste.py) */
async function renderForYou(main, view, focusFirst, quiet = false) {
  if (!quiet) main.replaceChildren(h("div", { class: "status" }, spinner(), "Lining up your picks…"));
  let d, likes = [];
  try {
    d = await api("/api/tv/foryou");
    if (d.likes) likes = (await api("/api/tv/likes")).items;
  } catch (err) {
    if (view !== state.view || err instanceof NeedPair) return;
    if (err instanceof Offline) return offlineView(err);
    main.replaceChildren(h("div", { class: "status", text: err.message }));
    return;
  }
  if (view !== state.view) return;
  const again = (ms) => setTimeout(() => { if (view === state.view && state.cat === "foryou") renderForYou(main, view, false, true); }, ms);
  if (d.off) {
    main.replaceChildren(h("div", { class: "status big" }, "Picks need Smart search, which is off.",
      h("div", { class: "d-note", text: `On the ${PC}: BuzzTorrent → Settings → Smart search & details.` })));
    return;
  }
  if (!d.likes) {
    main.replaceChildren(h("div", { class: "status big" }, "♥ Like a few movies or shows and your picks will show up here.",
      h("div", { class: "d-note", text: "Press ♡ Like on any title's page, or while you're watching. The more you like, the better the picks." })));
    return;
  }
  if (d.building && !d.rows.length) {
    main.replaceChildren(h("div", { class: "status big" }, spinner(), " Your video jockey is lining up picks… a few seconds.",
      h("div", { class: "d-note", text: `Based on ${d.likes} title${d.likes === 1 ? "" : "s"} you liked.` })));
    again(4000);
    return;
  }
  const rows = d.rows.map((row) => h("section", { class: "row" }, h("h2", { text: row.label }),
    h("div", { class: "row-track" }, ...row.items.map(recCard))));
  main.replaceChildren(
    h("p", { class: "phone-hint", text: d.building ? "Updating your picks…" : `Picks from the ${d.likes} title${d.likes === 1 ? "" : "s"} you liked. Like more for better picks; unlike on a title's page.` }),
    ...rows,
    h("section", { class: "row" }, h("h2", { text: "Your likes" }), h("div", { class: "row-track" }, ...likes.map(likeCard))));
  if (focusFirst) $("#main .card")?.focus({ preventScroll: true });
  if (d.building) again(6000);
}

function recCard(it) {
  let img = null;
  if (it.thumb && it.thumb.startsWith("/api/")) {
    img = h("img", { src: it.thumb, alt: "", loading: "lazy" });
    img.addEventListener("error", () => img.replaceWith(placeholder(it.title)), { once: true });
  }
  const cat = TABS.some(([id]) => id === it.category) ? it.category : "all";
  return h("button", { type: "button", class: "card", onclick: () => runSearch(it.title, true, cat) },
    h("div", { class: "thumb" }, img || placeholder(it.title),
      it.year ? h("span", { class: "badge q", text: String(it.year) }) : null),
    h("div", { class: "card-t", dir: "auto", text: it.title }),
    h("div", { class: "card-m", text: it.reason || it.description || "" }));
}

function likeCard(l) {
  let img = null;
  if (l.thumb && l.thumb.startsWith("/api/")) {
    img = h("img", { src: l.thumb, alt: "", loading: "lazy" });
    img.addEventListener("error", () => img.replaceWith(placeholder(l.title)), { once: true });
  }
  return h("button", { type: "button", class: "card", onclick: () => runSearch(l.title, true, l.category) },
    h("div", { class: "thumb" }, img || placeholder(l.title), h("span", { class: "badge like", text: "♥" })),
    h("div", { class: "card-t", dir: "auto", text: l.title }),
    h("div", { class: "card-m", text: [l.year, CAT_NOUN[l.category]].filter(Boolean).join(" · ") || "Liked" }));
}

/* Add or remove a ♥. `info` = {title, category, year, thumb, rid}; `entry` = the current like or null. */
async function toggleLike(info, entry) {
  try {
    if (entry) {
      await api("/api/tv/like", { action: "remove", id: entry.id });
      toast("Removed from your likes");
      return null;
    }
    const d = await api("/api/tv/like", info);
    toast("♥ Liked. Your picks in ♥ For you will catch up in a moment", "ok");
    return d.item;
  } catch (err) {
    if (!(err instanceof NeedPair)) toast(err.message, "bad");
    return entry;
  }
}
const likeCat = (c) => (["movies", "tv", "music"].includes(c) ? c : "movies");
async function findLike(title, category) {
  try {
    const t = String(title).toLowerCase();
    return (await api("/api/tv/likes")).items.find((l) => l.title.toLowerCase() === t && l.category === category) || null;
  } catch { return null; }
}

function qualityLabel(height) {
  return height >= 4000 ? "8K" : height >= 2000 ? "4K" : height >= 1000 ? "1080p" : height >= 690 ? "720p" : height >= 440 ? "480p" : "Low";
}

async function resumeItem(c) {
  try {
    if (c.key.startsWith("lib:")) {
      const d = await api("/api/tv/library");
      const it = d.items.find((x) => x.key === c.key);
      if (!it) { toast(`That video is no longer in the ${PC}'s download folder`, "bad"); return; }
      return playLibrary(it, d.progress, true, d.like);
    }
    if (c.key.startsWith("bt:")) {
      const [, hash, index] = c.key.split(":");
      return startStream({ thumb: c.thumb, quality: c.quality ? { label: c.quality } : null, category: "movies", title: c.title }, c.title,
        { hash, index: Number(index), pos: c.pos });
    }
    const ident = c.key.split(":")[1];
    const d = await api("/api/tv/play?" + qs({ ident }));
    const i = Math.max(0, d.files.findIndex((f) => f.key === c.key));
    state.playingThumb = c.thumb || "";
    state.playing = { title: c.title, category: "movies", thumb: c.thumb || "" };
    if (native()) return playNative(d, i, c.title, d.files[i]?.resume || 0);
    const inApp = d.files.filter((f) => f.url);
    if (!inApp.length) { toast("This copy needs the BuzzTorrent TV app to play", "bad"); return; }
    startPlayer(inApp, Math.max(0, inApp.indexOf(d.files[i])), c.title, d.files[i]?.resume || 0);
  } catch (err) {
    if (!(err instanceof NeedPair)) toast(err.message, "bad");
  }
}

/* ---------------------------------------------------- search history */
/* Kept on this TV only. Private-section searches are never added. */
const HISTORY_MAX = 15;
function remember(q) {
  if (state.cat === "adult") return;
  const old = store.get("history", []).filter((x) => typeof x === "string" && x.toLowerCase() !== q.toLowerCase());
  store.set("history", [q, ...old].slice(0, HISTORY_MAX));
}
function historyRow() {
  if (state.cat === "adult") return null;
  const items = store.get("history", []).filter((x) => typeof x === "string");
  if (!items.length) return null;
  const sec = h("section", { class: "row recent" }, h("h2", { text: "Recent searches" }),
    h("div", { class: "dym" },
      items.map((q) => h("button", { type: "button", class: "chip", dir: "auto", text: q, onclick: () => runSearch(q) })),
      h("button", { type: "button", class: "chip clear", text: "🗑  Clear history", onclick: () => {
        store.set("history", []);
        sec.remove();
        toast("Search history cleared", "ok");
        ($("#main .card") || $("#q")).focus({ preventScroll: true });
      } })));
  return sec;
}

/* ------------------------------------------------------------ search */
async function runSearch(q, focusFirst = true, cat = null) {
  q = q.trim();
  if (!q) return renderHome();
  state.query = q;
  state.qcat = cat;
  remember(q);
  $("#genres").hidden = true;                    // a title search covers every genre
  $("#q").value = q;
  const view = ++state.view;
  const main = $("#main");
  const label = (TABS.find(([id]) => id === searchCat()) || [, "the private section"])[1];
  main.replaceChildren(h("h2", { class: "section-h", text: `“${q}” in ${label}` + (state.lang !== "any" ? ` · ${LANG_NAME[state.lang]}` : "") }),
    h("div", { class: "status" }, spinner(), "Searching… this can take a few seconds"));
  (document.scrollingElement || document.documentElement).scrollTop = 0;
  let d;
  try {
    d = await api("/api/search?" + qs({ q, cat: searchCat(), lang: state.lang }));
  } catch (err) {
    if (view !== state.view || err instanceof NeedPair) return;
    if (err instanceof Offline) return offlineView(err);
    main.lastChild.replaceWith(h("div", { class: "status", text: err.message }));
    return;
  }
  if (view !== state.view) return;
  state.lastSearch = d;
  drawResults(focusFirst);
}

/* Filters on the results, the same as on the PC: minimum quality and "safe only" */
/* Exactly that quality: "1080p" shows 1080p copies only, not 4K ones */
const QUALITY_FILTERS = [["any", "Any quality"], ["720p", "720p"], ["1080p", "1080p"], ["4K", "4K"]];
function drawResults(focusFirst = false) {
  const d = state.lastSearch;
  const main = $("#main");
  if (!d) return;
  let qf = store.get("qfilter", "any");
  if (!QUALITY_FILTERS.some(([v]) => v === qf)) qf = "any";
  const safeOnly = store.get("safeonly", false);
  const all = d.results.filter((r) => r.verdict !== "danger");
  const items = all.filter((r) => (!safeOnly || r.verdict === "safe") && (qf === "any" || (r.quality?.height && qualityLabel(r.quality.height) === qf)));
  const hidden = d.results.length - all.length;
  const filters = h("div", { class: "dym filters" },
    QUALITY_FILTERS.map(([v, label]) => h("button", { type: "button", class: "chip", "aria-pressed": String(qf === v), text: label,
      onclick: () => { store.set("qfilter", v); drawResults(); $(".filters .chip[aria-pressed=true]")?.focus(); } })),
    h("button", { type: "button", class: "chip", "aria-pressed": String(safeOnly), text: safeOnly ? "✓ Safe only" : "Safe only",
      onclick: () => { store.set("safeonly", !safeOnly); drawResults(); $(".filters .chip:last-child")?.focus(); } }));
  const parts = [main.firstChild, filters];
  const dym = (d.did_you_mean || []).slice(0, 4);
  if (dym.length) {
    parts.push(h("div", { class: "dym" }, h("span", { class: "dym-l", text: "Did you mean" }),
      dym.map((w) => h("button", { type: "button", class: "chip", text: w.year ? `${w.title} (${w.year})` : w.title, onclick: () => runSearch(w.title) }))));
  }
  // A few hundred cards at once make a TV sluggish: show them a page at a time
  const grid = h("div", { class: "grid" }, items.slice(0, PAGE).map(card));
  let shown = Math.min(PAGE, items.length);
  const more = h("button", { type: "button", class: "act", onclick: () => {
    const next = items.slice(shown, shown + PAGE).map(card);
    shown += next.length;
    grid.append(...next);
    fillPosters(items.slice(shown - next.length, shown));
    if (shown >= items.length) moreBox.remove();
    else more.textContent = `Show more (${items.length - shown} left)`;
    next[0]?.focus({ preventScroll: true });
    next[0]?.scrollIntoView({ block: "center" });
  } }, `Show more (${items.length - shown} left)`);
  const moreBox = h("div", { class: "more" }, more);
  parts.push(items.length ? grid
    : h("div", { class: "status big", text: all.length ? `${all.length - items.length} results hidden by the filters above.`
      : state.cat === "tv" ? "No TV episodes found. Try Everything, or check spelling." : "Nothing found. Try another spelling or language." }));
  if (shown < items.length) parts.push(moreBox);
  if (hidden) parts.push(h("div", { class: "status", text: `${hidden} risky result${hidden > 1 ? "s" : ""} hidden for your safety.` }));
  main.replaceChildren(...parts);
  fillPosters(items.slice(0, shown));
  // Only jump to the results if the person hasn't moved somewhere else while waiting
  const at = document.activeElement;
  const idle = !at || at === document.body || !document.contains(at) || ["q", "micBtn", "micHiBtn", "main"].includes(at.id);
  if (focusFirst && idle) $(".grid .card", main)?.focus({ preventScroll: true });
}
const PAGE = 40;

/* Torrents have no artwork: the PC looks posters up on Wikipedia once the list is showing */
async function fillPosters(results) {
  const missing = results.filter((r) => !r.thumb && r.category !== "adult");
  if (!missing.length) return;
  const view = state.view;
  try {
    const { posters } = await api("/api/posters?" + qs({ ids: missing.map((r) => r.id).join(",") }));
    if (view !== state.view) return;
    for (const r of missing) {
      if (!posters[r.id]) continue;
      r.thumb = posters[r.id];
      const ph = document.querySelector(`#main .card[data-id="${CSS.escape(r.id)}"] .ph`);
      if (!ph) continue;
      const img = h("img", { src: r.thumb, alt: "", loading: "lazy" });
      img.addEventListener("error", () => img.replaceWith(placeholder(r.title)), { once: true });
      ph.replaceWith(img);
    }
  } catch { /* posters are a nicety */ }
}

/* ----------------------------------------------------------- overlays */
function push(id) {
  state.focusBack.push(document.activeElement);
  state.stack.push(id);
  document.body.classList.add("locked");        // the page underneath doesn't scroll while a screen is open
  $("#" + id).hidden = false;
  $("#" + id).scrollTop = 0;
  try { history.pushState({ overlay: id }, ""); } catch { /* ignore */ }
}
function closeTop() {
  const id = state.stack.pop();
  if (!id) return;
  $("#" + id).hidden = true;
  if (!state.stack.length) document.body.classList.remove("locked");
  if (id === "player") stopVideo();
  if (id === "streamBox") stopStream();
  const back = state.focusBack.pop();
  if (back && document.contains(back)) back.focus({ preventScroll: true });
  setTimeout(reloadIfIdle, 300);
}
window.addEventListener("popstate", () => { if (state.stack.length) closeTop(); });
const topOverlay = () => state.stack[state.stack.length - 1];
/* Called by the Android app on the remote's Back button: true = handled here. */
window.buzzBack = () => {
  if (!$("#pair").hidden) return false;
  if (state.stack.length) { history.back(); return true; }
  if (state.query) { renderHome(); return true; }
  return false;
};

/* ------------------------------------------------------------- detail */
let installedCache = null;
const norm = (s) => String(s).toLowerCase().replace(/[^a-z0-9+]/g, "");
function installedApps() {
  if (!BRIDGE || !BRIDGE.installedApps) return null;
  if (!installedCache) {
    try { installedCache = JSON.parse(BRIDGE.installedApps()).map(norm); } catch { installedCache = []; }
  }
  return installedCache;
}
function hasApp(service, labels) {
  return service.apps.some((a) => {
    const n = norm(a);
    return labels.some((l) => l === n || (n.length >= 5 && l.startsWith(n)));
  });
}

async function renderOtt(title) {
  const box = $("#dOtt");
  const labels = installedApps();
  $("#dWatchNote").textContent = labels
    ? "Free options come first. Opens the app on this TV and searches for this title; a green outline means it's installed. Paid titles still need that service's subscription."
    : "Searches each service's website for this title.";
  let services;
  try { services = (await api("/api/tv/services?" + qs({ title }))).services; } catch { return; }
  if (labels) services.sort((a, b) => hasApp(b, labels) - hasApp(a, labels));
  const btns = [];
  if (BRIDGE && BRIDGE.globalSearch && (!BRIDGE.canGlobalSearch || BRIDGE.canGlobalSearch())) {
    btns.push(h("button", { type: "button", class: "ott installed", onclick: () => {
      const res = BRIDGE.globalSearch(title);
      if (res !== "ok") toast("Google TV search isn't available on this TV", "bad");
    } }, "Search all my apps", h("small", { text: "Google TV" })));
  }
  for (const s of services) {
    const inst = labels ? hasApp(s, labels) : false;
    btns.push(h("button", { type: "button", class: "ott" + (inst ? " installed" : ""), onclick: () => openService(s, s.query || title) },
      s.name, s.free ? h("span", { class: "free", text: s.id === "youtube" ? "Free" : s.free }) : null,
      labels && !inst ? h("small", { text: "get app" }) : null));
  }
  box.replaceChildren(...btns);
}

function openService(s, title) {
  if (!BRIDGE) { window.open(s.web, "_blank", "noopener"); return; }
  let res = BRIDGE.openService(JSON.stringify(s.apps), s.name, title);
  // No app and no Play Store (Meta Quest): the service's website in the browser
  if (res === "none" && BRIDGE.openWeb && s.web && BRIDGE.openWeb(s.web) === "ok") res = "web";
  const msg = {
    search: [`Searching ${s.name} for “${title}”`, "ok"],
    opened: [`Opened ${s.name}. Search for “${title}” there`, "ok"],
    store: [`${s.name} isn't installed. Opening the Play Store`, ""],
    web: [`Opening ${s.name}'s website`, ""],
  }[res] || [`Couldn't open ${s.name}`, "bad"];
  toast(...msg);
}

async function openDetail(r) {
  push("detail");
  const poster = $("#dPoster");
  poster.src = r.thumb || "/favicon.svg";
  $("#dTitle").textContent = r.title;
  const langs = (r.language || []).map((c) => LANG_NAME[c] || c);
  const seeds = playable(r) || r.seeders == null ? "" : `${r.seeders} seeds${r.seeders < 5 ? " (may be slow)" : ""}`;
  $("#dMeta").textContent = [r.year, CAT_NOUN[r.category], fmtSize(r.size), seeds, ...langs, (r.sources || []).join(", ")].filter(Boolean).join(" · ");
  $("#dBadges").replaceChildren(h("span", { class: `v-${r.verdict}`, text: `${VERDICT[r.verdict]} · ${r.score}/100` }),
    playable(r) ? h("span", { class: "v-free", text: "Free to watch" }) : null,
    r.quality ? h("span", { class: "v-q", text: r.quality.label + (r.quality.exact ? "" : " (from title)") }) : null);
  $("#dSummary").textContent = "";
  $("#dCast").replaceChildren();
  $("#dFlags").replaceChildren(...(r.flags || []).filter((f) => f.level !== "info")
    .map((f) => h("li", { class: f.level, text: (f.level === "danger" ? "⛔ " : "⚠ ") + f.msg })));

  const actions = [];
  let playBtn = null;
  if (playable(r)) {
    playBtn = h("button", { type: "button", class: "act primary", onclick: () => play(r, $("#dTitle").textContent) }, "▶  Play on TV");
    actions.push(playBtn);
    // Learn the best copy up front so the button can say what it will play
    loadPlay(r).then((d) => {
      if (topOverlay() !== "detail" || !d) return;
      const best = bestLabel(d);
      if (best) playBtn.textContent = `▶  Play ${best}`;
    });
  }
  if (canStream(r)) {
    // Torrents stream straight to the TV: the PC fetches the video in playing order as it plays
    actions.push(h("button", { type: "button", class: "act primary", onclick: () => startStream(r, $("#dTitle").textContent) },
      `▶  Stream${r.quality ? " " + r.quality.label : ""}`));
  }
  const priv = r.category === "adult";
  if (!priv) actions.push(likeButton(r), watchButton(r));
  for (const el of [$("#detail .d-h"), $("#dWatchNote"), $("#dOtt")]) el.hidden = priv;
  $("#dActions").replaceChildren(...actions);
  actions[0].focus();
  if (!priv) renderOtt(r.title.replace(/[._]+/g, " "));

  try {
    const d = await api("/api/details?" + qs({ id: r.id }));
    if (topOverlay() !== "detail") return;
    if (d.title) $("#dTitle").textContent = d.title;
    if (d.poster) poster.src = d.poster;
    $("#dSummary").textContent = d.summary || d.upload?.description || "";
    const people = [["Cast", d.cast || []], ...(d.facts || []).filter((f) => f.label !== "Cast").slice(0, 2).map((f) => [f.label, f.values])];
    $("#dCast").replaceChildren(...people.filter(([, v]) => v.length)
      .map(([label, v]) => h("span", {}, h("b", { text: label + ": " }), v.slice(0, 8).join(", "))));
    const extra = [d.runtime, (d.genres || []).slice(0, 3).join(", ")].filter(Boolean);
    if (extra.length) $("#dMeta").textContent += " · " + extra.join(" · ");
    if (d.title && !priv) renderOtt(d.title);
  } catch { /* details are optional */ }
}

/* ------------------------------------------------------------- like */
function likeButton(r) {
  const btn = h("button", { type: "button", class: "act" }, "♡  Like");
  let entry = null;
  const cat = likeCat(r.category);
  const sync = () => { btn.textContent = entry ? "♥  Liked" : "♡  Like"; };
  findLike($("#dTitle").textContent || r.title, cat).then((e) => { entry = e; sync(); });
  btn.addEventListener("click", async () => {
    entry = await toggleLike({ title: $("#dTitle").textContent || r.title, category: cat, year: r.year,
      thumb: r.thumb || "", rid: r.id }, entry);
    sync();
  });
  return btn;
}

/* ------------------------------------------------------- watchlist */
function watchButton(r) {
  const btn = h("button", { type: "button", class: "act" }, "☆  Watchlist");
  let entry = null;
  const cat = ["movies", "tv", "music"].includes(r.category) ? r.category : "movies";
  const sync = () => { btn.textContent = entry ? "★  On watchlist" : "☆  Watchlist"; };
  api("/api/tv/watchlist").then((d) => {
    const t = ($("#dTitle").textContent || r.title).toLowerCase();
    entry = d.items.find((w) => w.title.toLowerCase() === t && w.category === cat) || null;
    sync();
  }).catch(() => {});
  btn.addEventListener("click", async () => {
    try {
      if (entry) {
        await api("/api/tv/watch", { action: "remove", id: entry.id });
        entry = null;
        toast("Removed from your watchlist");
      } else {
        const d = await api("/api/tv/watch", { title: $("#dTitle").textContent || r.title, category: cat, year: r.year,
          thumb: r.thumb || "", quality: r.quality?.height || 0, free: playable(r) });
        entry = d.item;
        toast("Added. You'll be told when a better or free copy turns up", "ok");
      }
      sync();
    } catch (err) {
      if (!(err instanceof NeedPair)) toast(err.message, "bad");
    }
  });
  return btn;
}

/* ------------------------------------------------------- PC library */
/* Videos the PC downloaded and its scanner checked clean, streamed from the PC */
async function openLibrary() {
  push("library");
  const grid = $("#libGrid");
  grid.replaceChildren(h("div", { class: "status" }, spinner(), `Looking at your ${PC}'s downloads…`));
  let d;
  try { d = await api("/api/tv/library"); } catch (err) {
    if (!(err instanceof NeedPair)) grid.replaceChildren(h("div", { class: "status", text: err.message }));
    return;
  }
  if (d.state === "scanner_off") {
    grid.replaceChildren(h("div", { class: "status big", text: `Turn on the Download scanner on the ${PC} (Settings → Download scanner) and choose your downloads folder. Every video it checks as clean shows up here.` }));
    return;
  }
  const busy = (d.downloading || []).map((x) => h("div", { class: "status" },
    `⬇ Downloading on your ${PC}: ${x.title} · ${x.total ? Math.floor((x.done / x.total) * 100) : 0}%` +
    (x.down ? ` · ${fmtSize(x.down)}/s` : "") + " (appears here once finished and scanned)"));
  $("#library .d-note").replaceChildren(`Videos your ${PC} downloaded and its virus scanner checked. They stream from the ${PC}.`, ...busy);
  if (!d.items.length) {
    grid.replaceChildren(h("div", { class: "status big", text: `No scanned videos yet. Downloads appear here once the ${PC}'s scanner has checked them.` }));
    return;
  }
  grid.replaceChildren(...d.items.map((it) => h("button", { type: "button", class: "card", onclick: () => playLibrary(it, d.progress, false, d.like) },
    h("div", { class: "thumb" }, placeholder(it.title),
      h("span", { class: "badge safe", text: "✓ Scanned" }),
      it.label ? h("span", { class: `badge q q-${it.label.toLowerCase()}`, text: it.label }) : null,
      it.resume ? h("span", { class: "badge play", text: "Resume" }) : null),
    h("div", { class: "card-t", dir: "auto", text: it.title }),
    h("div", { class: "card-m", text: [it.year, fmtSize(it.size), it.ext.toUpperCase(), it.subs.length ? "CC" : ""].filter(Boolean).join(" · ") }))));
  $("#libGrid .card")?.focus();
}

function playLibrary(it, progress, resumeNow = false, likeUrl = "") {
  state.playing = it.private ? null : { title: it.title, category: "movies", year: it.year };
  const run = (from) => {
    if (native()) {
      state.playingThumb = "";
      // every copy of the video, best first: the player falls back if the TV can't decode one
      const versions = (it.versions || [{ stream: it.stream, label: it.label || it.ext.toUpperCase(), size: it.size }])
        .map((v) => ({ url: location.origin + v.stream, label: v.label, size: v.size }));
      playNative({ progress, like: likeUrl, files: [{ name: it.title, key: it.key, resume: from, seconds: 0, subs: it.subs, versions }] }, 0, it.title, from);
    } else {
      startPlayer([{ url: it.stream, name: it.title, key: it.key, label: it.label }], 0, it.title, from);
    }
  };
  if (resumeNow) run(it.resume || 0);
  else withResume(it.resume, it.title, run);
}

/* ----------------------------------------- videos saved on this TV earlier */
const canSaveOnTv = () => !!(BRIDGE && BRIDGE.downloadToTv && BRIDGE.listDownloads);

function storages() {
  try { return JSON.parse(BRIDGE.storage()).sort((a, b) => b.free - a.free); } catch { return []; }
}

/* the Downloads screen: progress, play offline, delete */
let dlTimer = 0;
const armedDelete = new Set();
function openDownloads() {
  push("downloads");
  $("#dlTitle").textContent = `Downloads · TV app ${APP_VERSION}`;
  renderDownloads();
  clearInterval(dlTimer);
  dlTimer = setInterval(() => { if (topOverlay() === "downloads") renderDownloads(); else clearInterval(dlTimer); }, 2000);
}
const PC_STATUS = { active: "Downloading", metadata: "Finding the files…", waiting: "Queued", paused: "Paused",
  error: "Failed", complete: "Done", seeding: "Done · sharing back" };
async function renderPcDownloads() {
  let d;
  try { d = await api("/api/downloads"); } catch (err) {
    if (!(err instanceof NeedPair)) $("#dlPc").replaceChildren(h("div", { class: "status", text: err.message }));
    return;
  }
  const keep = document.activeElement?.dataset?.key;
  const items = d.items.filter((x) => x.status !== "removed");
  if (!items.length) {
    $("#dlPc").replaceChildren(h("div", { class: "status", text: `Nothing downloading on the ${PC}. Use ⬇ Download on ${PC} on any title.` }));
    return;
  }
  $("#dlPc").replaceChildren(...items.map((x) => {
    const pct = x.total ? Math.floor((x.done / x.total) * 100) : 0;
    const fill = h("span", { class: "dl-fill" });
    fill.style.width = `${pct}%`;
    const right = x.status === "active" ? `${pct}% · ${fmtSize(x.down)}/s` : PC_STATUS[x.status] || x.status;
    const act = (label, action, key) => h("button", { type: "button", class: "dl-del", "data-key": key + x.gid, text: label,
      onclick: async () => {
        if (action === "remove" && !armedDelete.has(x.gid)) {
          armedDelete.add(x.gid);
          setTimeout(() => armedDelete.delete(x.gid), 3000);
          renderPcDownloads();
          return;
        }
        armedDelete.delete(x.gid);
        try { await api("/api/downloads/action", { gid: x.gid, action }); } catch (err) { toast(err.message, "bad"); }
        renderPcDownloads();
      } });
    const btns = [];
    if (["active", "waiting", "metadata"].includes(x.status)) btns.push(act("Pause", "pause", "pp"));
    if (x.status === "paused") btns.push(act("Resume", "resume", "pr"));
    btns.push(act(armedDelete.has(x.gid) ? "Press again" : x.status === "seeding" ? "Stop sharing" : "Stop", "remove", "ps"));
    return h("div", { class: "dl-row" },
      h("button", { type: "button", class: "p-item", "data-key": "pi" + x.gid, onclick: () => toast(`${PC_STATUS[x.status] || x.status}: ${x.title}`) },
        h("span", { class: "dl-main" }, h("span", { dir: "auto", text: x.title }),
          ["seeding", "complete"].includes(x.status) ? null : h("span", { class: "dl-bar" }, fill)),
        h("span", { text: right })),
      ...btns);
  }));
  const again = keep && $(`#dlPc [data-key="${keep}"]`);
  if (again) again.focus({ preventScroll: true });
}

function renderDownloads() {
  renderPcDownloads();
  $("#dlTvBox").hidden = !canSaveOnTv();
  if (!canSaveOnTv()) {
    if (!$("#downloads").contains(document.activeElement)) setTimeout(() => $("#dlPc button")?.focus(), 300);
    return;
  }
  let list = [];
  try { list = JSON.parse(BRIDGE.listDownloads()); } catch { /* none */ }
  const keep = document.activeElement?.dataset?.key;
  $("#dlSpace").textContent = storages().map((s) => `${s.label}: ${fmtSize(s.free)} free`).join(" · ");
  if (!list.length) {
    $("#dlList").replaceChildren(h("div", { class: "status", text: "Nothing saved yet. Open a free movie and choose ⬇ Download to TV." }));
    return;
  }
  const STATUS = { running: "Downloading", pending: "Waiting", paused: "Paused (waiting for the network)", failed: "Failed", missing: "File was removed" };
  $("#dlList").replaceChildren(...list.map((x) => {
    const pct = x.total ? Math.floor((x.done / x.total) * 100) : 0;
    const right = x.status === "done" ? `▶ Play · ${fmtSize(x.total)}`
      : x.status === "running" ? `${pct}% · ${fmtSize(x.done)} of ${fmtSize(x.total)}` : STATUS[x.status] || x.status;
    const fill = h("span", { class: "dl-fill" });
    fill.style.width = `${pct}%`;
    const main = h("button", { type: "button", class: "p-item", "data-key": "p" + x.id, onclick: () => {
      if (x.status !== "done") { toast(STATUS[x.status] || "Not finished yet"); return; }
      if (BRIDGE.playDownload(String(x.id)) !== "ok") toast("Couldn't open the file", "bad");
    } }, h("span", { class: "dl-main" },
      h("span", { dir: "auto", text: `${x.title}${x.label ? " · " + x.label : ""}${x.removable ? " · USB" : ""}` }),
      x.status === "done" ? null : h("span", { class: "dl-bar" }, fill)),
    h("span", { text: right }));
    const del = h("button", { type: "button", class: "dl-del", "data-key": "d" + x.id,
      text: armedDelete.has(x.id) ? "Press again to delete" : (x.status === "done" ? "Delete" : "Cancel"), onclick: () => {
        if (!armedDelete.has(x.id)) {
          armedDelete.add(x.id);
          setTimeout(() => { armedDelete.delete(x.id); if (topOverlay() === "downloads") renderDownloads(); }, 3000);
          renderDownloads();
          return;
        }
        armedDelete.delete(x.id);
        BRIDGE.deleteDownload(String(x.id));
        toast("Deleted from the TV");
        renderDownloads();
      } });
    return h("div", { class: "dl-row" }, main, del);
  }));
  const again = keep && $(`#dlList [data-key="${keep}"]`);
  (again || $("#dlList .p-item"))?.focus({ preventScroll: !!again });
}

/* -------------------------------------------------------------- play */
/* Play: the best copy by default. The Android app has a native player that handles every
   format the TV can decode (MKV, HEVC, 1080p, 4K) and falls back to the next copy by itself;
   a plain TV browser plays the best .mp4/.webm copy in the page. */
const native = () => !!(BRIDGE && BRIDGE.playNative);
const playCache = new Map();
function loadPlay(r) {
  if (!playCache.has(r.id)) {
    playCache.set(r.id, api("/api/tv/play?" + qs({ id: r.id })).catch((err) => {
      playCache.delete(r.id);
      if (!(err instanceof NeedPair)) toast(err.message, "bad");
      return null;
    }));
  }
  return playCache.get(r.id);
}
function bestLabel(d) {
  const f = d.files[0];
  if (!f) return "";
  if (native()) return f.best?.label || f.label || "";
  return f.url ? f.label || "" : "";
}
/* Everything the native player needs: every copy (sharpest first, with bitrates for the
   Wi-Fi check), subtitles, where to resume, and where to save the position. */
function playNative(d, index, title, resumeFrom) {
  const abs = (u) => (u && u.startsWith("/") ? location.origin + u : u);
  const items = d.files.map((f, i) => ({
    name: f.name, key: f.key || "", thumb: state.playingThumb || "",
    resume: i === index ? resumeFrom || 0 : f.resume || 0,
    urls: f.versions.map((v) => v.url), labels: f.versions.map((v) => v.label || v.format),
    bitrates: f.versions.map((v) => (v.size && f.seconds ? Math.round((v.size * 8) / f.seconds) : 0)),
    subs: (f.subs || []).filter((x) => x.url).map((x) => ({ label: x.label, url: abs(x.url) })),
  }));
  const payload = { title, index, items, progress: abs(d.progress), like: nativeLike(d.like, title) };
  if (BRIDGE.playNative(JSON.stringify(payload)) !== "ok") toast("Couldn't start the player", "bad");
}

/* The native players (TV app, Quest cinema) get a ♥ button: where to post, and what the title is */
function nativeLike(url, title) {
  const p = state.playing;
  if (!url || !p || !p.title) return null;
  return { url: url.startsWith("/") ? location.origin + url : url, title: p.title || title, category: p.category || "movies",
    year: p.year || null, thumb: p.thumb || "" };
}

/* "Resume from 34:10" or "Start over" when there's a saved position */
function withResume(resume, title, run) {
  if (!(resume > 0)) { run(0); return; }
  push("picker");
  $("#pTitle").textContent = title;
  const items = [
    h("button", { type: "button", class: "p-item", onclick: () => { history.back(); run(resume); } },
      h("span", { text: `▶  Resume from ${fmtTime(resume)}` }), h("span", { text: "" })),
    h("button", { type: "button", class: "p-item", onclick: () => { history.back(); run(0); } },
      h("span", { text: "↺  Start from the beginning" }), h("span", { text: "" })),
  ];
  $("#pList").replaceChildren(...items);
  items[0].focus();
}

async function play(r, title) {
  const d = await loadPlay(r);
  if (!d) return;
  if (!d.files.length) { toast(d.note || "Nothing playable here", "bad"); return; }
  state.playingThumb = r.thumb || "";
  state.playing = { title, category: likeCat(r.category), year: r.year, thumb: r.thumb || "", rid: r.id };
  if (native()) {
    const go = (i) => withResume(d.files[i].resume, title, (from) => playNative(d, i, title, from));
    if (d.files.length === 1) { go(0); return; }
    return episodePicker(d.files, title, go, (f) => [f.best?.label, f.resume ? "resume " + fmtTime(f.resume) : ""].filter(Boolean).join(" · "));
  }
  const ext = !!(BRIDGE && BRIDGE.playExternal);
  const files = d.files.filter((f) => f.url || (f.alt && ext));
  if (!files.length) {
    toast("This copy is only in a format a TV browser can't play. Use the BuzzTorrent TV app.", "bad");
    return;
  }
  const inApp = files.filter((f) => f.url);
  const playAt = (f) => (f.url ? startPlayer(inApp, inApp.indexOf(f), title) : BRIDGE.playExternal(f.alt.url, title));
  const one = files.length === 1 ? files[0] : null;
  if (one && !(one.alt && one.url && ext)) { playAt(one); return; }
  if (one) {   // older TV app: the sharper copy needs a player app; best one first
    push("picker");
    $("#pTitle").textContent = `${title}: choose quality`;
    const items = [
      h("button", { type: "button", class: "p-item", onclick: () => BRIDGE.playExternal(one.alt.url, title) },
        h("span", { text: `▶  ${one.alt.label || "Best"} · best quality, in your video player app` }),
        h("span", { text: [one.alt.format, fmtSize(one.alt.size)].filter(Boolean).join(" · ") })),
      h("button", { type: "button", class: "p-item", onclick: () => startPlayer(inApp, 0, title) },
        h("span", { text: `▶  ${one.label || "Standard"} · plays here` }),
        h("span", { text: fmtSize(one.size) })),
    ];
    $("#pList").replaceChildren(...items);
    items[0].focus();
    return;
  }
  episodePicker(files, title, (i) => playAt(files[i]), (f) => f.label);
}

function episodePicker(files, title, onPick, labelOf) {
  push("picker");
  $("#pTitle").textContent = `${title}: ${files.length} videos`;
  const items = files.map((f, i) => h("button", { type: "button", class: "p-item", onclick: () => onPick(i) },
    h("span", { dir: "auto", text: f.name }),
    h("span", { text: [labelOf(f), f.seconds ? fmtTime(f.seconds) : "", fmtSize(f.size)].filter(Boolean).join(" · ") })));
  $("#pList").replaceChildren(...items);
  items[0].focus();
}

let hudTimer = 0;
const video = $("#video");
function showHud() {
  $("#hud").classList.remove("hide");
  clearTimeout(hudTimer);
  hudTimer = setTimeout(() => { if (!video.paused) $("#hud").classList.add("hide"); }, 3500);
}
function startPlayer(files, i, title, resumeFrom = 0) {
  if (topOverlay() !== "player") push("player");
  state.playlist = { files, i, title, saved: 0 };
  const f = files[i];
  $("#playerMsg").hidden = true;
  $("#hudTitle").textContent = files.length > 1 ? `${title} · ${f.name}` : title;
  video.src = f.url;
  if (resumeFrom > 0) video.addEventListener("loadedmetadata", () => { video.currentTime = resumeFrom; }, { once: true });
  video.play().catch(() => {});
  const btns = [];
  if (i + 1 < files.length) btns.push(h("button", { type: "button", text: "Next ▶▶", onclick: () => startPlayer(files, i + 1, title) }));
  if (i > 0) btns.push(h("button", { type: "button", text: "◀◀ Previous", onclick: () => startPlayer(files, i - 1, title) }));
  if (BRIDGE && BRIDGE.playExternal) btns.push(h("button", { type: "button", text: "Open in another player", onclick: () => BRIDGE.playExternal(f.alt ? f.alt.url : f.url, title) }));
  const like = hudLikeButton();
  if (like) btns.push(like);
  $("#hudBtns").replaceChildren(...btns);
  $("#player").focus();
  document.activeElement?.blur?.();
  showHud();
}
/* ♡ Like while watching: press ▼ on the remote to reach it */
function hudLikeButton() {
  const info = state.playing;
  if (!info || !info.title) return null;
  const btn = h("button", { type: "button", text: "♡ Like" });
  let entry = null;
  const sync = () => { btn.textContent = entry ? "♥ Liked" : "♡ Like"; };
  findLike(info.title, info.category).then((e) => { entry = e; sync(); });
  btn.addEventListener("click", async () => { entry = await toggleLike(info, entry); sync(); showHud(); });
  return btn;
}
function stopVideo() {
  video.pause();
  video.removeAttribute("src");
  video.load();
  state.playlist = null;
}
function saveWebProgress() {
  const p = state.playlist;
  const f = p && p.files[p.i];
  if (!f || !f.key || !video.duration) return;
  api("/api/tv/progress", { key: f.key, pos: video.currentTime, dur: video.duration, title: p.title,
    name: p.files.length > 1 ? f.name : "", thumb: state.playingThumb || "", quality: f.label || "" }).catch(() => {});
}
video.addEventListener("pause", saveWebProgress);
video.addEventListener("timeupdate", () => {
  const p = state.playlist;
  if (p && Date.now() - p.saved > 15000) { p.saved = Date.now(); saveWebProgress(); }
  $("#hudFill").style.width = video.duration ? `${(video.currentTime / video.duration) * 100}%` : "0";
  $("#hudTime").textContent = fmtTime(video.currentTime);
  $("#hudDur").textContent = fmtTime(video.duration);
});
video.addEventListener("pause", showHud);
video.addEventListener("ended", () => {
  const p = state.playlist;
  if (p && p.i + 1 < p.files.length) startPlayer(p.files, p.i + 1, p.title);
  else history.back();
});
video.addEventListener("error", () => {
  if (!state.playlist) return;
  const m = $("#playerMsg");
  m.textContent = "This video's format can't play in the TV app." + (BRIDGE && BRIDGE.playExternal ? " Press ▼ and choose “Open in another player” (e.g. VLC)." : "");
  m.hidden = false;
  showHud();
});
function playerKey(e) {
  const onBtn = e.target.closest && e.target.closest("#hudBtns");
  showHud();
  switch (e.key) {
    case "Enter": case " ": case "MediaPlayPause":
      if (onBtn) return false;
      video.paused ? video.play().catch(() => {}) : video.pause();
      return true;
    case "MediaPlay": video.play().catch(() => {}); return true;
    case "MediaPause": video.pause(); return true;
    case "ArrowLeft": if (onBtn) return false; video.currentTime = Math.max(0, video.currentTime - 10); return true;
    case "ArrowRight": if (onBtn) return false; video.currentTime = Math.min(video.duration || 0, video.currentTime + 10); return true;
    case "MediaRewind": video.currentTime = Math.max(0, video.currentTime - 30); return true;
    case "MediaFastForward": video.currentTime = Math.min(video.duration || 0, video.currentTime + 30); return true;
    case "ArrowDown": if (!onBtn) { $("#hudBtns button")?.focus(); return true; } return false;
    case "ArrowUp": if (onBtn) { e.target.blur(); return true; } return true;
    case "MediaTrackNext": { const p = state.playlist; if (p && p.i + 1 < p.files.length) startPlayer(p.files, p.i + 1, p.title); return true; }
    default: return false;
  }
}

/* ------------------------------------------------------------ pairing */
let pin = "";
function showPair() {
  const box = $("#pair");
  if (!box.hidden) return;
  box.hidden = false;
  pin = "";
  drawPin();
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"];
  $("#pad").replaceChildren(...keys.map((k) => h("button", { type: "button", text: k, onclick: () => padKey(k) })));
  $("#pad button").focus();
}
function drawPin() {
  $("#pinShow").replaceChildren(...Array.from({ length: 6 }, (_, i) => h("span", { class: i === pin.length ? "on" : "", text: pin[i] ? "•" : "" })));
}
function padKey(k) {
  $("#pairErr").textContent = "";
  if (k === "⌫") pin = pin.slice(0, -1);
  else if (k === "OK") return submitPin();
  else if (pin.length < 6) pin += k;
  drawPin();
  if (pin.length === 6) submitPin();
}
async function submitPin() {
  if (pin.length !== 6) { $("#pairErr").textContent = "The PIN has 6 digits."; return; }
  try {
    await api("/api/tv/pair", { pin });
    $("#pair").hidden = true;
    toast(`TV paired with your ${PC}`, "ok");
    remoteLoop();
    refresh();
  } catch (err) {
    $("#pairErr").textContent = err.message;
    pin = "";
    drawPin();
  }
}

/* ---------------------------------------------------------- streaming */
/* Torrents play while they download: the PC fetches the video in playing order and hands
   it to the TV. A short buffer first, then the player starts by itself. */
const canStream = (r) => !playable(r) && !!(r.infohash || r.magnet || r.has_torrent);
let streamRun = 0;
function stopStream() {
  streamRun++;
  const s = state.stream;
  state.stream = null;
  if (s && s.hash) api("/api/tv/bt/stop", { hash: s.hash }).catch(() => {});
}
function streamStage(text, frac = null) {
  $("#sStage").textContent = text;
  $("#sBar").hidden = frac === null;
  if (frac !== null) $("#sFill").style.width = `${Math.round(Math.min(1, Math.max(0, frac)) * 100)}%`;
}
function streamButtons(s, st) {
  const btns = [];
  if (st && st.url) {
    btns.push(h("button", { type: "button", class: "act primary", onclick: () => launchStream(s, st, true) },
      s.launched ? "▶  Play again" : "▶  Play now"));
    if (BRIDGE && BRIDGE.playExternal) {
      btns.push(h("button", { type: "button", class: "act", onclick: () => BRIDGE.playExternal(location.origin + st.url, s.title) },
        "Play in another app (VLC…)"));
    }
  }
  btns.push(h("button", { type: "button", class: "act", onclick: () => history.back() }, "✕  Stop"));
  const had = $("#sActions").contains(document.activeElement) ? document.activeElement.textContent : null;
  $("#sActions").replaceChildren(...btns);
  // keep focus on the same button across refreshes, else the first one
  const same = had && btns.find((b) => b.textContent === had);
  const elsewhere = $("#sFiles").contains(document.activeElement) || $("#sSubs").contains(document.activeElement);
  if (topOverlay() === "streamBox" && !elsewhere) (same || btns[0]).focus({ preventScroll: true });
}

async function startStream(r, title, resume = null) {
  const run = ++streamRun;
  push("streamBox");
  const s = { hash: "", index: resume ? resume.index : null, title, thumb: r.thumb || "",
    quality: r.quality?.label || "", private: r.category === "adult", resume: resume ? resume.pos : 0,
    asked: !!resume, prepared: false, launched: false };
  state.stream = s;
  state.playing = s.private ? null : { title, category: likeCat(r.category), year: r.year, thumb: r.thumb || "", rid: r.id };
  const alive = () => run === streamRun;
  $("#sTitle").textContent = title;
  $("#sStats").textContent = "";
  $("#sWarn").replaceChildren();
  $("#sFiles").replaceChildren();
  $("#sSubs").hidden = true;
  streamStage("Connecting…");
  streamButtons(s, null);
  const fail = (msg) => { if (alive()) { streamStage(msg); $("#sBar").hidden = true; streamButtons(s, null); } };

  // 1. hand the torrent to the PC's streaming engine (set up once, the first time)
  while (alive() && !s.hash) {
    let d;
    try { d = await api("/api/tv/bt/start", resume ? { hash: resume.hash } : { id: r.id }); } catch (err) {
      if (!(err instanceof NeedPair)) fail("⚠ " + err.message);
      return;
    }
    if (!d.installing) { s.hash = d.hash; break; }
    const st = await api("/api/tv/bt/status?" + qs({ h: "" })).catch(() => ({}));
    if (st.stage === "installing") {
      streamStage(st.state === "scanning" ? `Setting up streaming on your ${PC} (one time): virus-checking it…`
        : `Setting up streaming on your ${PC} (one time, about 60 MB)…`, null);
    } else if (st.stage === "error") return fail("⚠ " + st.error);
    await sleep(1500);
  }

  // 2. follow it: file list, safety check, buffer, then play
  while (alive()) {
    let st;
    try { st = await api("/api/tv/bt/status?" + qs({ h: s.hash, i: s.index ?? "" })); } catch (err) {
      if (!(err instanceof NeedPair)) fail("⚠ " + err.message);
      return;
    }
    if (!alive()) return;
    const peers = st.total_peers ? `${st.peers} of ${st.total_peers} peers connected` : "looking for peers";
    $("#sStats").textContent = st.stage === "error" ? "" : [peers, st.speed ? `${fmtSize(st.speed)}/s` : ""].filter(Boolean).join(" · ")
      + (s.quality === "4K" && st.speed && st.speed < 3e6 ? " · 4K needs about 3 MB/s or more: if it stutters, pick a copy with more seeds" : "");
    $("#sWarn").replaceChildren(...(st.warnings || []).map((w) => h("li", { class: "warn", text: "⚠ " + w })));
    if (st.stage === "error") return fail("⚠ " + st.error);
    if (st.stage === "metadata") streamStage("Finding the video…");
    else if (st.stage === "choose") {
      if (s.index === null) {
        if (st.files.length === 1) s.index = st.files[0].index;
        else {
          streamStage(`${st.files.length} videos. Choose one`);
          s.index = await new Promise((pick) => {
            const items = st.files.map((f) => h("button", { type: "button", class: "p-item", onclick: () => pick(f.index) },
              h("span", { dir: "auto", text: f.name }), h("span", { text: [f.resume ? "resume " + fmtTime(f.resume) : "", fmtSize(f.size)].filter(Boolean).join(" · ") })));
            $("#sFiles").replaceChildren(...items);
            items[0].focus();
          });
          if (!alive()) return;
          $("#sFiles").replaceChildren();
        }
      }
      if (!s.prepared) {
        s.prepared = true;
        try { await api("/api/tv/bt/prepare", { hash: s.hash, index: s.index }); } catch (err) { return fail("⚠ " + err.message); }
        loadStreamSubs(s);
        continue;
      }
    } else if (st.stage === "checking") streamStage("Checking it's a real video…");
    else if (st.stage === "buffering") {
      streamStage("Buffering…", st.preload_size ? st.preloaded / st.preload_size : 0);
    } else if (st.stage === "ready") {
      streamStage(s.launched ? "Streaming. Press ▶ Play again to go back to it" : "Ready", 1);
      if (!s.launched) launchStream(s, st);
    }
    if (st.url && !$("#sActions .act.primary")) streamButtons(s, st);
    else if (st.url && s.launched) streamButtons(s, st);
    await sleep(st.stage === "ready" && s.launched ? 3000 : 1000);
  }
}

/* Subtitles: the ones that came with the torrent, plus online ones when the PC has a SubDL key.
   The choice (a language, or Off) is remembered; ▲ in the player switches them too. */
async function loadStreamSubs(s) {
  let subs = [];
  try { subs = (await api("/api/tv/bt/subs?" + qs({ h: s.hash, i: s.index }))).subs; } catch { /* none */ }
  if (state.stream !== s) return;
  s.subs = subs;
  const want = store.get("subLang", "off");
  s.sub = want === "off" ? -1 : subs.findIndex((x) => x.lang === want);
  if (s.sub < 0 && want !== "off" && subs.length) s.sub = subs.findIndex((x) => x.lang === "en");
  drawSubChoice(s);
}
function drawSubChoice(s) {
  const box = $("#sSubs");
  if (!s.subs.length) {
    box.hidden = false;
    box.replaceChildren(h("span", { class: "dym-l", text: "No subtitles found for this video" }));
    return;
  }
  const pick = (i) => () => {
    s.sub = i;
    store.set("subLang", i < 0 ? "off" : s.subs[i].lang || "off");
    drawSubChoice(s);
    $("#sSubs .chip[aria-pressed=true]")?.focus();
  };
  box.hidden = false;
  box.replaceChildren(h("span", { class: "dym-l", text: "Subtitles" }),
    h("button", { type: "button", class: "chip", "aria-pressed": String(s.sub < 0), text: "Off", onclick: pick(-1) }),
    ...s.subs.map((x, i) => h("button", { type: "button", class: "chip", "aria-pressed": String(s.sub === i), text: x.label, onclick: pick(i) })),
    h("span", { class: "dym-l", text: "· ▲ in the player turns them on or off" }));
}

function launchStream(s, st, byHand = false) {
  const f = (st.files || []).find((x) => x.index === s.index) || {};
  if (!s.asked && f.resume > 0 && !byHand) {
    s.asked = true;
    withResume(f.resume, s.title, (from) => { s.resume = from; launchStream(s, st, true); });
    return;
  }
  s.launched = true;
  const url = location.origin + st.url;
  const key = s.private ? "" : `bt:${s.hash}:${s.index}`;
  const name = (st.files || []).length > 1 ? f.name || "" : "";
  if (native()) {
    const payload = { title: s.title, index: 0, progress: s.private ? "" : location.origin + st.progress,
      like: s.private ? null : nativeLike(st.like, s.title),
      items: [{ name: name || s.title, key, thumb: s.private ? "" : s.thumb, resume: s.resume || 0,
        urls: [url], labels: [s.quality || "Stream"], bitrates: [0],
        subs: (s.subs || []).map((x) => ({ label: x.label, url: location.origin + x.url })), sub: s.sub ?? -1 }] };
    if (BRIDGE.playNative(JSON.stringify(payload)) !== "ok") toast("Couldn't start the player", "bad");
  } else {
    startPlayer([{ url: st.url, name: name || s.title, key, label: s.quality }], 0, s.title, s.resume || 0);
  }
  s.resume = 0;
}

/* ----------------------------------------------------- remote control */
function focusables() {
  const scope = (!$("#pair").hidden && $("#pair")) || (topOverlay() && $("#" + topOverlay())) || document;
  return [...scope.querySelectorAll("button:not(:disabled), input")].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
}
function move(dir) {
  const list = focusables();
  if (!list.length) return;
  const cur = document.activeElement;
  if (!list.includes(cur)) {
    // Nothing focused (e.g. right after a search): start on what's on screen, never the search box,
    // which would pop up the keyboard
    const onScreen = (el) => { const b = el.getBoundingClientRect(); return b.bottom > 0 && b.top < innerHeight; };
    const first = list.find((el) => el.closest("#main") && onScreen(el)) || list.find((el) => el.tagName !== "INPUT" && onScreen(el)) || list[0];
    first.focus({ preventScroll: true });
    first.scrollIntoView({ block: "nearest", inline: "nearest" });
    return;
  }
  const a = cur.getBoundingClientRect();
  const ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  let best = null, bestScore = Infinity;
  for (const el of list) {
    if (el === cur) continue;
    const b = el.getBoundingClientRect();
    const bx = b.left + b.width / 2, by = b.top + b.height / 2;
    let main, cross;
    if (dir === "right") { if (b.left < a.right - 2 && bx <= ax + 1) continue; main = Math.max(0, b.left - a.right); cross = Math.abs(by - ay); }
    else if (dir === "left") { if (b.right > a.left + 2 && bx >= ax - 1) continue; main = Math.max(0, a.left - b.right); cross = Math.abs(by - ay); }
    else if (dir === "down") { if (b.top < a.bottom - 2 && by <= ay + 1) continue; main = Math.max(0, b.top - a.bottom); cross = Math.abs(bx - ax); }
    else { if (b.bottom > a.top + 2 && by >= ay - 1) continue; main = Math.max(0, a.top - b.bottom); cross = Math.abs(bx - ax); }
    if ((dir === "left" || dir === "right") && cross > Math.max(a.height, b.height)) continue;   // stay on the row
    const score = main + cross * (dir === "left" || dir === "right" ? 3 : 0.6);
    if (score < bestScore) { bestScore = score; best = el; }
  }
  const scroller = scrollContainer();
  if (!best) {
    // Nothing further that way: still scroll, so the top is always reachable and long text can be read
    if (dir === "up") scroller.scrollTop = 0;
    else if (dir === "down") scroller.scrollTop += scroller.clientHeight * 0.6;
    return;
  }
  best.focus({ preventScroll: true });
  // Instant scrolling: smooth scrolling stutters on TV hardware
  const bTop = best.getBoundingClientRect().top;
  const nothingAbove = !list.some((el) => el !== best && el.getBoundingClientRect().bottom <= bTop + 2);
  if (nothingAbove) scroller.scrollTop = 0;                  // first row: show everything above it (title, poster, header)
  else best.scrollIntoView({ block: best.classList.contains("card") ? "center" : "nearest", inline: "nearest" });
}
/* What scrolls right now: the open screen (details, pickers, Downloads…) or the page itself */
function scrollContainer() {
  if (!$("#pair").hidden) return $("#pair");
  const id = topOverlay();
  return id ? $("#" + id) : (document.scrollingElement || document.documentElement);
}

document.addEventListener("keydown", (e) => {
  if (!$("#pair").hidden && /^[0-9]$/.test(e.key)) { padKey(e.key); e.preventDefault(); return; }
  if (topOverlay() === "adultBox" && /^[0-9]$/.test(e.key)) { adultKey(e.key); e.preventDefault(); return; }
  if (topOverlay() === "player" && $("#pair").hidden) {
    if (playerKey(e)) { e.preventDefault(); return; }
  }
  if (["GoBack", "BrowserBack", "Escape", "Backspace"].includes(e.key) && e.target.tagName !== "INPUT") {
    if (window.buzzBack()) e.preventDefault();
    return;
  }
  const dir = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" }[e.key];
  if (!dir) return;
  const t = e.target;
  if (t.tagName === "INPUT" && (dir === "left" || dir === "right")) {
    const atEdge = dir === "left" ? t.selectionStart === 0 : t.selectionEnd === t.value.length;
    if (!atEdge) return;
  }
  e.preventDefault();
  move(dir);
});

/* Pointer devices (Meta Quest controllers or hands, touch, mouse): pointing at a button
   highlights it like the remote's focus does, and a ← Back button replaces the Back key. */
const pointerMode = () => {
  document.body.classList.add("pointer");
  document.documentElement.classList.add("pointer");   // desk density: more fits on a panel or monitor
};
if (/OculusBrowser|Quest/i.test(navigator.userAgent)) pointerMode();
document.addEventListener("pointerdown", pointerMode, { once: true, passive: true });
document.addEventListener("pointerover", (e) => {
  if (!document.body.classList.contains("pointer")) return;
  const b = e.target.closest && e.target.closest("button");
  const typing = document.activeElement && document.activeElement.tagName === "INPUT";
  if (b && !b.disabled && b !== document.activeElement && !typing) b.focus({ preventScroll: true });
});
$("#backFab").addEventListener("click", () => window.buzzBack());
/* BuzzTorrent VR (Meta Quest): step into the cinema and pick a room without starting a video */
renderHostSwitch();
if (window.BuzzVR) {
  $("#vrBtn").hidden = false;
  $("#vrBtn").addEventListener("click", () => window.BuzzVR.openCinema());
}

/* -------------------------------------------------------------- start */
$("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); $("#q").blur(); runSearch($("#q").value); });
$("#homeBtn").addEventListener("click", () => renderHome());
$("#libBtn").addEventListener("click", openLibrary);
$("#dlBtn").addEventListener("click", openDownloads);

/* Updates on the PC reach the TV by themselves: when the TV page changes, reload it as
   soon as nothing is open (never in the middle of a video), keeping the current search. */
let uiVersion = null, updateWaiting = false;
async function checkForUpdate() {
  try {
    const hello = await api("/api/tv/hello?" + qs({ app: APP_VERSION }));
    if (uiVersion === null) uiVersion = hello.ui;
    else if (hello.ui && hello.ui !== uiVersion) { updateWaiting = true; reloadIfIdle(); }
  } catch { /* PC offline: try again later */ }
}
function reloadIfIdle() {
  if (!updateWaiting || state.stack.length || !$("#pair").hidden) return;
  store.set("justUpdated", true);
  location.hash = state.query && state.cat !== "adult" ? qs({ q: state.query, cat: searchCat(), lang: state.lang }) : "";
  location.reload();
}
setInterval(checkForUpdate, 60000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) checkForUpdate(); });

/* ----------------------------------------------------- private section */
let adultPin = "";
async function loadAdultState() {
  try {
    const s = await api("/api/adult/state");
    adult.shown = s.enabled;
    adult.unlocked = s.unlocked;
  } catch { adult.shown = adult.unlocked = false; }
  if (!adult.shown && state.cat === "adult") state.cat = "movies";
  renderChips();
}
function askAdultPin() {
  push("adultBox");
  adultPin = "";
  drawAdultPin();
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"];
  $("#adultPad").replaceChildren(...keys.map((k) => h("button", { type: "button", text: k, onclick: () => adultKey(k) })));
  $("#adultErr").textContent = "";
  $("#adultPad button").focus();
}
function drawAdultPin() {
  $("#adultPinShow").replaceChildren(...Array.from({ length: Math.max(4, adultPin.length) }, (_, i) =>
    h("span", { class: i === adultPin.length ? "on" : "", text: adultPin[i] ? "•" : "" })));
}
async function adultKey(k) {
  $("#adultErr").textContent = "";
  if (k === "⌫") adultPin = adultPin.slice(0, -1);
  else if (k !== "OK" && adultPin.length < 8) adultPin += k;
  drawAdultPin();
  if (k !== "OK") return;
  try {
    await api("/api/adult/unlock", { pin: adultPin });
    adult.unlocked = true;
    history.back();                          // close the PIN pad
    state.cat = "adult";
    renderChips();
    renderHome();
  } catch (err) {
    $("#adultErr").textContent = err.message;
    adultPin = "";
    drawAdultPin();
  }
}
function leaveAdult(msg) {
  adult.unlocked = false;
  if (state.cat !== "adult") return;
  closeAll();
  state.cat = store.get("cat", "movies");
  if (msg) toast(msg);
  renderChips();
  renderHome();
}
async function lockAdult() {
  try { await api("/api/adult/lock", {}); } catch { /* locked anyway */ }
  leaveAdult("Private section locked");
}

/* ------------------------------------------------------- phone remote */
let remoteRunning = false;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function remoteLoop() {
  if (remoteRunning) return;
  remoteRunning = true;
  let seq = -1;
  while (true) {
    if (document.hidden) { await sleep(2000); continue; }
    try {
      const d = await api("/api/tv/remote/poll?" + qs({ after: seq }));
      for (const cmd of d.commands) await runRemote(cmd);
      seq = d.seq;
    } catch (err) {
      if (err instanceof NeedPair) { remoteRunning = false; return; }
      seq = -1;
      await sleep(5000);
    }
  }
}
function closeAll() {
  while (state.stack.length) closeTop();
}
async function getResult(id) {
  return state.byId.get(id) || (await api("/api/tv/result?" + qs({ id })));
}
async function runRemote(cmd) {
  try {
    if (cmd.action === "search") {
      closeAll();
      if (cmd.cat && TABS.some(([id]) => id === cmd.cat)) state.cat = cmd.cat;
      if (cmd.lang && LANG_NAME[cmd.lang]) state.lang = cmd.lang;
      renderChips();
      toast(`📱 ${cmd.q}`);
      await runSearch(cmd.q);
    } else if (cmd.action === "home") {
      closeAll();
      renderHome();
    } else if (cmd.action === "open" || cmd.action === "play") {
      const r = await getResult(cmd.id);
      closeAll();
      await openDetail(r);
      if (cmd.action === "play") (canStream(r) ? startStream(r, $("#dTitle").textContent) : play(r, $("#dTitle").textContent));
    }
  } catch (err) {
    if (!(err instanceof NeedPair)) toast(err.message, "bad");
  }
}

/* ------------------------------------------------------------- voice */
/* Spoken searches often come with extra words: "search for sholay movie" -> "sholay" */
function cleanQuery(q) {
  const t = String(q || "").trim().replace(/[.!?।]+$/u, "");
  const cmd = /^(please\s+)?(search(\s+for)?|find|play|show(\s+me)?|watch|look\s+for|open)\s+/i;
  if (!cmd.test(t)) return t;
  const rest = t.replace(cmd, "");
  return rest.replace(/\s+(full\s+)?(movie|film|please)$/i, "") || rest;
}
const canVoice = !!(BRIDGE && BRIDGE.voiceSearch && (!BRIDGE.canVoice || BRIDGE.canVoice()));
function startVoice(lang = "en-IN") {
  if (!canVoice) { $("#q").focus(); return; }
  $("#q").blur();                                  // no on-screen keyboard left behind the voice prompt
  if (BRIDGE.voiceSearch(lang) !== "ok") toast("Voice search isn't available on this TV. Use the keyboard's mic instead", "bad");
}
window.startVoice = startVoice;
/* Called by the Android app with what was heard */
window.onVoice = (text) => {
  const q = cleanQuery(text);
  if (!q) return;
  closeAll();
  runSearch(q);
};
if (canVoice) {
  $("#micBtn").hidden = $("#micHiBtn").hidden = false;
  $("#micBtn").addEventListener("click", () => startVoice("en-IN"));
  $("#micHiBtn").addEventListener("click", () => startVoice("hi-IN"));
}

async function start() {
  renderChips();
  if (store.get("justUpdated", false)) { store.set("justUpdated", false); toast("BuzzTorrent was updated", "ok"); }
  try {
    const hello = await api("/api/tv/hello?" + qs({ app: APP_VERSION }));
    uiVersion = hello.ui;
    if (!hello.paired) { showPair(); return; }
  } catch (err) {
    return offlineView(err);
  }
  remoteLoop();
  loadAdultState();
  // Deep link, e.g. /tv#q=ramayan&cat=tv (handy as a TV-browser bookmark)
  const link = new URLSearchParams(location.hash.slice(1));
  if (TABS.some(([id]) => id === link.get("cat"))) state.cat = link.get("cat");
  if (LANG_NAME[link.get("lang")]) state.lang = link.get("lang");
  renderChips();
  if (link.get("q")) {
    await runSearch(link.get("q"));
    const n = parseInt(link.get("open") || "", 10);
    if (n > 0) document.querySelectorAll("#main .card")[n - 1]?.click();
  } else renderHome();
}
start();
