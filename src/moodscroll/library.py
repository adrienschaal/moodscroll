"""Find things across every video already processed. Plain files, no database yet:
fast enough for a few thousand notes."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .pipeline import load

DEFAULT_ROOT = Path(os.environ.get("MOODSCROLL_DIR", "~/Moodscroll")).expanduser()


def folders(root: Path | None = None) -> list[Path]:
    root = root or DEFAULT_ROOT
    if not root.is_dir():
        return []
    # Newest first: by the date in the name, then by when the folder was created
    # (it keeps that time when renamed after its title).
    return sorted((p for p in root.iterdir() if (p / "meta.json").exists()),
                  key=lambda p: (p.name[:10], getattr(p.stat(), "st_birthtime", p.stat().st_mtime)), reverse=True)


def resolve_folder(name: str, root: Path | None = None) -> Path:
    """Turns a folder name from search results into a path, refusing anything that
    would point outside the library (a tool argument is untrusted input). A folder is
    renamed once its notes are written; its old name still finds it."""
    root = root or DEFAULT_ROOT
    path = (root / name).resolve()
    if path.parent != root.resolve():
        raise ValueError(f"no video folder named {name!r} in {root}")
    if (path / "meta.json").exists():
        return path
    for folder in folders(root):
        if name in load(folder)["meta"].get("previous_names", []):
            return folder
    raise ValueError(f"no video folder named {name!r} in {root}")


def instagram_codes(root: Path | None = None) -> set[str]:
    """Shortcodes of the Instagram posts already in the library, so an import skips them."""
    from .sources import instagram_code

    codes = set()
    for f in folders(root):
        meta = load(f)["meta"]
        if code := instagram_code(meta.get("source") or ""):
            codes.add(code)
    return codes


def waiting(root: Path | None = None) -> list[dict]:
    """Videos that were processed but have no notes yet, oldest first, each with
    what writing its notes through the API should cost."""
    from .notes import estimate_cost

    out = []
    for f in reversed(folders(root)):
        if (f / "notes.json").exists():
            continue
        d = load(f)
        out.append(summary(f) | {"est_cost": estimate_cost(d["meta"], d["transcript"], d["ocr"])})
    return out


def summary(folder: Path) -> dict:
    d = load(folder)
    n, m = d["notes"], d["meta"]
    return {
        "folder": folder.name,
        "title": n.title if n else m.get("title"),
        "author": m.get("author"),
        "category": n.category if n else None,
        "tags": n.tags if n else [],
        "summary": n.summary if n else None,
        "source": m.get("source"),
        "duration_s": m.get("duration_s"),
        "kind": kind(m),
        "slides": m.get("slides"),
        "thumb": d["frames"][0]["file"] if d["frames"] else None,
        "has_notes": n is not None,
        "notes_error": m.get("notes_error"),
    }


def kind(meta: dict) -> str:
    """reel, video, photo or carousel. Notes made before photo posts were supported
    don't say; an Instagram /reel/ link is a reel, anything else a video."""
    if meta.get("kind"):
        return meta["kind"]
    return "reel" if "instagram.com" in (meta.get("source") or "") else "video"


def search(query: str, root: Path | None = None, limit: int = 10) -> list[dict]:
    """Ranks videos by how many query words they contain, weighting the title,
    tags and summary above the caption and transcript."""
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
    hits = []
    for folder in folders(root):
        d = load(folder)
        n, m = d["notes"], d["meta"]
        strong = " ".join([n.title, " ".join(n.tags), n.summary, " ".join(n.key_points),
                           " ".join(f"{x.label} {x.value}" for x in n.details)] if n else [m.get("title") or ""]).lower()
        weak = " ".join([m.get("caption") or "", m.get("author") or ""]
                        + [s["text"] for s in d["transcript"]["segments"]]
                        + [o["text"] for o in d["ocr"]] + (m.get("alt_text") or [])).lower()
        score = sum(3 * strong.count(w) + weak.count(w) for w in words) if words else 1
        if score:
            hits.append((score, folder))
    hits.sort(key=lambda h: (-h[0], h[1].name))
    return [summary(f) | {"score": s} for s, f in hits[:limit]]
