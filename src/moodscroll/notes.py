"""The one step that leaves the machine: Claude reads the transcript, the on-screen
text, the caption and a few key frames, and returns structured notes."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

from .media import is_photos, place, subsample

MODEL = os.environ.get("MOODSCROLL_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("MOODSCROLL_EFFORT", "medium")
FRAMES_FOR_CLAUDE = 4
PICTURES_FOR_CLAUDE = 10  # a carousel's pictures are the content, so more of them
TOKENS_PER_IMAGE = 1200  # about, for a picture or frame sent to Claude

CATEGORIES = [
    "recipe", "travel", "fitness", "health", "money", "career", "tech", "business",
    "style", "home", "photography", "ideas", "humor", "other",
]


class Detail(BaseModel):
    label: str = Field(description="e.g. an ingredient, a setting, a place, a price")
    value: str = Field(description="the exact quantity, value or address as stated")


class Notes(BaseModel):
    title: str = Field(description="a specific title under 60 characters — not the creator's clickbait")
    summary: str = Field(description="2-3 sentences: what the video says or shows")
    category: str = Field(description="one of: " + ", ".join(CATEGORIES))
    key_points: list[str] = Field(description="0-6 points worth remembering")
    details: list[Detail] = Field(description="exact quantities, settings, names, places, prices; empty if none")
    steps: list[str] = Field(description="ordered steps if the video teaches a method; empty otherwise")
    claims_to_verify: list[str] = Field(description="stats, health or money claims stated as fact that a reader should check")
    tags: list[str] = Field(description="3-6 lowercase tags")
    worth_keeping: bool = Field(description="false for memes, ads and reactions with nothing reusable")


SYSTEM = """You turn short videos and photo posts into notes someone will reread months later.
Keep the substance: the method, the quantities, the names, the places. Drop the hook,
the call to action and the filler. Write what the creator claims as their claim
("argues", "says"), not as fact. If the transcript and the on-screen text disagree,
trust the on-screen text for numbers. Write in English, whatever the video's language."""


class NotesUnavailable(Exception):
    pass


ASK_PHRASE = "finish my MooDscroll notes"
WAITING_HINT = f'Waiting for notes. Ask Claude Code or Codex to "{ASK_PHRASE}".'


def has_key() -> bool:
    """Whether this Mac can write notes itself (through the Claude API). Without a
    key, videos wait in the library until Claude Code or Codex writes their notes."""
    from .keys import active
    return active()


def _frame_block(path: Path) -> dict:
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def build_prompt(meta: dict, transcript: dict, ocr: list[dict]) -> str:
    lines = [f"[{s['start']:.0f}s] {s['text']}" for s in transcript["segments"]]
    if is_photos(meta):
        screen = [f"[{place(meta, o['t'])}] {o['text']}" for o in ocr]
        parts = [
            f"A photo post: {meta.get('slides') or 1} picture(s), no video.",
            f"Source: {meta.get('site') or 'local file'}",
            f"Author: {meta.get('author') or 'unknown'}",
            f"Caption:\n{meta.get('caption') or 'none'}",
            "Text in the pictures (read by OCR):\n" + ("\n".join(screen) or "(none)"),
        ]
        if meta.get("alt_text"):
            parts.append("Instagram's description of the pictures:\n" + "\n".join(meta["alt_text"]))
        return "\n\n".join(parts)
    screen = [f"[{o['t']:.0f}s] {o['text']}" for o in ocr]
    parts = [
        f"Source: {meta.get('site') or 'local file'}",
        f"Author: {meta.get('author') or 'unknown'}",
        f"Title: {meta.get('title') or 'none'}",
        f"Caption:\n{meta.get('caption') or 'none'}",
        f"Spoken language: {transcript.get('language') or 'no speech'}",
        "Transcript:\n" + ("\n".join(lines) or "(no speech)"),
        "On-screen text:\n" + ("\n".join(screen) or "(none)"),
    ]
    return "\n\n".join(parts)


# $ per million tokens (input, output), from Anthropic's price list.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def cost(input_tokens: int, output_tokens: int, model: str = MODEL) -> float:
    price_in, price_out = PRICES.get(model, PRICES["claude-opus-5-5"])
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def estimate_cost(meta: dict, transcript: dict, ocr: list[dict]) -> float:
    """What writing this video's notes through the API should cost, before sending.
    Fitted on real calls (Opus 5.5, effort medium): about 6,000 tokens of fixed
    overhead (instructions, note schema, 4 key frames) plus ~1 token per 2.5
    characters of transcript, caption and on-screen text; the notes themselves
    run 400-2,500 tokens and grow with the material. Rounded up 10%."""
    chars = len(build_prompt(meta, transcript, ocr))
    extra_images = max(0, images_for_claude(meta) - FRAMES_FOR_CLAUDE)
    tokens_in = 6000 + extra_images * TOKENS_PER_IMAGE + chars / 2.5
    tokens_out = min(2500, 400 + chars / 8)
    return round(cost(tokens_in, tokens_out) * 1.1, 4)


def images_for_claude(meta: dict) -> int:
    return min(meta.get("slides") or 1, PICTURES_FOR_CLAUDE) if is_photos(meta) else FRAMES_FOR_CLAUDE


def make_notes(meta: dict, transcript: dict, ocr: list[dict], frames_dir: Path, frames: list[dict]) -> tuple[Notes, dict]:
    """Returns the notes and a small usage record (model, tokens) for the log."""
    try:
        client = anthropic.Anthropic()
    except anthropic.AnthropicError as e:  # no credentials configured
        raise NotesUnavailable(str(e)) from e

    content = [_frame_block(frames_dir / f["file"]) for f in subsample(frames, images_for_claude(meta))]
    content.append({"type": "text", "text": build_prompt(meta, transcript, ocr)})

    try:
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=Notes,
            output_config={"effort": EFFORT},
            # If a safety classifier declines, the API retries on a suitable model
            # inside the same call instead of returning nothing.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as e:
        raise NotesUnavailable("Claude API key invalid") from e
    except TypeError as e:
        # The SDK only notices missing credentials when it builds the request.
        if "authentication" not in str(e):
            raise
        raise NotesUnavailable("no Claude API key") from e
    except anthropic.APIConnectionError as e:
        raise NotesUnavailable("could not reach the Claude API") from e
    except anthropic.RateLimitError as e:
        raise NotesUnavailable("rate limited by the Claude API, try again shortly") from e
    except anthropic.APIStatusError as e:
        raise NotesUnavailable(f"Claude API error {e.status_code}: {e.message}") from e

    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise NotesUnavailable(f"no notes returned (stop reason: {response.stop_reason})")
    usage = {
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return response.parsed_output, usage
