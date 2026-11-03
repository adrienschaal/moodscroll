"""The one step that leaves the machine: Claude reads the transcript, the on-screen
text, the caption and a few key frames, and returns structured notes."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

from .media import subsample

MODEL = os.environ.get("MOODSCROLL_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("MOODSCROLL_EFFORT", "medium")
FRAMES_FOR_CLAUDE = 4

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


SYSTEM = """You turn short videos into notes someone will reread months later.
Keep the substance: the method, the quantities, the names, the places. Drop the hook,
the call to action and the filler. Write what the creator claims as their claim
("argues", "says"), not as fact. If the transcript and the on-screen text disagree,
trust the on-screen text for numbers. Write in English, whatever the video's language."""


class NotesUnavailable(Exception):
    pass


def _frame_block(path: Path) -> dict:
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def build_prompt(meta: dict, transcript: dict, ocr: list[dict]) -> str:
    lines = [f"[{s['start']:.0f}s] {s['text']}" for s in transcript["segments"]]
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


def make_notes(meta: dict, transcript: dict, ocr: list[dict], frames_dir: Path, frames: list[dict]) -> tuple[Notes, dict]:
    """Returns the notes and a small usage record (model, tokens) for the log."""
    try:
        client = anthropic.Anthropic()
    except anthropic.AnthropicError as e:  # no credentials configured
        raise NotesUnavailable(str(e)) from e

    content = [_frame_block(frames_dir / f["file"]) for f in subsample(frames, FRAMES_FOR_CLAUDE)]
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
        raise NotesUnavailable("no Claude API key: add one with moodscroll-setup, or use MOODscroll inside Claude") from e
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
