"""Find things across every video already processed. Plain files, no database yet:
fast enough for a few thousand notes."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .pipeline import load

DEFAULT_ROOT = Path(os.environ.get("VNOTES_DIR", "~/vnotes")).expanduser()


def folders(root: Path | None = None) -> list[Path]:
    root = root or DEFAULT_ROOT
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if (p / "meta.json").exists()), reverse=True)


def resolve_folder(name: str, root: Path | None = None) -> Path:
    """Turns a folder name from search results into a path, refusing anything that
    would point outside the library (a tool argument is untrusted input)."""
    root = root or DEFAULT_ROOT
    path = (root / name).resolve()
    if path.parent != root.resolve() or not (path / "meta.json").exists():
        raise ValueError(f"no video folder named {name!r} in {root}")
    return path


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
        "thumb": d["frames"][0]["file"] if d["frames"] else None,
        "has_notes": n is not None,
    }


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
                        + [o["text"] for o in d["ocr"]]).lower()
        score = sum(3 * strong.count(w) + weak.count(w) for w in words) if words else 1
        if score:
            hits.append((score, folder))
    hits.sort(key=lambda h: (-h[0], h[1].name))
    return [summary(f) | {"score": s} for s, f in hits[:limit]]
