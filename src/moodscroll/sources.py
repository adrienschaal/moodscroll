"""Turn whatever the user gave us (a file path or a link) into a local video file
plus whatever metadata the source knows about it (title, author, caption...)."""

from __future__ import annotations

import json
import re
import shutil
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Source:
    video: Path | None  # None for a photo post
    meta: dict = field(default_factory=dict)
    downloaded: bool = False  # True if we fetched it, so we may delete it afterwards
    images: list[Path] = field(default_factory=list)  # a photo post: one per slide, in order


IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".heic", ".webp")


class SourceError(Exception):
    pass


def is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def resolve(src: str, workdir: Path) -> Source:
    if not is_url(src):
        path = Path(src).expanduser().resolve()
        if not path.is_file():
            raise SourceError(f"no such file: {path}")
        if path.suffix.lower() in IMAGE_SUFFIXES:  # a screenshot or a saved picture
            return Source(video=None, images=[path], meta={"title": path.stem, "source": str(path), "kind": "photo"})
        return Source(video=path, meta={"title": path.stem, "source": str(path), "kind": "video"})

    try:
        return _download_ytdlp(src, workdir)
    except SourceError as first:
        # yt-dlp is the general path. For Instagram, the public embed page is a
        # second chance when yt-dlp's extractor is broken or rate-limited, and the
        # way in for photo posts and carousels, which yt-dlp doesn't download.
        if "instagram.com" in src:
            try:
                return _download_instagram_embed(src, workdir)
            except SourceError as second:
                raise SourceError(f"{first}\nInstagram fallback also failed: {second}")
        raise


# --- yt-dlp: YouTube, TikTok, Instagram, Vimeo, X and ~1,800 other sites ----------

def _download_ytdlp(url: str, workdir: Path) -> Source:
    import yt_dlp

    opts = {
        "outtmpl": str(workdir / "video.%(ext)s"),
        # Whisper and the frame grabber don't need more than 720p.
        "format": "bv*[height<=720]+ba/b[height<=720]/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:  # yt-dlp raises many types; all mean "couldn't get it"
        raise SourceError(f"download failed: {e}") from e

    files = [p for p in workdir.glob("video.*") if p.suffix != ".part"]
    if not files:
        raise SourceError("download finished but no video file was written")
    return Source(
        video=files[0],
        downloaded=True,
        meta={
            "title": info.get("title"),
            "author": info.get("uploader") or info.get("channel"),
            "caption": info.get("description"),
            "duration_s": info.get("duration"),
            "upload_date": info.get("upload_date"),
            "site": info.get("extractor_key"),
            "source": info.get("webpage_url") or url,
            "kind": "reel" if "instagram.com" in url else "video",
        },
    )


# --- Instagram public embed page (no login, no third-party code) ------------------

_UA = "curl/8"  # a browser user agent gets a JavaScript shell without the video URL


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _unescape(s: str) -> str:
    # The embed page nests JSON inside JSON, so strings are escaped several times.
    for _ in range(4):
        if "\\" not in s:
            break
        try:
            s = json.loads('"' + s + '"')
        except ValueError:
            break
    return s


def _field(html: str, pattern: str) -> str | None:
    m = re.search(pattern, html)
    return _unescape(m.group(1)) if m else None


def instagram_code(url: str) -> str | None:
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:reels?|p|tv)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def embed_post(html: str) -> dict | None:
    """The post as the embed page describes it: {"__typename": "GraphImage" |
    "GraphSidecar" | "GraphVideo", "display_url", "edge_sidecar_to_children", ...},
    or None if the page doesn't carry it."""
    i = html.find('"contextJSON":')
    if i < 0:
        return None
    try:
        raw, _ = json.JSONDecoder().raw_decode(html[i + len('"contextJSON":'):])
        return json.loads(raw)["gql_data"]["shortcode_media"]
    except (ValueError, KeyError, TypeError):
        return None


def _photo_post(post: dict, code: str, workdir: Path) -> Source:
    """A photo, or a carousel of photos: every slide downloaded in order. A video
    slide in a carousel is kept as its cover image."""
    slides = [e["node"] for e in (post.get("edge_sidecar_to_children") or {}).get("edges", [])] or [post]
    folder = workdir / "images"
    folder.mkdir()
    images, alt = [], []
    for n, slide in enumerate(slides, 1):
        if not slide.get("display_url"):
            continue
        path = folder / f"{n:04d}.jpg"
        path.write_bytes(_get(slide["display_url"]))
        images.append(path)
        alt.append(slide.get("accessibility_caption") or "")
    if not images:
        raise SourceError("no video or pictures in the embed page (private, removed or embedding disabled)")
    caption = ((post.get("edge_media_to_caption") or {}).get("edges") or [{}])[0].get("node", {}).get("text")
    return Source(
        video=None, images=images, downloaded=True,
        meta={
            "title": None,
            "author": (post.get("owner") or {}).get("username"),
            "caption": caption,
            "duration_s": None,
            "site": "Instagram",
            "source": f"https://www.instagram.com/p/{code}/",
            "kind": "carousel" if len(images) > 1 else "photo",
            "slides": len(images),
            # Instagram's own description of each picture, when it wrote one.
            "alt_text": [a for a in alt if a and not a.startswith("Photo by")] or None,
        },
    )


def _download_instagram_embed(url: str, workdir: Path) -> Source:
    code = instagram_code(url)
    if not code:
        raise SourceError(f"not an Instagram post or reel URL: {url}")
    try:
        html = _get(f"https://www.instagram.com/reel/{code}/embed/captioned/").decode("utf-8", "replace")
    except OSError as e:
        raise SourceError(f"embed page unreachable: {e}") from e

    video_url = _field(html, r'video_url\\+":\\+"(.*?)\\+"')
    if not video_url:
        post = embed_post(html)
        if post and post.get("__typename") in ("GraphImage", "GraphSidecar"):
            try:
                return _photo_post(post, code, workdir)
            except OSError as e:
                raise SourceError(f"couldn't download the pictures: {e}") from e
        raise SourceError("no video in the embed page (private, removed or embedding disabled)")
    video = workdir / "video.mp4"
    with open(video, "wb") as f:
        f.write(_get(video_url))
    duration = _field(html, r'video_duration\\+":([\d.]+)')
    return Source(
        video=video,
        downloaded=True,
        meta={
            "title": None,
            "author": _field(html, r'\\+"owner\\+":\{\\+"id\\+":\\+"\d+\\+",\\+"username\\+":\\+"(.*?)\\+"')
                      or _field(html, r'class="CaptionUsername"[^>]*>([^<]+)<'),
            "caption": _field(html, r'edge_media_to_caption\\+":\{\\+"edges\\+":\[\{\\+"node\\+":\{\\+"text\\+":\\+"(.*?)\\+"\}'),
            "duration_s": float(duration) if duration else None,
            "site": "Instagram",
            "source": f"https://www.instagram.com/reel/{code}/",
            "kind": "reel",
        },
    )


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise SourceError("ffmpeg is required: brew install ffmpeg")
