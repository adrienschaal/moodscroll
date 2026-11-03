import pytest
from moodscroll.media import clean_ocr, clean_segments, ocr_lines, paragraphs, subsample
from moodscroll.notes import Detail, Notes
from moodscroll.pipeline import slugify
from moodscroll.render import markdown
from moodscroll.sources import instagram_code, is_url


def seg(start, text, logprob=-0.1, ratio=1.4):
    return {"start": start, "end": start + 2, "text": text, "avg_logprob": logprob, "compression_ratio": ratio}


def test_clean_segments_drops_made_up_text():
    segments = [
        seg(0, " Real speech. "),
        seg(3, "p p p p p p p p", ratio=7.9),           # loop over music
        seg(5, "Pack rum prose JOSHUA", logprob=-5.2),  # unsure of every word
        seg(95, "Thanks for watching"),                 # after the video ended
        seg(6, "   "),
    ]
    assert clean_segments(segments, video_duration=92.9) == [{"start": 0, "end": 2, "text": "Real speech."}]


def test_clean_ocr_drops_repeats_scraps_and_subtitles():
    frames = [(0.0, ["Hello world", "SALE"]), (2.0, ["hello  WORLD", "New line"]), (4.0, ["SALE"])]
    assert clean_ocr(frames) == [{"t": 0.0, "lines": ["Hello world", "SALE"], "text": "Hello world / SALE"},
                                 {"t": 2.0, "lines": ["New line"], "text": "New line"}]

    # From a real reel: burned-in captions repeat the speech in fragments.
    spoken = ("I'm going to show you how to do the same exact thing. They all use these little things "
              "called NFC stickers. You can program them to do things.")
    frames = [(2.6, ["I'm gonna show you how", "to"]), (5.7, ["they all use these little", "things"]),
              (12.6, ["Fogos", "program them to do", "Cancel"]), (13.0, ["24", "|"])]
    assert clean_ocr(frames, spoken) == [{"t": 12.6, "lines": ["Fogos", "Cancel"], "text": "Fogos / Cancel"}]
    assert ocr_lines({"t": 0, "text": "old | format"}) == ["old", "format"]


def test_paragraphs_join_short_segments():
    segs = [{"start": 0, "end": 2, "text": "Don't ever spend money on app blocking devices."},
            {"start": 2.6, "end": 5.5, "text": "I'm going to show you how to do the same exact thing at a fraction of the price."},
            {"start": 5.7, "end": 8.1, "text": "They all use these little things called NFC stickers,"},
            {"start": 8.3, "end": 10.6, "text": "and you can buy a roll of 50 for like eight bucks."},
            {"start": 14, "end": 15, "text": "After a pause."}]
    assert [[s["start"] for s in p] for p in paragraphs(segs)] == [[0, 2.6, 5.7, 8.3], [14]]


def test_subsample_keeps_ends_and_count():
    items = list(range(100))
    picked = subsample(items, 5)
    assert len(picked) == 5 and picked[0] == 0 and picked[-1] == 99
    assert subsample([1, 2], 5) == [1, 2]


def test_slugify():
    assert slugify("Pâtes à la crème — 3 ingrédients!") == "pates-a-la-creme-3-ingredients"
    assert slugify("!!!") == "video"


def test_source_detection():
    assert is_url("https://youtu.be/x") and not is_url("~/Movies/clip.mov")
    assert instagram_code("https://www.instagram.com/reel/Ab-CdEf1G23/?igsh=abc") == "Ab-CdEf1G23"
    assert instagram_code("https://www.instagram.com/someone/p/ABC123/") == "ABC123"


def test_markdown_with_and_without_notes():
    transcript = {"language": "en", "segments": [{"start": 65, "end": 67, "text": "Add the salt."}]}
    frames = [{"file": "0001.jpg", "t": 0.0}]
    meta = {"source": "https://example.com/v", "author": "chef", "caption": "Easy pasta"}
    notes = Notes(title="Cacio e pepe", summary="A three-ingredient pasta.", category="recipe",
                  key_points=["Use pasta water"], details=[Detail(label="Pecorino", value="100 g")],
                  steps=["Boil", "Toss"], claims_to_verify=[], tags=["pasta"], worth_keeping=True)

    md = markdown(meta, transcript, [], frames, notes)
    assert md.startswith("---\ntitle: \"Cacio e pepe\"")
    assert "- **Pecorino:** 100 g" in md and "1. Boil" in md
    assert "`1:05` Add the salt." in md and "](frames/0001.jpg)" in md
    assert "Claims to verify" not in md  # empty sections are left out

    md = markdown({**meta, "notes_error": "Claude API key invalid"}, transcript, [], [], None)
    assert "*Notes failed: Claude API key invalid. Waiting for notes." in md
    assert "Waiting for notes. Ask Claude Code or Codex" in markdown(meta, transcript, [], [], None)


def test_run_without_key_leaves_video_waiting(tmp_path, monkeypatch):
    from moodscroll import pipeline

    folder = tmp_path / "2026-11-03-v"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(pipeline, "extract", lambda *a, **k: folder)
    monkeypatch.setattr(pipeline.notes, "make_notes", lambda *a: pytest.fail("must not call the API"))
    messages = []
    assert pipeline.run("x.mp4", tmp_path, progress=messages.append) == folder
    assert "Waiting for notes" in messages[-1]
