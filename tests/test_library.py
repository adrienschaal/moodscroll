import json

import pytest

from vnotes import library, pipeline
from vnotes.notes import Notes


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
