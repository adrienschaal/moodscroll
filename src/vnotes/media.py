"""Everything that happens on this Mac, without the network: speech to text with
Whisper on Apple Silicon, key frames with ffmpeg, on-screen text with Apple Vision."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

WHISPER_MODEL = os.environ.get("VNOTES_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
SWIFT_DIR = Path(__file__).parent / "swift"
CACHE = Path.home() / ".cache" / "vnotes"


# --- Speech to text ----------------------------------------------------------------

def has_audio(video: Path) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    return bool(r.stdout.strip())


def transcribe(video: Path) -> dict:
    """Returns {"language": "en", "segments": [{"start", "end", "text"}, ...]}."""
    if not has_audio(video):
        return {"language": None, "segments": []}
    import mlx_whisper

    # Not feeding each segment's text into the next one stops most of Whisper's
    # loops over background music.
    r = mlx_whisper.transcribe(str(video), path_or_hf_repo=WHISPER_MODEL,
                               condition_on_previous_text=False)
    return {"language": r.get("language"),
            "segments": clean_segments(r["segments"], duration(video))}


def duration(video: Path) -> float | None:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        return round(float(r.stdout.strip()), 1)
    except ValueError:
        return None


def clean_segments(segments: list[dict], video_duration: float | None = None) -> list[dict]:
    """Drops text Whisper made up over music or silence. Three tells, measured on
    real reels: the line repeats (high compression ratio), the model was unsure of
    every word (real speech scores about -0.1 average log-probability, invented
    lines about -5), or the segment starts after the video has ended."""
    out = []
    for s in segments:
        text = s["text"].strip()
        if (not text
                or s.get("compression_ratio", 0) >= 2.4
                or s.get("avg_logprob", 0) < -1.0
                or (video_duration and s["start"] >= video_duration)):
            continue
        out.append({"start": round(s["start"], 1), "end": round(s["end"], 1), "text": text})
    return out


# --- Key frames --------------------------------------------------------------------

def keyframes(video: Path, outdir: Path, threshold: float = 0.3, every: float = 8.0,
              max_frames: int = 40) -> list[dict]:
    """Saves one frame per scene change (plus the first frame) as JPEGs.

    Returns [{"file": "0001.jpg", "t": 3.2}, ...]. Sampling on scene changes rather
    than every N seconds gives fewer near-duplicate frames and better OCR.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    # A frame is kept if it is the first one, if the picture changed a lot, or if
    # `every` seconds passed without a change (a single-shot talking head would
    # otherwise give one frame for the whole video).
    vf = (f"select='eq(n\\,0)+gt(scene\\,{threshold})"
          f"+gte(t-prev_selected_t\\,{every})',showinfo,scale=720:-2")
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(video), "-vf", vf,
         "-fps_mode", "vfr", "-q:v", "3", str(outdir / "%04d.jpg")],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-500:]}")
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    files = sorted(outdir.glob("*.jpg"))
    frames = [{"file": f.name, "t": round(t, 1)} for f, t in zip(files, times)]

    keep = subsample(frames, max_frames)
    for f in frames:
        if f not in keep:
            (outdir / f["file"]).unlink()
    return keep


def subsample(items: list, n: int) -> list:
    """Keeps n items spread evenly, always including the first and the last."""
    if len(items) <= n:
        return items
    if n == 1:
        return items[:1]
    step = (len(items) - 1) / (n - 1)
    return [items[round(i * step)] for i in range(n)]


# --- On-screen text ----------------------------------------------------------------

def _swift_binary(name: str) -> Path:
    # Compile once and cache; running the .swift file as a script costs seconds.
    src = SWIFT_DIR / f"{name}.swift"
    exe = CACHE / name
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        CACHE.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", "-O", "-suppress-warnings", str(src), "-o", str(exe)], check=True)
    return exe


def ocr(frames_dir: Path, frames: list[dict]) -> list[dict]:
    """Returns [{"t": 3.2, "text": "..."}] with lines already seen on earlier
    frames removed (burned-in subtitles repeat across many frames)."""
    if not frames:
        return []
    r = subprocess.run([str(_swift_binary("ocr")), str(frames_dir)],
                       capture_output=True, text=True, check=True)
    by_file = {}
    for line in r.stdout.splitlines():
        rec = json.loads(line)
        by_file[rec["file"]] = rec["lines"]
    return dedupe_ocr([(f["t"], by_file.get(f["file"], [])) for f in frames])


def dedupe_ocr(frames: list[tuple[float, list[str]]]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for t, lines in frames:
        new = []
        for line in lines:
            key = " ".join(line.lower().split())
            if len(key) < 2 or key in seen:
                continue
            seen.add(key)
            new.append(line.strip())
        if new:
            out.append({"t": t, "text": " | ".join(new)})
    return out
