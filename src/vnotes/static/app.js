// vnotes web app: no framework, two views (home and note), routed by the URL hash.

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
function route() {
  clearTimeout(pollTimer);
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
  document.title = "vnotes";
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
}

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
      <span class="pill ${j.status}">${j.status}</span>
      <span class="label">${esc(j.label)}</span>
      <span class="step">${esc(j.step || j.error || (j.notes_error ? "saved without AI notes: " + j.notes_error : ""))}</span>
      ${j.folder ? `<a href="#/note/${encodeURIComponent(j.folder)}">Open note →</a>` : ""}
    </div>`).join("");

  const newlyDone = jobs.filter((j) => j.status === "done" && !seenDone.has(j.id));
  newlyDone.forEach((j) => seenDone.add(j.id));
  if (newlyDone.length) loadLibrary();
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
        <div class="title">${esc(i.title || i.folder)}</div>
        <div class="sub">${esc([i.author, i.category].filter(Boolean).join(" · "))}</div>
      </div>
    </a>`).join("")
    : `<p class="empty">${q ? "Nothing matches." : "Nothing here yet — paste a link above."}</p>`;
}

// --- Note: video beside the notes, every timestamp clickable ------------------------

async function showNote(folder) {
  let d;
  try {
    d = await api(`/api/notes/${encodeURIComponent(folder)}`);
  } catch {
    view.innerHTML = `<p class="empty">Note not found. <a href="#/">Back</a></p>`;
    return;
  }
  const n = d.notes, m = d.meta;
  const frameUrl = (f) => `/media/${encodeURIComponent(d.folder)}/frames/${f.file}`;
  const title = n?.title || m.title || d.folder;
  document.title = `${title} · vnotes`;

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
            : `<p class="warn">No AI notes for this video${m.notes_error ? ": " + esc(m.notes_error) : ""}.</p>`}
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
  window.scrollTo(0, 0);
}

route();
