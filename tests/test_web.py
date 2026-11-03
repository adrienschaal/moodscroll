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


@pytest.fixture
def key_files(tmp_path, monkeypatch):
    """A fake key location, so tests never touch the real ~/.config/moodscroll."""
    from moodscroll import keys
    cfg = tmp_path / "config"
    monkeypatch.setattr(keys, "KEY_FILE", cfg / ".env")
    monkeypatch.setattr(keys, "KEY_OFF", cfg / ".env.off")
    monkeypatch.setattr(web, "KEY_FILE", cfg / ".env")
    for v in keys.ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    checked = []
    monkeypatch.setattr(keys.anthropic, "Anthropic", lambda api_key: checked.append(api_key) or _FakeClient(api_key))
    return cfg, checked


class _FakeClient:
    def __init__(self, key):
        import types
        def list_(limit):
            if key.endswith("bad"):
                import httpx
                from moodscroll.keys import anthropic
                raise anthropic.AuthenticationError("bad", response=httpx.Response(401, request=httpx.Request("GET", "https://x")), body=None)
        self.models = types.SimpleNamespace(list=list_)


GOOD = "sk-ant-api03-" + "x" * 40
POST = {"headers": {"Origin": "http://127.0.0.1:8765"}}


def test_switch_between_assistant_and_api_key(client, key_files):
    cfg, checked = key_files
    assert client.get("/api/status").json()["mode"] == "assistant"

    r = client.post("/api/key", json={"key": "hello"}, **POST)
    assert r.status_code == 400 and "sk-ant-" in r.json()["detail"] and not checked
    r = client.post("/api/key", json={"key": GOOD[:-3] + "bad"}, **POST)
    assert r.status_code == 400 and "rejected" in r.json()["detail"]
    assert not (cfg / ".env").exists()

    r = client.post("/api/key", json={"key": GOOD}, **POST)
    assert r.json()["mode"] == "api" and GOOD not in r.text  # never echoed back
    assert (cfg / ".env").stat().st_mode & 0o777 == 0o600

    r = client.post("/api/key/off", **POST).json()
    assert r["mode"] == "assistant" and r["saved_key_off"] and not (cfg / ".env").exists()
    assert client.post("/api/waiting/write", **POST).status_code == 400

    assert client.post("/api/key/on", **POST).json()["mode"] == "api"
    assert (cfg / ".env").read_text() == f"ANTHROPIC_API_KEY={GOOD}\n"


def test_key_cannot_be_set_from_another_website(client, key_files):
    r = client.post("/api/key", json={"key": GOOD}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and not (key_files[0] / ".env").exists()


def test_delete_moves_to_trash(client, tmp_path, monkeypatch):
    trash = tmp_path.parent / (tmp_path.name + "-trash")
    monkeypatch.setattr(web, "TRASH", trash)
    assert client.delete("/api/notes/%2E%2E").status_code in (404, 405)
    assert client.delete("/api/notes/secret.txt").status_code == 404
    assert client.delete("/api/notes/2026-11-03-clip").json() == {"trashed": "2026-11-03-clip"}
    assert (trash / "2026-11-03-clip" / "note.md").exists() and client.get("/api/library").json() == []
    assert (tmp_path / "secret.txt").exists()
