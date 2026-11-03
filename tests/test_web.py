import json

import pytest
from fastapi.testclient import TestClient

from moodscroll import library, web


@pytest.fixture
def client(tmp_path, monkeypatch):
    folder = tmp_path / "2026-11-03-clip"
    (folder / "frames").mkdir(parents=True)
    (folder / "frames" / "0001.jpg").write_bytes(b"jpg")
    (folder / "meta.json").write_text(json.dumps({"title": "Clip"}))
    (folder / "frames.json").write_text(json.dumps([{"file": "0001.jpg", "t": 0}]))
    (folder / "note.md").write_text("# Clip\n")
    (tmp_path / "secret.txt").write_text("nope")
    monkeypatch.setattr(library, "DEFAULT_ROOT", tmp_path)
    return TestClient(web.app, base_url="http://127.0.0.1:8765")


def test_library_and_note(client):
    items = client.get("/api/library").json()
    assert [i["folder"] for i in items] == ["2026-11-03-clip"] and items[0]["thumb"] == "0001.jpg"
    note = client.get("/api/notes/2026-11-03-clip").json()
    assert note["markdown"] == "# Clip\n" and note["video"] is None
    assert client.get("/media/2026-11-03-clip/frames/0001.jpg").content == b"jpg"


def test_media_stays_inside_the_note_folder(client):
    assert client.get("/media/2026-11-03-clip/../secret.txt").status_code == 404
    assert client.get("/media/2026-11-03-clip/%2e%2e/secret.txt").status_code == 404
    assert client.get("/api/notes/..").status_code == 404


def test_job_input_is_validated(client):
    assert client.post("/api/jobs", data={"url": "not a link"}).status_code == 400
    r = client.post("/api/jobs", files={"file": ("notes.txt", b"x", "text/plain")})
    assert r.status_code == 400 and "not a video" in r.json()["detail"]
    assert client.post("/api/jobs").status_code == 400


def test_other_websites_are_refused(client):
    assert client.post("/api/jobs", data={"url": "https://x.com/v"}, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/library", headers={"host": "evil.example:8765"}).status_code == 403
    assert client.get("/api/library", headers={"origin": "http://127.0.0.1:8765"}).status_code == 200
