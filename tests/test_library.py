import json

import pytest

from moodscroll import library, pipeline
from moodscroll.notes import Notes


def make_folder(root, name, title, transcript="", caption=""):
    folder = root / name
    (folder / "frames").mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"title": title, "caption": caption}))
    (folder / "transcript.json").write_text(json.dumps(
        {"language": "en", "segments": [{"start": 0, "end": 1, "text": transcript}] if transcript else []}))
    return folder


def notes(title, tags, summary="s"):
    return Notes(title=title, summary=summary, category="recipe", key_points=[], details=[],
                 steps=[], claims_to_verify=[], tags=tags, worth_keeping=True)


def test_add_notes_renders_and_renames(tmp_path):
    folder = make_folder(tmp_path, "2026-11-03-video-by-someone", "Video by someone")
    out = pipeline.add_notes(folder, notes("Crispy Gnocchi", ["pasta"]))
    assert out.name == "2026-11-03-crispy-gnocchi" and not folder.exists()
    assert (out / "note.md").read_text().startswith('---\ntitle: "Crispy Gnocchi"')
    assert pipeline.load(out)["notes"].tags == ["pasta"]


def test_search_ranks_title_and_tags_above_transcript(tmp_path):
    a = make_folder(tmp_path, "2026-11-01-a", "a", transcript="we talk about pasta once")
    b = make_folder(tmp_path, "2026-11-02-b", "b")
    pipeline.add_notes(b, notes("Pasta night", ["pasta", "dinner"]))
    make_folder(tmp_path, "2026-11-03-c", "c", transcript="nothing relevant")
    hits = library.search("pasta", root=tmp_path)
    assert [h["folder"] for h in hits] == ["2026-11-02-pasta-night", a.name]


def test_resolve_folder_refuses_paths_outside_library(tmp_path):
    make_folder(tmp_path, "2026-11-01-a", "a")
    assert library.resolve_folder("2026-11-01-a", root=tmp_path).name == "2026-11-01-a"
    for bad in ["../x", "/etc", "2026-11-01-a/frames", "missing"]:
        with pytest.raises(ValueError):
            library.resolve_folder(bad, root=tmp_path)


def test_waiting_and_old_names_after_notes(tmp_path):
    a = make_folder(tmp_path, "2026-11-01-video-by-x", "Video by x")
    make_folder(tmp_path, "2026-11-02-video-by-y", "Video by y")
    assert [w["folder"] for w in library.waiting(tmp_path)] == ["2026-11-01-video-by-x", "2026-11-02-video-by-y"]

    out = pipeline.add_notes(a, notes("Crispy Gnocchi", ["pasta"]))
    assert [w["folder"] for w in library.waiting(tmp_path)] == ["2026-11-02-video-by-y"]
    # a link opened before the notes were written still finds the renamed folder
    assert library.resolve_folder("2026-11-01-video-by-x", tmp_path) == out.resolve()
    with pytest.raises(ValueError):
        library.resolve_folder("../2026-11-01-video-by-x", tmp_path)


def test_mcp_tools(tmp_path, monkeypatch):
    import asyncio
    from moodscroll import mcp_server

    monkeypatch.setattr(library, "DEFAULT_ROOT", tmp_path)
    make_folder(tmp_path, "2026-11-01-video-by-x", "Video by x", transcript="hello")
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert names == {"process_video", "list_waiting", "get_video", "save_notes", "search_notes", "read_note"}
    assert "2026-11-01-video-by-x" in mcp_server.list_waiting()
    text = mcp_server.get_video("2026-11-01-video-by-x")[0]
    assert "folder: 2026-11-01-video-by-x" in text and "hello" in text
    path = mcp_server.save_notes("2026-11-01-video-by-x", notes("Crispy Gnocchi", ["pasta"]))
    assert path.endswith("2026-11-03-crispy-gnocchi/note.md") or "crispy-gnocchi" in path
    assert mcp_server.list_waiting() == "Nothing is waiting for notes."
