import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from moodscroll import imports, library, pipeline, web

SAVED = {"saved_saved_media": [
    {"title": "chef.anna", "string_map_data": {"Saved on": {
        "href": "https://www.instagram.com/reel/AAAAA11111/", "timestamp": 1761000000}}},
    {"title": "traveller", "string_map_data": {"Saved on": {
        "href": "https://www.instagram.com/p/BBBBB22222/?igsh=x", "timestamp": 1762000000}}},
]}
COLLECTIONS = {"saved_saved_collections": [
    {"title": "Collection", "string_map_data": {"Name": {"value": "Recipes ð\u009f\u008d\u009d"},
                                                "Creation Time": {"timestamp": 1760000000}}},
    {"string_map_data": {"Name": {"href": "https://www.instagram.com/reel/AAAAA11111/", "value": "chef.anna"},
                         "Added Time": {"timestamp": 1761000000}}},
]}
HTML = """<html><body><main>
<div class="pam _3-95 _2ph- _a6-g uiBoxWhite noborder"><h2>chef.anna</h2><div><table><tr><td>Saved on</td>
<td><a target="_blank" href="https://www.instagram.com/reel/AAAAA11111/">https://www.instagram.com/reel/AAAAA11111/</a>
<div>Oct 20, 2025 10:40 pm</div></td></tr></table></div></div>
<div class="pam _3-95 _2ph- _a6-g uiBoxWhite noborder"><h2>traveller</h2><div><table><tr><td>Saved on</td>
<td><a target="_blank" href="https://www.instagram.com/p/BBBBB22222/">https://www.instagram.com/p/BBBBB22222/</a>
<div>Nov 1, 2025 9:00 am</div></td></tr></table></div></div>
</main></body></html>"""


def zipped(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_json_export_with_collections():
    data = zipped({
        "your_instagram_activity/saved/saved_posts.json": json.dumps(SAVED),
        "your_instagram_activity/saved/saved_collections.json": json.dumps(COLLECTIONS),
        "media/photo.jpg": "not read",
    })
    r = imports.read_export([("instagram-adrien-2026-11-03.zip", data)])
    assert [p["code"] for p in r["posts"]] == ["BBBBB22222", "AAAAA11111"]  # newest saved first
    first, second = r["posts"][1], r["posts"][0]
    assert first == {"code": "AAAAA11111", "url": "https://www.instagram.com/reel/AAAAA11111/",
                     "author": "chef.anna", "caption": None, "saved_at": "2025-10-20",
                     "collections": ["Recipes 🍝"]}
    assert second["url"] == "https://www.instagram.com/p/BBBBB22222/"  # tracking parameter dropped
    assert r["collections"] == [{"name": "Recipes 🍝", "count": 1}] and r["format"] == "json"


def test_html_export():
    r = imports.read_export([("export.zip", zipped({"your_instagram_activity/saved/saved_posts.html": HTML}))])
    assert [(p["code"], p["author"], p["saved_at"]) for p in r["posts"]] == [
        ("BBBBB22222", "traveller", "2025-11-01"), ("AAAAA11111", "chef.anna", "2025-10-20")]


def test_single_file_and_problems():
    assert len(imports.read_export([("saved_posts.json", json.dumps(SAVED).encode())])["posts"]) == 2
    with pytest.raises(imports.ExportProblem, match="Saved"):
        imports.read_export([("export.zip", zipped({"your_instagram_activity/likes/liked_posts.json": "{}"}))])
    with pytest.raises(imports.ExportProblem):
        imports.read_export([("notes.txt", b"hello")])


@pytest.fixture
def client(tmp_path, monkeypatch):
    folder = tmp_path / "2026-11-03-pasta"
    folder.mkdir()
    (folder / "meta.json").write_text(json.dumps({"title": "Pasta", "source": "https://www.instagram.com/reel/AAAAA11111/"}))
    monkeypatch.setattr(library, "DEFAULT_ROOT", tmp_path)
    monkeypatch.setattr(web, "IMPORT_PACE_S", 0)
    return TestClient(web.app, base_url="http://127.0.0.1:8765")


def test_import_read_marks_library_and_start_queues(client, monkeypatch):
    data = zipped({"saved/saved_posts.json": json.dumps(SAVED)})
    r = client.post("/api/import/read", files=[("files", ("export.zip", data, "application/zip"))]).json()
    assert {p["code"]: p["in_library"] for p in r["posts"]} == {"AAAAA11111": True, "BBBBB22222": False}

    calls = []

    def fake_run(src, root, **kw):
        calls.append(src)
        raise RuntimeError("download failed: There is no video in this post")
    monkeypatch.setattr(pipeline, "run", fake_run)
    r = client.post("/api/import/start", json={"posts": [
        {"code": "BBBBB22222", "kind": "p", "author": "traveller"},
        {"code": "../../etc", "kind": "reel"},  # not a post code: refused
    ]}).json()
    assert r["queued"] == 1
    for _ in range(50):
        job = next(j for j in client.get("/api/jobs").json() if j.get("batch") == r["batch"])
        if job["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert calls == ["https://www.instagram.com/p/BBBBB22222/"]
    assert job["status"] == "skipped" and job["label"] == "@traveller"


# The layout of a real export from November 2026 (values shortened).
POSTS_2026 = [{"timestamp": 1793749583, "media": [], "fbid": "1", "label_values": [
    {"label": "URL", "value": "https://www.instagram.com/reel/CCCCC33333/", "href": "https://www.instagram.com/reel/CCCCC33333/"},
    {"label": "Caption", "value": "Caf\u00c3\u00a9 cr\u00c3\u00a8me"},
    {"label": "Title", "value": ""},
    {"title": "Owner", "dict": [{"title": "", "dict": [
        {"label": "URL", "value": "http://example.com/"}, {"label": "Name", "value": "Chef"},
        {"label": "Username", "value": "chef.cafe"}]}]}]}]
COLLECTIONS_2026 = [{"timestamp": 1772145791, "media": [], "fbid": "2", "label_values": [
    {"label": "Name", "value": "Recipes"}, {"label": "Type", "value": "Default"},
    {"title": "Media", "dict": [{"title": "", "dict": [
        {"label": "URL", "value": "https://www.instagram.com/reel/CCCCC33333/", "href": "https://www.instagram.com/reel/CCCCC33333/"},
        {"label": "Caption", "value": "x"}]}]}]}]


def test_2026_layout_from_an_unzipped_folder():
    r = imports.read_export([
        ("saved_posts.json", json.dumps(POSTS_2026).encode()),
        ("saved_collections.json", json.dumps(COLLECTIONS_2026).encode()),
        ("saved_music.json", b"[]"),  # ignored
    ])
    assert r["posts"] == [{"code": "CCCCC33333", "url": "https://www.instagram.com/reel/CCCCC33333/",
                           "author": "chef.cafe", "caption": "Café crème", "saved_at": "2026-11-03",
                           "collections": ["Recipes"]}]
