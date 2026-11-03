from moodscroll.media import clean_segments, dedupe_ocr, subsample
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


def test_dedupe_ocr_skips_repeated_subtitles():
    frames = [(0.0, ["Hello world", "SALE"]), (2.0, ["hello  WORLD", "New line"]), (4.0, ["SALE"])]
    assert dedupe_ocr(frames) == [{"t": 0.0, "text": "Hello world | SALE"}, {"t": 2.0, "text": "New line"}]


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

    md = markdown({**meta, "notes_error": "no key"}, transcript, [], [], None)
    assert "*No AI notes for this video: no key.*" in md
