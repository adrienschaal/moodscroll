// moodscroll web app: no framework, two views (home and note), routed by the URL hash.

const $ = (sel, el = document) => el.querySelector(sel);
const view = $("#view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const ts = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

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
  const m = location.hash.match(/^#\/note\/(.+)$/);
  if (m) showNote(decodeURIComponent(m[1]));
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
  document.title = "MOODscroll";
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
    if (status?.waiting && !document.hidden) { loadStatus(); loadLibrary(); }
  }, 4000);
}

// Without an API key, Claude Code or Codex writes the notes. Say so, with the
// exact words to use, so a video "waiting for notes" never looks broken.
let status = null;
const askBox = (phrase) =>
  `<code>${esc(phrase)}</code> <button class="ghost small" data-copy="${esc(phrase)}">Copy</button>`;

async function loadStatus() {
  status = await api("/api/status");
  const box = $("#banner");
  if (!box) return;
  const waiting = status.waiting
    ? `<span class="count">${status.waiting} video${status.waiting > 1 ? "s" : ""} waiting for notes.</span> ` : "";
  if (!status.has_key) {
    box.innerHTML = `<div class="banner">
      <p><b>Your notes are written by Claude Code or Codex.</b> ${waiting}Add videos here
      whenever you like, then tell Claude Code or Codex: ${askBox(status.ask_phrase)}</p>
      <p class="fine">They appear here as soon as they're written. Prefer this app to write them by
      itself? Run the installer again and add a Claude API key (about $0.04 a video).</p></div>`;
  } else {
    box.innerHTML = status.waiting
      ? `<div class="banner"><p>${waiting}Tell Claude Code or Codex: ${askBox(status.ask_phrase)}</p></div>` : "";
  }
}

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
  box.innerHTML = jobs.map((j) => `
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
    <a class="card" href="#/note/${encodeURIComponent(i.folder)}">
      <div class="thumb" style="background-image:url('${i.thumb ? `/media/${encodeURIComponent(i.folder)}/frames/${i.thumb}` : ""}')"></div>
      <div class="body">
        ${i.has_notes ? "" : '<span class="badge">Waiting for notes</span>'}
        <div class="title">${esc(i.title || i.folder)}</div>
        <div class="sub">${esc([i.author, i.category].filter(Boolean).join(" · "))}</div>
      </div>
    </a>`).join("")
    : `<p class="empty">${q ? "Nothing matches." : "Nothing here yet — paste a link above."}</p>`;
}

// --- Note: video beside the notes, every timestamp clickable ------------------------

async function showNote(folder) {
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
  const here = `#/note/${encodeURIComponent(d.folder)}`;
  if (location.hash !== here) history.replaceState(null, "", here);
  const n = d.notes, m = d.meta;
  const frameUrl = (f) => `/media/${encodeURIComponent(d.folder)}/frames/${f.file}`;
  const title = n?.title || m.title || d.folder;
  document.title = `${title} · MOODscroll`;

  const list = (items, tag = "ul", cls = "") =>
    items?.length ? `<${tag} class="${cls}">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</${tag}>` : "";
  const section = (name, html) => (html ? `<h3>${name}</h3>${html}` : "");

  view.innerHTML = `
    <p><a href="#/">← Library</a></p>
    <div class="note">
      <aside class="side">
        ${d.video
          ? `<video id="player" src="${d.video}" controls playsinline preload="metadata"></video>`
          : d.frames[0] ? `<img class="poster" src="${frameUrl(d.frames[0])}" alt="">` : ""}
        <div class="frames">${d.frames.map((f) =>
          `<button data-t="${f.t}" title="Jump to ${ts(f.t)}"><img src="${frameUrl(f)}" alt="" loading="lazy"><span>${ts(f.t)}</span></button>`).join("")}</div>
      </aside>
      <article>
        <h1>${esc(title)}</h1>
        <div class="meta">${esc([m.author, m.site, m.duration_s && ts(m.duration_s)].filter(Boolean).join(" · "))}
          ${m.source?.startsWith("http") ? ` · <a href="${esc(m.source)}" target="_blank" rel="noopener">original</a>` : ""}</div>
        ${n ? `<p class="summary">${esc(n.summary)}</p>`
            : `<div class="banner"><p><b>Waiting for notes.</b>${m.notes_error ? ` (Notes failed: ${esc(m.notes_error)}.)` : ""}
                Tell Claude Code or Codex: ${askBox(status?.ask_phrase || "finish my MOODscroll notes")}</p>
                <p class="fine">This page updates by itself when they're written.</p></div>`}
        ${n ? section("Key points", list(n.key_points))
            + section("Details", n.details.length ? `<dl class="details">${n.details.map((x) =>
                `<dt>${esc(x.label)}</dt><dd>${esc(x.value)}</dd>`).join("")}</dl>` : "")
            + section("Steps", list(n.steps, "ol"))
            + section("Claims to verify", list(n.claims_to_verify, "ul", "claims")) : ""}
        <div class="actions">
          <button class="ghost" id="copy">Copy Markdown</button>
        </div>
        ${section("Transcript", d.transcript.segments.length
          ? d.transcript.segments.map((s) =>
              `<div class="line" data-start="${s.start}" data-end="${s.end}"><button class="ts" data-t="${s.start}">${ts(s.start)}</button>${esc(s.text)}</div>`).join("")
          : `<p class="caption">(no speech)</p>`)}
        ${section("On-screen text", d.ocr.map((o) =>
          `<div class="line"><button class="ts" data-t="${o.t}">${ts(o.t)}</button>${esc(o.text)}</div>`).join(""))}
        ${m.caption ? `<h3>Caption</h3><details><summary>Show the original caption</summary><p class="caption">${esc(m.caption)}</p></details>` : ""}
      </article>
    </div>`;

  // Any element with data-t seeks the video there.
  const player = $("#player");
  // onclick (not addEventListener) so opening another note replaces the handler.
  view.onclick = (e) => {
    const t = e.target.closest("[data-t]")?.dataset.t;
    if (t === undefined || !player) return;
    player.currentTime = Number(t);
    player.play();
  };
  // Highlight the transcript line being spoken.
  if (player) {
    const lines = [...view.querySelectorAll(".line[data-start]")];
    player.addEventListener("timeupdate", () => {
      const now = player.currentTime;
      lines.forEach((l) => l.classList.toggle("now", now >= l.dataset.start && now < l.dataset.end));
    });
  }
  $("#copy").addEventListener("click", async () => {
    await navigator.clipboard.writeText(d.markdown);
    $("#copy").textContent = "Copied";
  });
  if (!n) {  // waiting: show the notes the moment Claude Code or Codex saves them
    liveTimer = setInterval(async () => {
      if (document.hidden) return;
      const fresh = await api(`/api/notes/${encodeURIComponent(d.folder)}`).catch(() => null);
      if (fresh?.notes) { clearInterval(liveTimer); showNote(fresh.folder); }
    }, 4000);
  }
  window.scrollTo(0, 0);
}

$("#quit").addEventListener("click", async (e) => {
  e.preventDefault();
  if (!confirm("Quit MOODscroll? Videos still processing will stop.")) return;
  await fetch("/api/quit", { method: "POST" }).catch(() => {});
  document.body.innerHTML = '<main><p class="empty">MOODscroll has quit. Open it again from Applications or Spotlight.</p></main>';
});

route();
