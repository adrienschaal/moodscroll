// moodscroll web app: no framework, two views (home and note), routed by the URL hash.

const $ = (sel, el = document) => el.querySelector(sel);
const view = $("#view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const ts = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;
// What a library tile says it is. A photo post's frames are its pictures, numbered by slide.
const KINDS = { reel: "Reel", video: "Video", photo: "Photo", carousel: "Carousel" };
const kindLabel = (i) => i.kind === "carousel" && i.slides ? `Carousel · ${i.slides}` : KINDS[i.kind] || "Video";
const isPhotos = (m) => m.kind === "photo" || m.kind === "carousel";

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

// --- Routing ------------------------------------------------------------------------

let pollTimer = null;
let liveTimer = null;
function route() {
  clearTimeout(pollTimer);
  clearInterval(liveTimer);
  // #/note/<folder>, or #/note/<folder>?at=5 from a search: open at that slide or moment
  const m = location.hash.match(/^#\/note\/([^?]+)(?:\?at=([\d.]+))?$/);
  if (m) showNote(decodeURIComponent(m[1]), m[2] === undefined ? null : Number(m[2]));
  else if (location.hash === "#/import") showImport();
  else showHome();
}
window.addEventListener("hashchange", route);

let searchTimer = null;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    if (location.hash.startsWith("#/note/")) location.hash = "#/";
    else loadLibrary();
  }, 200);
});

// --- Home: add videos, follow jobs, browse the library ------------------------------

function showHome() {
  view.onclick = null;
  document.title = "MooDscroll";
  view.replaceChildren($("#home").content.cloneNode(true));
  $("#add-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = new FormData();
    body.append("url", $("#url").value);
    await submit(body);
    $("#url").value = "";
  });
  $("#file").addEventListener("change", (e) => uploadFiles(e.target.files));

  const drop = $("#drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    const text = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
    else if (text) { const b = new FormData(); b.append("url", text.trim()); submit(b); }
  });

  pollJobs();
  loadLibrary();
  loadStatus();
  // Notes written in Claude Code or Codex land in the same library: while anything
  // is waiting, check every few seconds so they appear without a reload.
  liveTimer = setInterval(() => {
    if (status?.waiting && !document.hidden && !$(".menu:not([hidden])")) { loadStatus(); loadLibrary(); pollJobs(); }
  }, 4000);
}

// Without an API key, Claude Code or Codex writes the notes. Say so, with the
// exact words to use, so a video "waiting for notes" never looks broken.
let status = null;
const askBox = (phrase) =>
  `<code>${esc(phrase)}</code> <button class="ghost small" data-copy="${esc(phrase)}">Copy</button>`;

// Who writes the notes, and a switch between the two:
//   assistant  Claude Code or Codex, on the user's subscription (no key)
//   api        this app, with the user's Claude API key
let keyFormOpen = false;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const money = (usd) => (usd < 0.01 ? "under $0.01" : `$${usd.toFixed(2)}`);

async function loadStatus() {
  status = await api("/api/status");
  const box = $("#banner");
  if (!box || keyFormOpen) return;  // don't wipe a key being typed
  box.innerHTML = status.mode === "api" ? apiBanner() : assistantBanner();
}

function assistantBanner() {
  const waiting = status.waiting ? `<b>${plural(status.waiting, "post")} waiting for notes.</b> ` : "";
  return `<div class="banner">
    <p><b>Notes are written by Claude Code or Codex</b>, on your subscription. ${waiting}Add videos
    here whenever you like, then tell Claude Code or Codex: ${askBox(status.ask_phrase)}</p>
    <p class="fine">Want this app to write notes by itself?
      <button class="link-btn" data-act="show-key">Use a Claude API key</button>${status.saved_key_off
        ? ` or <button class="link-btn" data-act="key-on">turn your saved key back on</button>` : ""}</p>
    <div id="key-box"></div></div>`;
}

function apiBanner() {
  const n = status.waiting;
  const waiting = n ? `<p>${plural(n, "post")} waiting for notes.
      <button class="small" data-act="write-waiting">Write ${n === 1 ? "it" : "them"} now</button>
      <span class="fine">about ${money(status.waiting_cost)}, based on each video's length</span></p>` : "";
  return `<div class="banner">
    <p><b>Notes are written by this app</b>, with your Claude API key (about $0.04 for a short video).
      <button class="link-btn" data-act="key-off">Switch to Claude Code / Codex</button></p>${waiting}</div>`;
}

function showKeyForm() {
  keyFormOpen = true;
  $("#key-box").innerHTML = `
    <form id="key-form" class="key-form" autocomplete="off">
      <input id="key" type="password" placeholder="sk-ant-…" spellcheck="false" autocomplete="off" required>
      <button type="submit">Save key</button>
      <button type="button" class="ghost" data-act="hide-key">Cancel</button>
    </form>
    <p class="fine">Get a key at <a href="https://platform.claude.com/settings/keys" target="_blank" rel="noopener">platform.claude.com</a>.
      API use is billed by Anthropic, separately from any Claude subscription; about $0.04 a video.
      The key is checked with Anthropic, then saved only on this Mac. Switch back any time.</p>
    <p class="fine error" id="key-msg"></p>`;
  $("#key").focus();
  $("#key-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true; btn.textContent = "Checking…";
    try {
      await api("/api/key", { method: "POST", headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ key: $("#key").value }) });
      keyFormOpen = false;
      loadStatus();
    } catch (err) {
      $("#key-msg").textContent = err.message;
      btn.disabled = false; btn.textContent = "Save key";
    }
  });
}

const closeMenus = (except) =>
  document.querySelectorAll(".menu:not([hidden])").forEach((m) => { if (m !== except) m.hidden = true; });

document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-act]");
  if (!el || !el.dataset.act.startsWith("card-")) closeMenus();
  if (!el) return;
  const act = el.dataset.act;
  e.preventDefault();
  const post = (path) => api(path, { method: "POST" });
  try {
    if (act === "card-menu") {
      const menu = el.nextElementSibling;
      closeMenus(menu);
      menu.hidden = !menu.hidden;
    }
    if (act === "delete-note") {
      if (!confirm(`Delete “${el.dataset.title}”?\n\nIt moves to the Trash. To restore it, drag it from the Trash back into your Moodscroll folder.`)) return;
      await api(`/api/notes/${encodeURIComponent(el.dataset.folder)}`, { method: "DELETE" });
      loadLibrary(); loadStatus(); pollJobs();  // its "waiting for notes" row goes too
    }
    if (act === "stop-import") { await post(`/api/import/stop?batch=${encodeURIComponent(el.dataset.batch)}`); pollJobs(); }
    if (act === "show-key") showKeyForm();
    if (act === "hide-key") { keyFormOpen = false; loadStatus(); }
    if (act === "key-on") { await post("/api/key/on"); keyFormOpen = false; loadStatus(); }
    if (act === "key-off") { await post("/api/key/off"); keyFormOpen = false; loadStatus(); }
    if (act === "write-waiting" || act === "write-this") {
      const one = el.dataset.folder;
      await post("/api/waiting/write" + (one ? `?folder=${encodeURIComponent(one)}` : ""));
      if (one) el.replaceWith(Object.assign(document.createElement("span"), { textContent: "Writing notes…" }));
      else { loadStatus(); pollJobs(); }
    }
  } catch (err) {
    alert(err.message);
  }
});

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  e.preventDefault();
  await navigator.clipboard.writeText(b.dataset.copy);
  b.textContent = "Copied";
  setTimeout(() => (b.textContent = "Copy"), 1500);
});
window.addEventListener("focus", () => {
  if (location.hash.startsWith("#/note/")) return;
  loadStatus(); loadLibrary();
});

async function uploadFiles(files) {
  for (const f of files) {
    const body = new FormData();
    body.append("file", f);
    await submit(body);
  }
}

async function submit(body) {
  try {
    await api("/api/jobs", { method: "POST", body });
    pollJobs();
  } catch (err) {
    alert(err.message);
  }
}

let seenDone = new Set();
async function pollJobs() {
  clearTimeout(pollTimer);
  const box = $("#jobs");
  if (!box) return;
  const jobs = await api("/api/jobs");
  const batches = {};
  jobs.filter((j) => j.batch).forEach((j) => (batches[j.batch] ||= []).push(j));
  box.innerHTML = Object.entries(batches).map(([id, list]) => importRow(id, list)).join("") +
    jobs.filter((j) => !j.batch).map((j) => `
    <div class="job">
      ${j.status === "running" ? '<div class="spinner"></div>' : ""}
      <span class="pill ${j.waiting ? "waiting" : j.status}">${j.waiting ? "waiting for notes" : j.status}</span>
      <span class="label">${esc(j.label)}</span>
      <span class="step">${esc(j.step || j.error || (j.notes_error ? "notes failed: " + j.notes_error : ""))}</span>
      ${j.folder ? `<a href="#/note/${encodeURIComponent(j.folder)}">Open note →</a>` : ""}
    </div>`).join("");

  const newlyDone = jobs.filter((j) => j.status === "done" && !seenDone.has(j.id));
  newlyDone.forEach((j) => seenDone.add(j.id));
  if (newlyDone.length) { loadLibrary(); loadStatus(); }
  if (jobs.some((j) => j.status === "queued" || j.status === "running")) {
    pollTimer = setTimeout(pollJobs, 1000);
  }
}

function importRow(id, list) {
  const count = (s) => list.filter((j) => j.status === s).length;
  const done = count("done"), skipped = count("skipped"), failed = count("failed");
  const left = count("queued") + count("running");
  const running = list.find((j) => j.status === "running") || list.find((j) => j.status === "queued" && j.step);
  const total = list.length - count("cancelled");
  const bits = [skipped && `${skipped} skipped`, failed && `${failed} failed`,
                count("cancelled") && `${count("cancelled")} stopped`].filter(Boolean).join(" · ");
  const problems = list.filter((j) => j.status === "failed");
  return `<div class="job import-job">
      ${left ? '<div class="spinner"></div>' : ""}
      <span class="pill ${left ? "running" : "done"}">${left ? "importing" : "imported"}</span>
      <span class="label">Instagram saved posts: ${done + skipped + failed} of ${total}${bits ? " · " + bits : ""}</span>
      <span class="step">${running ? esc(`${running.label}: ${running.step || "starting"}`) : ""}</span>
      ${left ? `<button class="small ghost" data-act="stop-import" data-batch="${esc(id)}">Stop</button>` : ""}
      ${problems.length ? `<details class="import-fails"><summary>Why ${problems.length === 1 ? "one" : "some"} failed</summary>
        ${problems.map((j) => `<p><b>${esc(j.label)}</b>: ${esc(j.error)}</p>`).join("")}
        <p class="fine">Private or deleted posts can't be downloaded. Drop the same export again later to retry the
        rest: posts already in your library are skipped.</p></details>` : ""}
    </div>`;
}

let category = null;
async function loadLibrary() {
  const grid = $("#library");
  if (!grid) return;
  const q = $("#search").value.trim();
  const items = await api(`/api/library?q=${encodeURIComponent(q)}`);
  $("#lib-title").textContent = q ? `Results for “${q}”` : `Library · ${items.length}`;

  const cats = [...new Set(items.map((i) => i.category).filter(Boolean))].sort();
  $("#cats").innerHTML = cats.map((c) =>
    `<button class="chip ${c === category ? "on" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("");
  $("#cats").onclick = (e) => {
    const c = e.target.dataset.cat;
    if (!c) return;
    category = category === c ? null : c;
    loadLibrary();
  };

  const shown = items.filter((i) => !category || i.category === category);
  grid.innerHTML = shown.length ? shown.map((i) => `
    <div class="card">
      <a class="card-link" href="#/note/${encodeURIComponent(i.folder)}${i.match ? `?at=${i.match.t}` : ""}">
        <div class="thumb" style="background-image:url('${i.thumb ? `/media/${encodeURIComponent(i.folder)}/frames/${i.thumb}` : ""}')">
          <span class="kind kind-${esc(i.kind || "video")}">${esc(kindLabel(i))}</span></div>
        <div class="body">
          ${i.has_notes ? "" : '<span class="badge">Waiting for notes</span>'}
          <div class="title">${esc(i.title || i.folder)}</div>
          <div class="sub">${esc([i.author, i.category].filter(Boolean).join(" · "))}</div>
          ${i.match ? `<div class="hit"><b>${esc(isPhotos(i) ? `Slide ${i.match.t}` : ts(i.match.t))}</b> ${esc(i.match.text.slice(0, 90))}</div>` : ""}
        </div>
      </a>
      <button class="more" data-act="card-menu" aria-label="More actions" title="More">⋮</button>
      <div class="menu" hidden>
        <button data-act="delete-note" data-folder="${esc(i.folder)}" data-title="${esc(i.title || i.folder)}">Delete</button>
      </div>
    </div>`).join("")
    : `<p class="empty">${q ? "Nothing matches." : "Nothing here yet — paste a link above."}</p>`;
}

// --- Note: video beside the notes, every timestamp clickable ------------------------

async function showNote(folder, openAt = null) {
  clearInterval(liveTimer);
  if (!status) loadStatus().catch(() => {});
  let d;
  try {
    d = await api(`/api/notes/${encodeURIComponent(folder)}`);
  } catch {
    view.innerHTML = `<p class="empty">Note not found. <a href="#/">Back</a></p>`;
    return;
  }
  // The folder is renamed after its title once notes are written; follow it.
  const here = `#/note/${encodeURIComponent(d.folder)}${openAt === null ? "" : `?at=${openAt}`}`;
  if (location.hash !== here) history.replaceState(null, "", here);
  const n = d.notes, m = d.meta;
  const frameUrl = (f) => `/media/${encodeURIComponent(d.folder)}/frames/${f.file}`;
  const title = n?.title || m.title || d.folder;
  const photos = isPhotos(m);
  const at = (t) => (photos ? `${t}` : ts(t));  // a slide number, or a time in the video
  document.title = `${title} · MooDscroll`;

  const list = (items, tag = "ul", cls = "") =>
    items?.length ? `<${tag} class="${cls}">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</${tag}>` : "";
  const section = (name, html) => (html ? `<h3>${name}</h3>${html}` : "");

  view.innerHTML = `
    <p><a href="#/">← Library</a></p>
    <div class="note">
      <aside class="side">
        ${d.video && !photos
          ? `<video id="player" src="${d.video}" controls playsinline preload="metadata"></video>`
          : d.frames[0] ? `<img class="poster" id="slide" src="${frameUrl(d.frames[0])}" alt="">` : ""}
        ${photos && d.frames.length < 2 ? "" : `<div class="frames">${d.frames.map((f, k) =>
          `<button data-t="${f.t}" class="${photos && k === 0 ? "on" : ""}" title="${photos ? `Picture ${f.t}` : `Jump to ${ts(f.t)}`}"><img src="${frameUrl(f)}" alt="" loading="lazy"><span>${at(f.t)}</span></button>`).join("")}</div>`}
      </aside>
      <article>
        <h1>${esc(title)}</h1>
        <div class="meta">${esc([kindLabel(m),
          m.author, m.site, !photos && m.duration_s && ts(m.duration_s)].filter(Boolean).join(" · "))}
          ${m.source?.startsWith("http") ? ` · <a href="${esc(m.source)}" target="_blank" rel="noopener">original</a>` : ""}</div>
        ${n ? `<p class="summary">${esc(n.summary)}</p>`
            : `<div class="banner"><p><b>Waiting for notes.</b>${m.notes_error ? ` (Notes failed: ${esc(m.notes_error)}.)` : ""}
                Tell Claude Code or Codex: ${askBox(status?.ask_phrase || "finish my MooDscroll notes")}${status?.mode === "api"
                  ? ` or <button class="small" data-act="write-this" data-folder="${esc(d.folder)}">Write them now</button>
                      <span class="fine">about ${money(d.est_cost)}</span>` : ""}</p>
                <p class="fine">This page updates by itself when they're written.</p></div>`}
        ${n ? section("Key points", list(n.key_points))
            + section("Details", n.details.length ? `<dl class="details">${n.details.map((x) =>
                `<dt>${esc(x.label)}</dt><dd>${esc(x.value)}</dd>`).join("")}</dl>` : "")
            + section("Steps", list(n.steps, "ol"))
            + section("Claims to verify", list(n.claims_to_verify, "ul", "claims")) : ""}
        <div class="actions">
          <button class="ghost" id="copy">Copy Markdown</button>
        </div>
        ${photos ? "" : section("Transcript", d.paragraphs.length
          ? d.paragraphs.map((p) => `<p class="para"><button class="ts" data-t="${p[0].start}">${ts(p[0].start)}</button>${
              p.map((s) => `<span class="seg" data-t="${s.start}" data-start="${s.start}" data-end="${s.end}">${esc(s.text.trim())}</span>`).join(" ")}</p>`).join("")
          : `<p class="caption">(no speech)</p>`)}
        ${section(photos ? "Text in the pictures" : "On-screen text", d.ocr.map((o) => o.lines.length <= (photos ? 20 : 6)
          ? `<div class="line"><button class="ts" data-t="${o.t}">${at(o.t)}</button><div class="ocr">${o.lines.map(esc).join("<br>")}</div></div>`
          : `<div class="line"><button class="ts" data-t="${o.t}">${at(o.t)}</button><details class="ocr"><summary>${esc(o.lines[0])} <span class="count">· ${o.lines.length} lines${photos ? "" : " on screen"}</span></summary>${o.lines.slice(1).map(esc).join("<br>")}</details></div>`).join(""))}
        ${photos && m.alt_text?.length ? section("Instagram's description of the pictures", list(m.alt_text)) : ""}
        ${m.caption ? `<h3>Caption</h3><details><summary>Show the original caption</summary><p class="caption">${esc(m.caption)}</p></details>` : ""}
      </article>
    </div>`;

  // Any element with data-t seeks the video there.
  const player = $("#player");
  // onclick (not addEventListener) so opening another note replaces the handler.
  view.onclick = (e) => {
    if (e.target.closest("summary")) return;  // opening a folded screen, not seeking
    const t = e.target.closest("[data-t]")?.dataset.t;
    if (t !== undefined && photos) {  // show that picture
      const f = d.frames.find((x) => String(x.t) === t);
      if (f) $("#slide").src = frameUrl(f);
      view.querySelectorAll(".frames button").forEach((b) => b.classList.toggle("on", b.dataset.t === t));
      $("#slide").scrollIntoView({ block: "nearest", behavior: "smooth" });
      return;
    }
    if (t === undefined || !player) return;
    player.currentTime = Number(t);
    player.play();
    // Bring the video back into view so you see what you clicked on.
    const r = player.getBoundingClientRect();
    if (r.top < 70 || r.bottom > innerHeight) player.scrollIntoView({ block: "start" });
  };
  // The video keeps the volume (and mute) you last set, on every note.
  if (player) {
    try {
      const v = JSON.parse(localStorage.getItem("moodscroll-volume") || "null");
      if (v) { player.volume = v.volume; player.muted = v.muted; }
    } catch { /* first time, or storage blocked: browser default */ }
    player.addEventListener("volumechange", () => {
      try { localStorage.setItem("moodscroll-volume", JSON.stringify({ volume: player.volume, muted: player.muted })); } catch { /* not kept */ }
    });
  }
  // Highlight the transcript line being spoken.
  if (player) {
    const lines = [...view.querySelectorAll(".seg")];
    player.addEventListener("timeupdate", () => {
      const now = player.currentTime;
      lines.forEach((l) => l.classList.toggle("now", now >= l.dataset.start && now < l.dataset.end));
    });
  }
  window.scrollTo(0, 0);
  // Opened from a search: go to the slide or moment the query matched, and mark it.
  if (openAt !== null) {
    const target = [...view.querySelectorAll(".line [data-t], .para [data-t]")].find((b) => Number(b.dataset.t) === openAt);
    if (photos) {
      const f = d.frames.find((x) => x.t === openAt);
      if (f) $("#slide").src = frameUrl(f);
      view.querySelectorAll(".frames button").forEach((b) => b.classList.toggle("on", Number(b.dataset.t) === openAt));
    } else if (player) {  // seek once the video can be seeked
      if (player.readyState >= 1) player.currentTime = openAt;
      else player.addEventListener("loadedmetadata", () => { player.currentTime = openAt; }, { once: true });
    }
    const row = target?.closest(".line, .para");
    if (row) { row.classList.add("found"); row.scrollIntoView({ block: "center" }); }
  }
  $("#copy").addEventListener("click", async () => {
    await navigator.clipboard.writeText(d.markdown);
    $("#copy").textContent = "Copied";
  });
  if (!n) {  // waiting: show the notes the moment Claude Code or Codex saves them
    liveTimer = setInterval(async () => {
      if (document.hidden) return;
      const fresh = await api(`/api/notes/${encodeURIComponent(d.folder)}`).catch(() => null);
      if (fresh?.notes) { clearInterval(liveTimer); showNote(fresh.folder, openAt); }
    }, 4000);
  }
}

$("#quit").addEventListener("click", async (e) => {
  e.preventDefault();
  if (!confirm("Quit MooDscroll? Videos still processing will stop.")) return;
  await fetch("/api/quit", { method: "POST" }).catch(() => {});
  document.body.innerHTML = '<main><p class="empty">MooDscroll has quit. Open it again from Applications or Spotlight.</p></main>';
});



// --- Import: the posts you saved on Instagram, from Instagram's own export ---------

let found = null;          // what the export lists
let shownCollection = null;
const picked = new Set();  // shortcodes ticked for import

function showImport() {
  view.onclick = null;
  document.title = "Import saved posts · MooDscroll";
  found = null; picked.clear(); shownCollection = null;
  if (!status) loadStatus().catch(() => {});
  view.innerHTML = `<section class="import">
    <p><a href="#/">← Library</a></p>
    <h1>Import your Instagram saved posts</h1>
    <p class="lead">Instagram can send you a file that lists everything you've saved. Drop it here, pick
      the posts you want, and MooDscroll turns them into notes. It never logs in to your account.</p>

    <h2>1. Ask Instagram for the file <span class="fine">(2 minutes, once)</span></h2>
    <ol class="steps">
      <li>In the Instagram app, go to your profile, tap <b>☰</b>, then <b>Meta Account</b>.</li>
      <li>Tap <b>Your information and permissions</b> → <b>Export your information</b> → <b>Create export</b>.
        <span class="fine">(Some versions say Download your information.)</span></li>
      <li>Choose your Instagram profile, then <b>Export to device</b>.</li>
      <li>On <b>Confirm your export</b>, set:
        <ul>
          <li><b>Customize information</b>: untick everything except <b>Saved</b></li>
          <li><b>Date range</b>: <b>All time</b></li>
          <li><b>Format</b>: <b>JSON</b> (HTML works too)</li>
          <li><b>Media quality</b>: any; the file only holds links</li>
        </ul></li>
      <li>Tap <b>Start export</b>.</li>
    </ol>
    <p class="fine">With only Saved ticked, the file is small and Instagram usually emails you within minutes
      (“Your Meta information download is ready”). Download it from the <b>Export your information</b> page within
      four days. Easiest on this Mac: open instagram.com in a browser, go to the same page and download it here.
      From your phone, AirDrop it to this Mac or save it to iCloud Drive.</p>

    <h2>2. Drop the ZIP here</h2>
    <div class="add" id="imp-drop">
      <p class="hint">Drop the ZIP Instagram sent you on this box, or the folder it unzipped to ·
        <label class="link">choose the ZIP<input id="imp-file" type="file" accept=".zip,.json,.html" multiple hidden></label></p>
      <p class="fine error" id="imp-msg"></p>
    </div>
    <div id="imp-list"></div>
  </section>`;

  const drop = $("#imp-drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", async (e) => {
    e.preventDefault(); drop.classList.remove("over");
    readExport(await droppedFiles(e.dataTransfer));
  });
  $("#imp-file").addEventListener("change", (e) => readExport([...e.target.files]));
  $("#imp-list").addEventListener("click", importClick);
  $("#imp-list").addEventListener("change", (e) => {
    if (e.target.dataset.code) {
      e.target.checked ? picked.add(e.target.dataset.code) : picked.delete(e.target.dataset.code);
      importFooter();
    }
    if (e.target.id === "imp-notes") importFooter();
  });
}

// A dropped folder (Safari unzips downloads) arrives as a directory entry: walk it
// and keep the two files that matter, saved_posts and saved_collections.
async function droppedFiles(dt) {
  const entries = [...dt.items].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
  if (!entries.some((en) => en.isDirectory)) return [...dt.files];
  const out = [];
  const walk = async (en) => {
    if (en.isFile) {
      if (/^saved_(posts|collections).*\.(json|html)$/i.test(en.name) || /\.zip$/i.test(en.name))
        out.push(await new Promise((ok, bad) => en.file(ok, bad)));
    } else {
      const reader = en.createReader();
      for (let batch; (batch = await new Promise((ok, bad) => reader.readEntries(ok, bad))).length;)
        for (const child of batch) await walk(child);
    }
  };
  for (const en of entries) await walk(en);
  return out;
}

async function readExport(files) {
  const msg = $("#imp-msg");
  if (!files?.length) {
    msg.classList.add("error"); msg.textContent = "No saved posts there. Drop the ZIP, or the folder it unzipped to.";
    return;
  }
  msg.classList.remove("error"); msg.textContent = `Reading ${files.length === 1 ? files[0].name : "the export"}…`;
  const body = new FormData();
  files.forEach((f) => body.append("files", f, f.name));
  try {
    found = await api("/api/import/read", { method: "POST", body });
  } catch (err) {
    msg.classList.add("error"); msg.textContent = err.message; return;
  }
  msg.textContent = "";
  picked.clear();
  newPosts().slice(0, 20).forEach((p) => picked.add(p.code));
  renderImport();
}

const newPosts = () => found.posts.filter((p) => !p.in_library);
const visiblePosts = () => newPosts().filter((p) => !shownCollection || p.collections.includes(shownCollection));

function renderImport() {
  const all = found.posts.length, fresh = newPosts().length, have = all - fresh;
  const chips = found.collections.length ? `<div class="chips imp-cols">
      <button class="chip ${shownCollection ? "" : "on"}" data-col="">All</button>
      ${found.collections.map((c) => `<button class="chip ${c.name === shownCollection ? "on" : ""}"
        data-col="${esc(c.name)}">${esc(c.name)} · ${c.count}</button>`).join("")}</div>` : "";
  const rows = visiblePosts().map((p) => `<label class="imp-row">
      <input type="checkbox" data-code="${esc(p.code)}" ${picked.has(p.code) ? "checked" : ""}>
      <span class="who">${esc(p.author ? "@" + p.author : p.code)}</span>
      <span class="what"><span class="cap">${esc(p.caption || "")}</span>
        <span class="fine">${esc([p.saved_at && `saved ${p.saved_at}`, p.collections.join(", ")].filter(Boolean).join(" · "))}</span></span>
      <a href="${esc(p.url)}" target="_blank" rel="noopener" class="fine">view ↗</a>
    </label>`).join("");
  $("#imp-list").innerHTML = `
    <h2>3. Pick what to import</h2>
    <p>Found <b>${plural(all, "saved post")}</b>${have ? `; ${have} already in your library` : ""}.
      Reels, videos, photos and carousels all come in; for pictures, the text in them is read.</p>
    ${chips}
    <p class="imp-tools fine">Select:
      <button class="link-btn" data-sel="20">newest 20</button> ·
      <button class="link-btn" data-sel="50">newest 50</button> ·
      <button class="link-btn" data-sel="all">all shown</button> ·
      <button class="link-btn" data-sel="none">none</button></p>
    <div class="imp-rows">${rows || '<p class="empty">Everything here is already in your library.</p>'}</div>
    <div class="imp-footer" id="imp-footer"></div>`;
  importFooter();
}

function importFooter() {
  const box = $("#imp-footer");
  if (!box) return;
  const n = picked.size;
  const minutes = Math.max(1, Math.round((n * 15) / 60));
  const api_ = status?.mode === "api";
  const withNotes = api_ && $("#imp-notes")?.checked;
  box.innerHTML = `
    <button data-act-imp="start" ${n ? "" : "disabled"}>Import ${plural(n, "post")}</button>
    <span class="fine">About ${minutes} min on this Mac. You can keep using it meanwhile, and stop any time.</span>
    ${api_ ? `<label class="fine imp-notes"><input type="checkbox" id="imp-notes" ${withNotes ? "checked" : ""}>
        Also write the notes now with my API key (about ${money(0.042 * n)})</label>`
      : `<p class="fine">They'll wait for notes. Then tell Claude Code or Codex: ${askBox(status?.ask_phrase || "finish my MooDscroll notes")}
        Each note uses some of your subscription, so batches of 20 to 50 work best.</p>`}`;
}

async function importClick(e) {
  const col = e.target.closest("[data-col]");
  if (col) { shownCollection = col.dataset.col || null; renderImport(); return; }
  const sel = e.target.closest("[data-sel]");
  if (sel) {
    const v = sel.dataset.sel, list = visiblePosts();
    picked.clear();
    (v === "all" ? list : v === "none" ? [] : list.slice(0, +v)).forEach((p) => picked.add(p.code));
    renderImport(); return;
  }
  const start = e.target.closest('[data-act-imp="start"]');
  if (!start) return;
  start.disabled = true; start.textContent = "Starting…";
  const posts = found.posts.filter((p) => picked.has(p.code)).map((p) => ({
    code: p.code, kind: p.url.includes("/p/") ? "p" : "reel", saved_at: p.saved_at,
    author: p.author, collections: p.collections }));
  try {
    await api("/api/import/start", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ posts, with_notes: !!$("#imp-notes")?.checked }) });
    location.hash = "#/";
  } catch (err) {
    alert(err.message); start.disabled = false; importFooter();
  }
}

route();
