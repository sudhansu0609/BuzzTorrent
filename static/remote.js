"use strict";
/* BuzzTorrent phone remote: search here, results appear on the living-room TV. */
const $ = (s, el = document) => el.querySelector(s);
const PC = document.documentElement.dataset.host || "PC";     // "PC" or "Mac", set by the server
document.querySelectorAll(".pc").forEach((el) => { el.textContent = PC; });

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
  get(k, d) { try { const v = localStorage.getItem("remote." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("remote." + k, JSON.stringify(v)); } catch { /* storage off */ } },
};

const CATS = [["movies", "Movies"], ["tv", "TV Shows"], ["music", "Music"], ["all", "Everything"]];
const LANGS = [["any", "All languages"], ["hi", "Hindi"], ["bho", "Bhojpuri"], ["bn", "Bengali"], ["ur", "Urdu"],
  ["ta", "Tamil"], ["te", "Telugu"], ["mr", "Marathi"], ["pa", "Punjabi"], ["en", "English"]];
const CAT_NOUN = { movies: "Film", tv: "TV", music: "Music", books: "Book", games: "Game", software: "Software" };
const state = { cat: store.get("cat", "movies"), lang: store.get("lang", "any"), sort: store.get("sort", "match"), view: 0, items: [] };
if (!CATS.some(([id]) => id === state.cat)) state.cat = "movies";
if (!LANGS.some(([id]) => id === state.lang)) state.lang = "any";

class NeedPair extends Error {}
async function api(path, body) {
  const opts = body === undefined ? { credentials: "same-origin", cache: "no-store" } : {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-BuzzTorrent": "1" }, body: JSON.stringify(body),
  };
  let res;
  try { res = await fetch(path, opts); } catch { throw new Error(`Can't reach BuzzTorrent. Is the ${PC} on, and this phone on the home Wi-Fi?`); }
  let data;
  try { data = await res.json(); } catch { throw new Error(`The ${PC} answered with an error (${res.status})`); }
  if (res.status === 401 && data.pair) { showPair(); throw new NeedPair("pair first"); }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
function toast(msg, kind = "") {
  const t = h("div", { class: `toast ${kind}`, role: "status", text: msg });
  $("#toasts").append(t);
  setTimeout(() => t.remove(), 3200);
}
const qs = (o) => new URLSearchParams(o).toString();
function fmtSize(b) {
  if (!b) return "";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return `${b >= 10 || i < 2 ? Math.round(b) : b.toFixed(1)} ${u[i]}`;
}

function chips() {
  $("#cats").replaceChildren(...CATS.map(([id, label]) => h("button", { type: "button", class: "chip", "aria-pressed": String(id === state.cat),
    text: label, onclick: () => { state.cat = id; store.set("cat", id); chips(); } })));
  $("#langs").replaceChildren(...LANGS.map(([id, label]) => h("button", { type: "button", class: "chip", "aria-pressed": String(id === state.lang),
    text: label, onclick: () => { state.lang = id; store.set("lang", id); chips(); } })));
}

async function send(cmd, done) {
  try {
    await api("/api/tv/remote", cmd);
    if (done) toast(done, "ok");
    return true;
  } catch (err) {
    if (!(err instanceof NeedPair)) toast(err.message, "bad");
    return false;
  }
}

/* Spoken searches often come with extra words: "search for sholay movie" -> "sholay" */
function cleanQuery(q) {
  const t = q.trim().replace(/[.!?।]+$/u, "");
  const cmd = /^(please\s+)?(search(\s+for)?|find|play|show(\s+me)?|watch|look\s+for|open)\s+/i;
  if (!cmd.test(t)) return t;                    // typed titles stay as they are ("Bee Movie")
  const rest = t.replace(cmd, "");
  return rest.replace(/\s+(full\s+)?(movie|film|please)$/i, "") || rest;
}

async function search(e) {
  e?.preventDefault();
  const q = cleanQuery($("#q").value);
  if (!q) { $("#q").focus(); return; }
  $("#q").value = q;
  $("#q").blur();
  const view = ++state.view;
  const ok = await send({ action: "search", q, cat: state.cat, lang: state.lang }, "Showing on your TV");
  if (!ok) return;
  $("#results").replaceChildren(h("li", { class: "status" }, h("span", { class: "spin" }), "Searching…"));
  try {
    const d = await api("/api/search?" + qs({ q, cat: state.cat, lang: state.lang }));
    if (view !== state.view) return;
    state.items = d.results.filter((r) => r.verdict !== "danger");
    drawResults();
  } catch (err) {
    if (!(err instanceof NeedPair)) $("#results").replaceChildren(h("li", { class: "status", text: err.message }));
  }
}

/* Sort: best match (the PC's ranking) or most seeds (seeds = how fast it streams) */
const SORTS = [["match", "Best match"], ["seeds", "Most seeds"], ["size", "Biggest"]];
function drawResults() {
  const items = [...state.items];
  if (state.sort === "seeds") items.sort((a, b) => (b.seeders ?? -1) - (a.seeders ?? -1));
  if (state.sort === "size") items.sort((a, b) => (b.size || 0) - (a.size || 0));
  $("#sorts").hidden = !items.length;
  $("#sorts").replaceChildren(...SORTS.map(([id, label]) => h("button", { type: "button", class: "chip", "aria-pressed": String(id === state.sort),
    text: label, onclick: () => { state.sort = id; store.set("sort", id); drawResults(); } })));
  const shown = items.slice(0, 60);
  $("#results").replaceChildren(...(shown.length ? shown.map(row)
    : [h("li", { class: "status", text: "Nothing found. Try another spelling or language." })]));
  loadPosters(shown.filter((r) => !r.thumb));
}

/* Torrents have no artwork: the PC finds posters on Wikipedia, a moment after the list */
async function loadPosters(items) {
  if (!items.length) return;
  const view = state.view;
  try {
    const { posters } = await api("/api/posters?" + qs({ ids: items.map((r) => r.id).join(",") }));
    if (view !== state.view) return;
    for (const r of items) {
      if (!posters[r.id]) continue;
      r.thumb = posters[r.id];
      const ph = document.querySelector(`.res[data-id="${CSS.escape(r.id)}"] .ph`);
      if (ph) ph.replaceWith(h("img", { src: r.thumb, alt: "", loading: "lazy" }));
    }
  } catch { /* posters are a nicety */ }
}

/* Details under a result: summary, cast, director, runtime, genres (Wikipedia/Wikidata) */
async function toggleDetails(r, li, btn) {
  const open = li.querySelector(".res-more");
  if (open) { open.remove(); btn.textContent = "Details"; return; }
  btn.textContent = "Hide details";
  const box = h("div", { class: "res-more" }, h("span", { class: "spin" }), "Looking it up…");
  li.append(box);
  try {
    const d = await api("/api/details?" + qs({ id: r.id }));
    const facts = (d.facts || []).filter((f) => f.label !== "Cast").slice(0, 3);
    box.replaceChildren(
      h("div", { class: "more-meta", text: [d.year, d.runtime, (d.genres || []).slice(0, 3).join(", "), d.language].filter(Boolean).join(" · ") }),
      d.summary ? h("p", { class: "more-sum", dir: "auto", text: d.summary }) : h("p", { class: "more-sum", text: "No summary found for this one." }),
      d.cast && d.cast.length ? h("p", {}, h("b", { text: "Cast: " }), d.cast.slice(0, 10).join(", ")) : null,
      ...facts.map((f) => h("p", {}, h("b", { text: f.label + ": " }), f.values.join(", "))));
    if (d.poster && !r.thumb) li.querySelector(".ph")?.replaceWith(h("img", { src: d.poster, alt: "" }));
  } catch (err) {
    if (!(err instanceof NeedPair)) box.textContent = err.message;
  }
}

function row(r) {
  const free = (r.sources || []).includes("Internet Archive");
  let img = h("div", { class: "ph" });
  if (r.thumb) {
    img = h("img", { src: r.thumb, alt: "", loading: "lazy" });
    img.addEventListener("error", () => img.replaceWith(h("div", { class: "ph" })), { once: true });
  }
  const seeds = free || r.seeders == null ? null
    : h("span", { class: "seeds " + (r.seeders >= 20 ? "safe" : r.seeders >= 5 ? "" : "caution"),
      text: `${r.seeders} seed${r.seeders === 1 ? "" : "s"}${r.seeders < 5 ? " (slow)" : ""}` });
  const meta = h("div", { class: "res-m" },
    h("span", { class: r.verdict, text: r.verdict === "safe" ? "Safe" : r.verdict === "caution" ? "Caution" : "Unrated" }),
    " · ", [r.year, fmtSize(r.size)].filter(Boolean).join(" · "),
    r.quality ? [" · ", h("b", { text: r.quality.label })] : null,
    seeds ? [" · ", seeds] : null);
  const li = h("li", { class: "res", "data-id": r.id });
  const more = h("button", { type: "button", text: "Details", onclick: () => toggleDetails(r, li, more) });
  li.append(img, h("div", { class: "res-body" },
    h("div", { class: "res-t", dir: "auto", text: r.title }), meta,
    h("div", { class: "res-btns" },
      h("button", { type: "button", class: "primary", text: free ? "▶ Play on TV" : "▶ Stream on TV",
        onclick: () => send({ action: "play", id: r.id }, free ? "Playing on your TV" : "Starting the stream on your TV") }),
      h("button", { type: "button", text: "Open on TV", onclick: () => send({ action: "open", id: r.id }, "Opened on your TV") }),
      more,
      h("button", { type: "button", text: "☆ Watchlist", onclick: async (e) => {
        try {
          await api("/api/tv/watch", { title: r.title, category: ["movies", "tv", "music"].includes(r.category) ? r.category : "movies",
            year: r.year, thumb: r.thumb || "", quality: r.quality?.height || 0, free: free });
          e.target.textContent = "★ On watchlist";
          toast("Added. You'll hear when a better or free copy turns up", "ok");
        } catch (err) {
          if (!(err instanceof NeedPair)) toast(err.message, "bad");
        }
      } }))));
  return li;
}

/* pairing */
function showPair() {
  $("#app").hidden = true;
  $("#pairBox").hidden = false;
  $("#status").textContent = "Not paired yet";
  $("#status").classList.remove("ok");
  $("#pin").focus();
}
$("#pairForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#pairErr").textContent = "";
  try {
    await api("/api/tv/pair", { pin: $("#pin").value.trim() });
    $("#pin").value = "";
    ready();
  } catch (err) {
    $("#pairErr").textContent = err.message;
  }
});

function ready() {
  $("#pairBox").hidden = true;
  $("#app").hidden = false;
  $("#status").textContent = "Connected · results show on your TV";
  $("#status").classList.add("ok");
}

$("#searchForm").addEventListener("submit", search);
$("#homeBtn").addEventListener("click", () => send({ action: "home" }, "TV is back on the home screen"));

/* After an update on the PC, an open phone page reloads itself (keeping the last search box text) */
let uiVersion = null;
async function checkForUpdate() {
  try {
    const hello = await api("/api/tv/hello");
    if (uiVersion && hello.ui && hello.ui !== uiVersion) location.reload();
  } catch { /* PC offline: try later */ }
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) checkForUpdate(); });
setInterval(() => { if (!document.hidden) checkForUpdate(); }, 60000);

(async function start() {
  chips();
  try {
    const hello = await api("/api/tv/hello");
    uiVersion = hello.ui;
    if (!hello.paired) { showPair(); return; }
    ready();
  } catch (err) {
    $("#status").textContent = err.message;
  }
})();
