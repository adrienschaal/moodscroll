"""Runs the steps in order and writes everything into one folder per video:

    <out>/<date>-<slug>/
        note.md          the readable result
        notes.json       Claude's structured notes
        meta.json        source, author, caption, duration, timings
        transcript.json  timestamped speech
        ocr.json         timestamped on-screen text
        frames/          key frames (one per scene change)
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


def slugify(text: str, max_len: int = 50) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-") or "video"


def _unique_dir(root: Path, name: str) -> Path:
    path, n = root / name, 2
    while path.exists():
        path, n = root / f"{name}-{n}", n + 1
    return path


def run(src: str, out_root: Path, *, with_notes: bool = True, keep_video: bool = False,
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

        result, usage, error = None, None, None
        if with_notes:
            try:
                result, usage = step("writing notes with Claude", notes.make_notes,
                                     source.meta, transcript, screen_text, work / "frames", frames)
            except notes.NotesUnavailable as e:
                error = str(e)
                progress(f"  skipped notes: {error}")

        title = (result.title if result else None) or source.meta.get("title") or "video"
        out = _unique_dir(out_root, f"{date.today().isoformat()}-{slugify(title)}")
        out.mkdir()
        shutil.move(str(work / "frames"), out / "frames")
        if keep_video and source.downloaded:  # never touch a file the user gave us
            shutil.move(str(source.video), out / source.video.name)

        meta = {**source.meta, "timings_s": timings, "claude": usage, "notes_error": error}
        _write_json(out / "meta.json", meta)
        _write_json(out / "transcript.json", transcript)
        _write_json(out / "ocr.json", screen_text)
        if result:
            _write_json(out / "notes.json", result.model_dump())
        (out / "note.md").write_text(render.markdown(meta, transcript, screen_text, frames, result))
    return out


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
