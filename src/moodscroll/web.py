"""moodscroll in the browser: drop a video or paste a link, watch it being processed,
read the note next to the video, search everything saved.

    uv run moodscroll-web        # then open http://127.0.0.1:8765

Same engine as the command line and the same library as the MCP server. With an
API key it writes notes itself; without one, videos wait in the library until
Claude Code or Codex writes their notes. Listens on this Mac only.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import tempfile
import threading
import time
import uuid
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import KEY_FILE, library, notes, pipeline, sources
from .media import ocr_lines, paragraphs

STATIC = Path(__file__).parent / "static"
VIDEO_TYPES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}

app = FastAPI(title="MOODscroll")

ALLOWED_HOSTS = {"127.0.0.1:8765", "localhost:8765"}


@app.middleware("http")
async def only_this_app(request, call_next):
    # The server only listens on this Mac, but any web page open in the browser can
    # still send requests to 127.0.0.1. Refuse requests from other sites (Origin)
    # and from look-alike domains pointed at this Mac (Host, "DNS rebinding").
    origin = request.headers.get("origin")
    if request.headers.get("host") not in ALLOWED_HOSTS or (
            origin and origin.removeprefix("http://") not in ALLOWED_HOSTS):
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    response = await call_next(request)
    if not request.url.path.startswith("/media/"):
        # After an update, the browser must fetch the new app.js, not a cached one.
        response.headers["Cache-Control"] = "no-cache"
    return response


# --- Jobs ---------------------------------------------------------------------------
# One worker thread processes videos one at a time: transcription already uses the
# whole GPU, so running two at once would only make both slower.

jobs: dict[str, dict] = {}
_lock = threading.Lock()
_queue: queue.Queue[str] = queue.Queue()


def _update(job_id: str, **fields) -> None:
    with _lock:
        jobs[job_id].update(fields)


def _worker() -> None:
    while True:
        job_id = _queue.get()
        job = jobs[job_id]
        _update(job_id, status="running", started=time.time())
        try:
            folder = pipeline.run(job["input"], library.DEFAULT_ROOT, keep_video=True,
                                  progress=lambda m: _update(job_id, step=m.strip()))
            upload = job.get("upload")
            if upload:  # an uploaded file lives in a temp folder; keep it with its note
                shutil.move(upload, folder / f"video{Path(upload).suffix.lower()}")
                shutil.rmtree(Path(upload).parent, ignore_errors=True)
                meta_file = folder / "meta.json"  # record the file's name, not the temp path
                meta = json.loads(meta_file.read_text())
                meta["source"] = job["label"]
                meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
            d = pipeline.load(folder)
            _update(job_id, status="done", folder=folder.name, step=None,
                    waiting=d["notes"] is None, notes_error=d["meta"].get("notes_error"))
        except Exception as e:  # shown to the user in the job list
            _update(job_id, status="failed", error=str(e), step=None)
        finally:
            _update(job_id, finished=time.time())


threading.Thread(target=_worker, daemon=True).start()


def _enqueue(label: str, input_: str, upload: str | None = None) -> dict:
    job_id = uuid.uuid4().hex[:8]
    with _lock:
        jobs[job_id] = {"id": job_id, "label": label, "input": input_, "upload": upload,
                        "status": "queued", "step": None, "created": time.time()}
    _queue.put(job_id)
    return _public(jobs[job_id])


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in ("input", "upload")}


@app.post("/api/jobs")
async def create_job(url: str | None = Form(None), file: UploadFile | None = File(None)):
    if url:
        url = url.strip()
        if not sources.is_url(url):
            raise HTTPException(400, "that doesn't look like a link")
        return _enqueue(url, url)
    if file and file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in VIDEO_TYPES:
            raise HTTPException(400, f"not a video file ({suffix or 'no extension'})")
        tmpdir = Path(tempfile.mkdtemp(prefix="moodscroll-upload-"))
        path = tmpdir / f"{Path(file.filename).stem}{suffix}"
        with open(path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return _enqueue(file.filename, str(path), upload=str(path))
    raise HTTPException(400, "send a link or a video file")


@app.get("/api/jobs")
def list_jobs():
    with _lock:
        return sorted((_public(j) for j in jobs.values()), key=lambda j: -j["created"])


@app.get("/api/status")
def status():
    load_dotenv(KEY_FILE)  # moodscroll-setup may have added a key while the app runs
    return {"has_key": notes.has_key(), "ask_phrase": notes.ASK_PHRASE,
            "waiting": len(library.waiting())}


# --- Library ------------------------------------------------------------------------

def _folder(name: str) -> Path:
    try:
        return library.resolve_folder(name)
    except ValueError:
        raise HTTPException(404, "no such note")


@app.get("/api/library")
def list_library(q: str = "", limit: int = 200):
    if q.strip():
        return library.search(q, limit=limit)
    return [library.summary(f) for f in library.folders()[:limit]]


@app.get("/api/notes/{name}")
def get_note(name: str):
    folder = _folder(name)
    d = pipeline.load(folder)
    video = next((p.name for p in folder.glob("video.*")), None)
    return {
        "folder": folder.name,
        "meta": d["meta"],
        "transcript": d["transcript"],
        "paragraphs": paragraphs(d["transcript"]["segments"]),
        "ocr": [{"t": o["t"], "lines": ocr_lines(o)} for o in d["ocr"]],
        "frames": d["frames"],
        "notes": d["notes"].model_dump() if d["notes"] else None,
        "video": f"/media/{folder.name}/{video}" if video else None,
        "markdown": (folder / "note.md").read_text(),
    }


@app.get("/media/{name}/{path:path}")
def media(name: str, path: str):
    folder = _folder(name)
    file = (folder / path).resolve()
    if folder not in file.parents or not file.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(file)


@app.post("/api/quit")
def quit_app():
    # The app keeps running in the background after its window is closed; this is
    # the off switch (the footer's "Quit" link). Exit just after replying.
    threading.Timer(0.3, lambda: os._exit(0)).start()
    return {"ok": True}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")

HOST, PORT = "127.0.0.1", 8765  # this Mac only; nothing else on the network can reach it


def main() -> None:
    import argparse

    import uvicorn

    p = argparse.ArgumentParser(prog="moodscroll-web", description="Run the MOODscroll web app.")
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = p.parse_args()
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
