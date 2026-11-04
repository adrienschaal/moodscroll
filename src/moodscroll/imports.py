"""Reads the list of posts you saved from Instagram's own data export.

Instagram: Meta Account → Your information and permissions → Export your
information → Export to device, with only "Saved" ticked. The ZIP it sends holds
links to your saved posts (not the videos), in JSON or HTML:

    your_instagram_activity/saved/saved_posts.json        every saved post
    your_instagram_activity/saved/saved_collections.json  your collections

This module only reads those files. It never logs in to Instagram, and nothing is
downloaded until you pick posts to import.
"""

from __future__ import annotations

import html as htmlmod
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath

POST = re.compile(r"https?://(?:www\.)?instagram\.com/(?:[A-Za-z0-9_.]+/)?(reels?|p|tv)/([A-Za-z0-9_-]{5,})")
MAX_FILE = 50 * 1024 * 1024  # a saved-posts file is a few MB even for thousands of posts


class ExportProblem(Exception):
    """The file isn't an Instagram export we can read; the message says why."""


def post_url(kind: str, code: str) -> str:
    """One clean link per post, without tracking parameters."""
    return f"https://www.instagram.com/{'p' if kind == 'p' else 'reel'}/{code}/"


def read_export(files: list[tuple[str, bytes]]) -> dict:
    """Reads an export: the ZIP Instagram sent, the folder it unzips to (as its
    files), or just saved_posts.json. Returns {"posts", "collections", "format"};
    each post is {"code", "url", "author", "caption", "saved_at", "collections"}."""
    texts: list[tuple[str, str]] = []
    for filename, data in files:
        name = filename.lower()
        if name.endswith(".zip") or data[:4] == b"PK\x03\x04":
            try:
                z = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                raise ExportProblem("That ZIP file is damaged. Download the export again.") from None
            for info in z.infolist():
                if _wanted(info.filename) and info.file_size <= MAX_FILE:
                    texts.append((info.filename, z.read(info).decode("utf-8", "replace")))
        elif _wanted(filename):
            texts.append((filename, data.decode("utf-8", "replace")))
    if not texts:
        raise ExportProblem("No saved posts in that. Drop the ZIP Instagram sent you (or the folder it "
                            "unzipped to). When you create the export, tick only “Saved”.")

    posts: dict[str, dict] = {}
    formats = set()
    for path, text in texts:
        is_collections = "collection" in PurePosixPath(path.lower()).name
        if path.lower().endswith(".json"):
            formats.add("json")
            try:
                found = _from_json(json.loads(text), is_collections)
            except json.JSONDecodeError:
                raise ExportProblem(f"{PurePosixPath(path).name} isn't valid JSON.") from None
        else:
            formats.add("html")
            found = _from_html(text, is_collections)
        for p in found:
            have = posts.setdefault(p["code"], {**p, "collections": []})
            for k in ("author", "caption", "saved_at"):
                have[k] = have.get(k) or p.get(k)
            if p.get("collection") and p["collection"] not in have["collections"]:
                have["collections"].append(p["collection"])
            have.pop("collection", None)

    if not posts:
        raise ExportProblem("Found the saved-posts file, but no post links in it.")
    out = sorted(posts.values(), key=lambda p: p["saved_at"] or "", reverse=True)
    counts: dict[str, int] = {}
    for p in out:
        for c in p["collections"]:
            counts[c] = counts.get(c, 0) + 1
    return {"posts": out,
            "collections": [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])],
            "format": "+".join(sorted(formats))}


def _wanted(path: str) -> bool:
    """saved_posts and saved_collections, not saved_music or anything else."""
    name = PurePosixPath(path.lower()).name
    return name.startswith(("saved_posts", "saved_collections")) and name.endswith((".json", ".html"))


# --- JSON ---------------------------------------------------------------------------
# saved_posts.json:  {"saved_saved_media": [{"title": "<author>", "string_map_data":
#                      {"Saved on": {"href": "<post>", "timestamp": 1730000000}}}, ...]}
# saved_collections.json: one list where a collection's own entry (its name, no post
#   link) comes first, then the posts in it, then the next collection.

def _from_json(doc, is_collections: bool) -> list[dict]:
    entries = _longest_list(doc)
    if entries and isinstance(entries[0], dict) and "label_values" in entries[0]:
        return _from_labels(entries, is_collections)
    out, collection = [], None  # the older layout, "string_map_data"
    for e in entries:
        href, ts = _first(e, "href"), _first(e, "timestamp")
        m = POST.search(href or "")
        if not m:
            if is_collections:  # a collection's header entry
                collection = _collection_name(e) or collection
            continue
        author = e.get("title") if isinstance(e, dict) else None
        if is_collections:
            author = _first_value_near_href(e) or author
        out.append({"code": m.group(2), "url": post_url(m.group(1), m.group(2)),
                    "author": author or None, "caption": None, "saved_at": _date(ts),
                    "collection": collection if is_collections else None})
    if not entries:  # unknown layout: still find every post link anywhere in the file
        for href in _all(doc, "href"):
            if m := POST.search(str(href)):
                out.append({"code": m.group(2), "url": post_url(m.group(1), m.group(2)),
                            "author": None, "caption": None, "saved_at": None, "collection": None})
    return out


# The 2026 layout: a list of entries, each {"timestamp", "label_values": [...]}, where
# every value is {"label": "URL" | "Caption" | "Username" | ..., "value", "href"?}
# and groups nest as {"title": "Owner" | "Media", "dict": [{"dict": [...]}, ...]}.
#   saved_posts.json        one entry per post; timestamp = when you saved it
#   saved_collections.json  one entry per collection: its "Name", then "Media", a
#                           group with one item per post in it

def _from_labels(entries: list[dict], is_collections: bool) -> list[dict]:
    out = []
    for e in entries:
        values = e.get("label_values") or []
        if is_collections:
            name = next((_fix_text(v["value"]) for v in values if v.get("label") == "Name" and v.get("value")), None)
            for group in values:
                for item in group.get("dict") or []:
                    if post := _post_from_values(item.get("dict") or [], None):
                        out.append({**post, "collection": name})
        elif post := _post_from_values(values, e.get("timestamp")):
            out.append({**post, "collection": None})
    return out


def _post_from_values(values: list, timestamp) -> dict | None:
    m = next((POST.search(v.get("href") or v.get("value") or "") for v in values
              if v.get("label") == "URL" and POST.search(v.get("href") or v.get("value") or "")), None)
    if not m:
        return None
    caption = next((v.get("value") for v in values if v.get("label") == "Caption"), None)
    author = next(iter(_labelled(values, "Username")), None)
    return {"code": m.group(2), "url": post_url(m.group(1), m.group(2)),
            "author": _fix_text(author) if author else None,
            "caption": _fix_text(caption)[:300] if caption else None, "saved_at": _date(timestamp)}


def _labelled(values, label: str):
    for v in values:
        if not isinstance(v, dict):
            continue
        if v.get("label") == label and v.get("value"):
            yield v["value"]
        for item in v.get("dict") or []:
            yield from _labelled(item.get("dict") or [item], label)


def _longest_list(doc):
    """The export's main list of entries, wherever its top-level key puts it."""
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        lists = [v for v in doc.values() if isinstance(v, list)]
        return max(lists, key=len) if lists else []
    return []


def _first(obj, key):
    for v in _all(obj, key):
        return v
    return None


def _all(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            else:
                yield from _all(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all(v, key)


def _collection_name(e) -> str | None:
    if not isinstance(e, dict):
        return None
    smd = e.get("string_map_data") or {}
    for key in ("Name", "Collection name", "name"):
        v = smd.get(key)
        if isinstance(v, dict) and v.get("value"):
            return _fix_text(v["value"])
    if isinstance(e.get("title"), str) and e["title"].strip():
        return _fix_text(e["title"])
    return None


def _first_value_near_href(e) -> str | None:
    """In a collection, a post entry names its author next to the link."""
    for v in _all(e, "value"):
        if isinstance(v, str) and v and not v.startswith("http"):
            return v
    return None


def _fix_text(s: str) -> str:
    # Meta's exports write UTF-8 bytes as \u00xx escapes ("cafÃ©"); undo that.
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _date(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# --- HTML ---------------------------------------------------------------------------
# The HTML export is the same data laid out as blocks, one per entry. We read every
# post link in order, the author (the block's heading) and the date next to it. In
# saved_collections.html a block without a post link is a collection's name.

_BLOCK = re.compile(r'<div class="pam[^"]*"[^>]*>', re.I)
_TEXT = re.compile(r"<[^>]+>")
_DATE = re.compile(r"([A-Z][a-z]{2} \d{1,2}, \d{4})")


def _from_html(page: str, is_collections: bool) -> list[dict]:
    blocks = _BLOCK.split(page)
    if len(blocks) < 2:  # an unfamiliar layout: one entry per link, in order
        blocks = re.split(r"(?=<a\s)", page)
    out, collection = [], None
    for b in blocks:
        hrefs = [htmlmod.unescape(h) for h in re.findall(r'href="([^"]+)"', b)]
        m = next((POST.search(h) for h in hrefs if POST.search(h)), None)
        text = [t.strip() for t in htmlmod.unescape(_TEXT.sub("\n", b)).split("\n") if t.strip()]
        if not m:
            if is_collections and text and len(blocks) > 2:
                collection = text[0]
            continue
        d = _DATE.search(" ".join(text))
        saved = None
        if d:
            try:
                saved = datetime.strptime(d.group(1), "%b %d, %Y").date().isoformat()
            except ValueError:
                pass
        author = next((t for t in text if not t.startswith("http") and not _DATE.search(t)
                       and t.lower() not in ("saved on", "added time", "name")), None)
        out.append({"code": m.group(2), "url": post_url(m.group(1), m.group(2)), "author": author,
                    "caption": None, "saved_at": saved, "collection": collection if is_collections else None})
    return out
