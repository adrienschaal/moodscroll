"""Runs the steps in order and writes everything into one folder per video:

    <out>/<date>-<slug>/
        note.md          the readable result
        notes.json       the structured notes (once written)
        meta.json        source, author, caption, duration, timings
        transcript.json  timestamped speech
        ocr.json         timestamped on-screen text
        frames.json      which frame was taken when
        frames/          key frames (one per scene change)

Two steps, so the notes can come from either place:
  extract()    everything local: fetch, transcribe, frames, OCR
  add_notes()  attach notes, from the Claude API (CLI, web app) or from Claude
               itself through the MCP server (your Claude subscription)
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
import unicodedata
from datetime import date
from pathlib import Path
from typing import Callable

from . import media, notes, render, sources
from .notes import Notes


def slugify(text: str, max_len: int = 50) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-") or "video"


def _unique_dir(root: Path, name: str) -> Path:
    path, n = root / name, 2
    while path.exists():
        path, n = root / f"{name}-{n}", n + 1
    return path


def extract(src: str, out_root: Path, *, keep_video: bool = False,
            progress: Callable[[str], None] = print) -> Path:
    sources.require_ffmpeg()
    out_root.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    def step(name: str, fn, *args):
        progress(f"{name}...")
        t0 = time.monotonic()
        result = fn(*args)
        timings[name] = round(time.monotonic() - t0, 1)
        return result

    with tempfile.TemporaryDirectory(prefix="vnotes-") as tmp:
        work = Path(tmp)
        source = step("fetching", sources.resolve, src, work)
        source.meta["duration_s"] = source.meta.get("duration_s") or media.duration(source.video)
        transcript = step("transcribing", media.transcribe, source.video)
        frames = step("finding key frames", media.keyframes, source.video, work / "frames")
        screen_text = step("reading on-screen text", media.ocr, work / "frames", frames)

        out = _unique_dir(out_root, f"{date.today().isoformat()}-{slugify(source.meta.get('title') or 'video')}")
        out.mkdir()
        shutil.move(str(work / "frames"), out / "frames")
        if keep_video and source.downloaded:  # never touch a file the user gave us
            shutil.move(str(source.video), out / source.video.name)

    _write_json(out / "meta.json", {**source.meta, "timings_s": timings})
    _write_json(out / "transcript.json", transcript)
    _write_json(out / "ocr.json", screen_text)
    _write_json(out / "frames.json", frames)
    _render(out)
    return out


def load(folder: Path) -> dict:
    """Reads back everything extract() and add_notes() wrote."""
    def read(name, default=None):
        path = folder / name
        return json.loads(path.read_text()) if path.exists() else default

    raw = read("notes.json")
    return {
        "meta": read("meta.json", {}),
        "transcript": read("transcript.json", {"language": None, "segments": []}),
        "ocr": read("ocr.json", []),
        "frames": read("frames.json", []),
        "notes": Notes.model_validate(raw) if raw else None,
    }


def add_notes(folder: Path, result: Notes, usage: dict | None = None) -> Path:
    """Saves the notes, re-renders note.md, and renames the folder after the notes'
    title (creators' own titles are often 'Video by someone'). Returns the folder."""
    _write_json(folder / "notes.json", result.model_dump())
    meta = load(folder)["meta"]
    meta.update(claude=usage, notes_error=None)
    _write_json(folder / "meta.json", meta)

    date_prefix = folder.name[:10]
    wanted = f"{date_prefix}-{slugify(result.title)}"
    if not folder.name.startswith(wanted):
        target = _unique_dir(folder.parent, wanted)
        folder.rename(target)
        folder = target
    _render(folder)
    return folder


def run(src: str, out_root: Path, *, with_notes: bool = True, keep_video: bool = False,
        progress: Callable[[str], None] = print) -> Path:
    """The whole thing in one go, with notes from the Claude API."""
    folder = extract(src, out_root, keep_video=keep_video, progress=progress)
    if not with_notes:
        return folder
    data = load(folder)
    progress("writing notes with Claude...")
    t0 = time.monotonic()
    try:
        result, usage = notes.make_notes(data["meta"], data["transcript"], data["ocr"],
                                         folder / "frames", data["frames"])
    except notes.NotesUnavailable as e:
        progress(f"  skipped notes: {e}")
        meta = {**data["meta"], "notes_error": str(e)}
        _write_json(folder / "meta.json", meta)
        _render(folder)
        return folder
    usage["seconds"] = round(time.monotonic() - t0, 1)
    progress(f"  {usage['input_tokens']:,} tokens in, {usage['output_tokens']:,} out, {usage['seconds']} s")
    return add_notes(folder, result, usage)


def _render(folder: Path) -> None:
    d = load(folder)
    (folder / "note.md").write_text(render.markdown(d["meta"], d["transcript"], d["ocr"], d["frames"], d["notes"]))


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
