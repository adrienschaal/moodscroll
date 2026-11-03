"""vnotes in the browser: drop a video or paste a link, watch it being processed,
read the note next to the video, search everything saved.

    uv run vnotes-web        # then open http://127.0.0.1:8765

Same engine as the command line (pipeline.run, notes through the Claude API) and
the same library as the MCP server. Listens on this Mac only.
"""

from __future__ import annotations

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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import library, pipeline, sources

load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.home() / ".config" / "vnotes" / ".env")

STATIC = Path(__file__).parent / "static"
VIDEO_TYPES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}

app = FastAPI(title="vnotes")


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
            notes_error = pipeline.load(folder)["meta"].get("notes_error")
            _update(job_id, status="done", folder=folder.name, step=None, notes_error=notes_error)
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
        tmpdir = Path(tempfile.mkdtemp(prefix="vnotes-upload-"))
        path = tmpdir / f"{Path(file.filename).stem}{suffix}"
        with open(path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return _enqueue(file.filename, str(path), upload=str(path))
    raise HTTPException(400, "send a link or a video file")


@app.get("/api/jobs")
def list_jobs():
    with _lock:
        return sorted((_public(j) for j in jobs.values()), key=lambda j: -j["created"])


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
        "ocr": d["ocr"],
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


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


def main() -> None:
    import uvicorn

    host, port = "127.0.0.1", 8765  # this Mac only; nothing else on the network can reach it
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
