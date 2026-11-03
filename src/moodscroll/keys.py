"""The optional Claude API key: check it, save it, switch it off and on.

Two modes, switchable at any time (from the app or the installer):
  assistant  no key; Claude Code or Codex writes the notes on your subscription
  api        the key is in ~/.config/moodscroll/.env; the app writes notes itself

Switching off never deletes the key: it moves to .env.off, so switching back on
needs no retyping. The key is never sent anywhere but Anthropic, and never shown.
"""

from __future__ import annotations

import os

import anthropic

from . import KEY_FILE

KEY_OFF = KEY_FILE.with_name(".env.off")
ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


class KeyProblem(Exception):
    """A key that can't be used; the message is safe to show (it never contains the key)."""


def active() -> bool:
    return any(os.environ.get(v) for v in ENV_VARS)


def check(key: str) -> None:
    """Asks Anthropic whether the key works (listing models costs nothing)."""
    key = key.strip()
    if not key.startswith("sk-ant-") or len(key) < 40 or any(c.isspace() for c in key):
        raise KeyProblem("That doesn't look like a Claude API key. It starts with sk-ant-.")
    try:
        anthropic.Anthropic(api_key=key).models.list(limit=1)
    except anthropic.AuthenticationError:
        raise KeyProblem("Anthropic rejected that key. Check it at platform.claude.com.") from None
    except anthropic.APIConnectionError:
        raise KeyProblem("Couldn't reach Anthropic to check the key. Are you online?") from None


def save(key: str) -> None:
    """Saves the key (readable only by you) and turns it on for this process."""
    key = key.strip()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"ANTHROPIC_API_KEY={key}\n")
    os.chmod(KEY_FILE, 0o600)
    os.environ["ANTHROPIC_API_KEY"] = key
    KEY_OFF.unlink(missing_ok=True)  # the new key replaces any switched-off one


def turn_off() -> None:
    """Back to Claude Code / Codex mode. Keeps the key in .env.off."""
    if KEY_FILE.exists():
        os.replace(KEY_FILE, KEY_OFF)
    for v in ENV_VARS:
        os.environ.pop(v, None)


def turn_on() -> None:
    """Uses the switched-off key again."""
    if not KEY_OFF.exists():
        raise KeyProblem("There's no saved key to turn back on.")
    from dotenv import dotenv_values

    key = (dotenv_values(KEY_OFF).get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise KeyProblem("The saved key file is empty. Paste a key instead.")
    os.replace(KEY_OFF, KEY_FILE)
    os.environ["ANTHROPIC_API_KEY"] = key


def status() -> dict:
    return {"mode": "api" if active() else "assistant", "saved_key_off": KEY_OFF.exists()}
