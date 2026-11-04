"""Photo posts and carousels: downloaded from the embed page, read like a video's
frames, searchable by the text in the pictures, and marked as such in the library."""

import json

from fastapi.testclient import TestClient

from moodscroll import library, notes, pipeline, render, sources, web
from moodscroll.notes import Notes


def embed_html(post: dict) -> str:
    # The embed page carries the post as JSON inside a JSON string inside a script.
    ctx = json.dumps({"context": {"type": post["__typename"]}, "gql_data": {"shortcode_media": post}})
    return '<script>{"require":[["PolarisEmbedSimple","init",[],[{"isSidecar":true,"contextJSON":' \
        + json.dumps(ctx) + "}]]]}</script>"


CAROUSEL = {
    "__typename": "GraphSidecar", "shortcode": "CAROU12345", "is_video": False,
    "display_url": "https://cdn.example/cover.jpg",
    "owner": {"username": "parisfood"},
    "edge_media_to_caption": {"edges": [{"node": {"text": "5 bakeries in Paris"}}]},
    "edge_sidecar_to_children": {"edges": [
        {"node": {"is_video": False, "display_url": "https://cdn.example/1.jpg",
                  "accessibility_caption": "Photo by parisfood on May 01, 2026."}},
        {"node": {"is_video": False, "display_url": "https://cdn.example/2.jpg",
                  "accessibility_caption": "A croissant on a plate"}},
    ]},
}


def test_carousel_from_the_embed_page(tmp_path, monkeypatch):
    fetched = []

    def fake_get(url):
        fetched.append(url)
        return embed_html(CAROUSEL).encode() if "embed" in url else b"jpeg " + url.encode()
    monkeypatch.setattr(sources, "_get", fake_get)
    src = sources._download_instagram_embed("https://www.instagram.com/p/CAROU12345/", tmp_path)
    assert src.video is None and [p.read_bytes() for p in src.images] == [
        b"jpeg https://cdn.example/1.jpg", b"jpeg https://cdn.example/2.jpg"]
    assert src.meta["kind"] == "carousel" and src.meta["slides"] == 2
    assert src.meta["author"] == "parisfood" and src.meta["caption"] == "5 bakeries in Paris"
    assert src.meta["source"] == "https://www.instagram.com/p/CAROU12345/"
    assert src.meta["alt_text"] == ["A croissant on a plate"]  # Instagram's generic "Photo by" dropped


def test_single_photo_and_no_media(tmp_path, monkeypatch):
    photo = {"__typename": "GraphImage", "display_url": "https://cdn.example/p.jpg", "owner": {"username": "a"}}
    monkeypatch.setattr(sources, "_get", lambda url: embed_html(photo).encode() if "embed" in url else b"x")
    src = sources._download_instagram_embed("https://www.instagram.com/p/PHOTO12345/", tmp_path)
    assert len(src.images) == 1 and src.meta["kind"] == "photo"

    monkeypatch.setattr(sources, "_get", lambda url: b"<html>nothing</html>")
    try:
        sources._download_instagram_embed("https://www.instagram.com/p/GONE012345/", tmp_path / "x")
    except sources.SourceError as e:
        assert "no video" in str(e)
    else:
        raise AssertionError("expected SourceError")


def photo_folder(root, ocr):
    folder = root / "2026-11-04-bakeries"
    (folder / "frames").mkdir(parents=True)
    for n in (1, 2):
        (folder / "frames" / f"000{n}.jpg").write_bytes(b"jpg")
    meta = {"title": None, "author": "parisfood", "site": "Instagram", "kind": "carousel", "slides": 2,
            "source": "https://www.instagram.com/p/CAROU12345/", "caption": "5 bakeries"}
    pipeline._write_json(folder / "meta.json", meta)
    pipeline._write_json(folder / "frames.json", [{"file": "0001.jpg", "t": 1}, {"file": "0002.jpg", "t": 2}])
    pipeline._write_json(folder / "ocr.json", ocr)
    pipeline._write_json(folder / "transcript.json", {"language": None, "segments": []})
    pipeline._render(folder)
    return folder


OCR = [{"t": 2, "lines": ["Du Pain et des Idées", "34 Rue Yves Toudic"], "text": "Du Pain et des Idées / 34 Rue Yves Toudic"}]


def test_photo_post_is_searchable_by_its_pictures_text(tmp_path):
    photo_folder(tmp_path, OCR)
    hits = library.search("yves toudic", root=tmp_path)
    assert [h["folder"] for h in hits] == ["2026-11-04-bakeries"]
    assert hits[0]["kind"] == "carousel" and hits[0]["slides"] == 2


def test_photo_post_note_and_prompt(tmp_path):
    folder = photo_folder(tmp_path, OCR)
    md = (folder / "note.md").read_text()
    assert "## Pictures" in md and "![slide 2](frames/0002.jpg)" in md
    assert "`slide 2` Du Pain et des Idées / 34 Rue Yves Toudic" in md
    assert "Transcript" not in md and 'kind: "carousel"' in md
    d = pipeline.load(folder)
    prompt = notes.build_prompt(d["meta"], d["transcript"], d["ocr"])
    assert "A photo post: 2 picture(s)" in prompt and "[slide 2] Du Pain" in prompt
    assert notes.images_for_claude(d["meta"]) == 2
    assert notes.images_for_claude({"kind": "carousel", "slides": 20}) == notes.PICTURES_FOR_CLAUDE
    # notes don't change what kind of post it is
    out = pipeline.add_notes(folder, Notes(title="Five Paris bakeries", summary="s", category="travel",
                                           key_points=[], details=[], steps=[], claims_to_verify=[],
                                           tags=["paris"], worth_keeping=True))
    assert library.summary(out)["kind"] == "carousel" and "## Pictures" in (out / "note.md").read_text()


def test_kind_of_older_notes():
    assert library.kind({"source": "https://www.instagram.com/reel/AAAAA11111/"}) == "reel"
    assert library.kind({"source": "https://youtu.be/x"}) == "video"
    assert library.kind({"kind": "photo"}) == "photo"


def test_web_lists_kind_and_accepts_pictures(tmp_path, monkeypatch):
    photo_folder(tmp_path, OCR)
    monkeypatch.setattr(library, "DEFAULT_ROOT", tmp_path)
    client = TestClient(web.app, base_url="http://127.0.0.1:8765")
    assert client.get("/api/library").json()[0]["kind"] == "carousel"
    assert client.get("/api/notes/2026-11-04-bakeries").json()["meta"]["kind"] == "carousel"
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")))
    r = client.post("/api/jobs", files={"file": ("menu.png", b"png", "image/png")})
    assert r.status_code == 200


def test_render_video_unchanged():
    md = render.markdown({"title": "Clip", "kind": "reel"}, {"language": "en", "segments": [
        {"start": 65, "end": 66, "text": "Hello"}]}, [{"t": 65, "lines": ["Hi there"], "text": "Hi there"}],
        [{"file": "0001.jpg", "t": 65}], None)
    assert "![1:05](frames/0001.jpg)" in md and "`1:05` Hi there" in md and "## Transcript" in md
