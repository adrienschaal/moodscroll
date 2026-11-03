"""Builds note.md: plain Markdown with YAML front matter, so it opens nicely in
Obsidian, on GitHub, or in any text editor."""

from __future__ import annotations

import json

from .notes import Notes


def _ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _yaml(value) -> str:
    # JSON strings and lists are valid YAML, which keeps quoting rules simple.
    return json.dumps(value, ensure_ascii=False)


def markdown(meta: dict, transcript: dict, ocr: list[dict], frames: list[dict], notes: Notes | None) -> str:
    title = (notes.title if notes else None) or meta.get("title") or "Untitled video"
    front = {
        "title": title,
        "source": meta.get("source"),
        "author": meta.get("author"),
        "site": meta.get("site"),
        "duration_s": meta.get("duration_s"),
        "language": transcript.get("language"),
    }
    if notes:
        front.update(category=notes.category, tags=notes.tags, worth_keeping=notes.worth_keeping)

    out = ["---"]
    out += [f"{k}: {_yaml(v)}" for k, v in front.items() if v not in (None, [], "")]
    out += ["---", "", f"# {title}", ""]

    if notes:
        out += [notes.summary, ""]
        if notes.key_points:
            out += ["## Key points"] + [f"- {p}" for p in notes.key_points] + [""]
        if notes.details:
            out += ["## Details"] + [f"- **{d.label}:** {d.value}" for d in notes.details] + [""]
        if notes.steps:
            out += ["## Steps"] + [f"{i}. {s}" for i, s in enumerate(notes.steps, 1)] + [""]
        if notes.claims_to_verify:
            out += ["## Claims to verify"] + [f"- {c}" for c in notes.claims_to_verify] + [""]
    else:
        out += ["*No AI notes for this video" + (f": {meta['notes_error']}" if meta.get("notes_error") else "") + ".*", ""]

    if meta.get("caption"):
        out += ["## Caption", "", meta["caption"].strip(), ""]
    if frames:
        out += ["## Key frames", ""]
        out += [f"![{_ts(f['t'])}](frames/{f['file']})" for f in frames] + [""]
    if ocr:
        out += ["## On-screen text"] + [f"- `{_ts(o['t'])}` {o['text']}" for o in ocr] + [""]
    out += ["## Transcript"]
    if transcript["segments"]:
        out += [f"`{_ts(s['start'])}` {s['text']}  " for s in transcript["segments"]]
    else:
        out += ["(no speech)"]
    return "\n".join(out) + "\n"
