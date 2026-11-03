"""moodscroll-setup: everything after the code is downloaded. install.sh runs it;
it is safe to run again (each step skips what is already done).

    moodscroll-setup               # asks before each optional step
    moodscroll-setup --yes         # accepts every step, never asks
    moodscroll-setup --uninstall   # removes the app and the Claude connections
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from . import KEY_FILE, library, media

REPO = Path(__file__).resolve().parents[2]
APP = Path.home() / "Applications" / "MOODscroll.app"
ICON = REPO / "assets" / "AppIcon.icns"
DESKTOP_CONFIG = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
LOG = Path.home() / "Library" / "Logs" / "MOODscroll.log"
MCP_NAME = "moodscroll"

BOLD, DIM, GREEN, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[0m"


def say(msg: str) -> None:
    print(f"\n{BOLD}{msg}{RESET}")


def done(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def note(msg: str) -> None:
    print(f"  {DIM}{msg}{RESET}")


def ask(question: str, yes: bool) -> bool:
    if yes:
        return True
    answer = input(f"  {question} [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


def uv() -> str:
    return shutil.which("uv") or "/opt/homebrew/bin/uv"


def mcp_command() -> dict:
    return {"command": uv(), "args": ["--directory", str(REPO), "run", "moodscroll-mcp"]}


# --- Steps --------------------------------------------------------------------------

def whisper_model() -> None:
    say("1/5  Speech-to-text model (Whisper, ~1.6 GB, runs on this Mac)")
    from huggingface_hub import snapshot_download

    snapshot_download(media.WHISPER_MODEL)
    done(f"{media.WHISPER_MODEL} is ready")


def ocr_helper() -> None:
    say("2/5  On-screen text reader (Apple Vision)")
    media._swift_binary("ocr")
    done("compiled")


def api_key(yes: bool) -> None:
    say("3/5  Claude API key (for the app and the command line; not needed in Claude itself)")
    import anthropic

    if os.environ.get("ANTHROPIC_API_KEY"):
        done(f"already set ({KEY_FILE if KEY_FILE.exists() else 'environment'})")
        return
    if yes:
        note(f"skipped; add one later: moodscroll-setup, or put ANTHROPIC_API_KEY=… in {KEY_FILE}")
        return
    note("Create one at https://platform.claude.com/settings/keys (about $0.04 a video).")
    key = getpass.getpass("  Paste it here (typing is hidden), or press Enter to skip: ").strip()
    if not key:
        note("skipped; the app still transcribes, notes need a key")
        return
    try:
        anthropic.Anthropic(api_key=key).models.list(limit=1)
    except anthropic.AuthenticationError:
        note("that key was rejected; nothing saved. Run moodscroll-setup again to retry.")
        return
    except anthropic.APIConnectionError:
        note("couldn't reach Anthropic to check it; saving it anyway")
    save_key(key)
    done(f"saved to {KEY_FILE} (readable only by you)")


def save_key(key: str) -> None:
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"ANTHROPIC_API_KEY={key}\n")
    os.environ["ANTHROPIC_API_KEY"] = key


def mac_app(yes: bool) -> None:
    say("4/5  MOODscroll app (Applications, Spotlight, Launchpad, Dock)")
    if not ask(f"Create {APP}?", yes):
        note("skipped; start it with: uv run moodscroll-web")
        return
    macos = APP / "Contents" / "MacOS"
    resources = APP / "Contents" / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    shutil.copy(ICON, resources / "AppIcon.icns")
    with open(APP / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump({
            "CFBundleName": "MOODscroll",
            "CFBundleDisplayName": "MOODscroll",
            "CFBundleIdentifier": "com.adrienschaal.moodscroll",
            "CFBundleExecutable": "MOODscroll",
            "CFBundleIconFile": "AppIcon",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "1.0",
            "LSUIElement": True,  # no Dock bounce: the window is a browser tab
        }, f)
    launcher = macos / "MOODscroll"
    launcher.write_text(f"""#!/bin/bash
# Starts the MOODscroll server in the background if it isn't running, then opens it.
URL=http://127.0.0.1:8765
if ! /usr/bin/curl -s -o /dev/null --max-time 1 "$URL/api/jobs"; then
  cd "$HOME"
  nohup "{uv()}" --directory "{REPO}" run moodscroll-web --no-browser >>"{LOG}" 2>&1 &
  for _ in $(seq 1 60); do
    /usr/bin/curl -s -o /dev/null --max-time 1 "$URL/api/jobs" && break
    sleep 0.5
  done
fi
open "$URL"
""")
    launcher.chmod(0o755)
    # Tell Finder and Spotlight about the new app (and its icon) right away.
    subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
                    "/Support/lsregister", "-f", str(APP)], capture_output=True)
    done(f"{APP} — open it from Spotlight (⌘ Space, type MOODscroll); drag it to the Dock to keep it")


def claude_connections(yes: bool) -> None:
    say("5/5  Use MOODscroll inside Claude (your Claude plan writes the notes, no API key)")
    if shutil.which("claude"):
        if ask("Connect it to Claude Code?", yes):
            subprocess.run(["claude", "mcp", "remove", MCP_NAME, "--scope", "user"], capture_output=True)
            cmd = mcp_command()
            r = subprocess.run(["claude", "mcp", "add", MCP_NAME, "--scope", "user", "--",
                                cmd["command"], *cmd["args"]], capture_output=True, text=True)
            done("Claude Code: connected") if r.returncode == 0 else note(f"Claude Code: failed: {r.stderr.strip()}")
    else:
        note("Claude Code not found; skipped")

    if DESKTOP_CONFIG.parent.exists():
        if ask("Connect it to the Claude desktop app?", yes):
            config = json.loads(DESKTOP_CONFIG.read_text()) if DESKTOP_CONFIG.exists() else {}
            if DESKTOP_CONFIG.exists():
                shutil.copy2(DESKTOP_CONFIG, DESKTOP_CONFIG.with_name(DESKTOP_CONFIG.name + ".bak"))
            config.setdefault("mcpServers", {})[MCP_NAME] = mcp_command()
            _write_json(DESKTOP_CONFIG, config)
            done("Claude desktop app: connected — quit Claude (⌘Q) and reopen it to load it")
    else:
        note("Claude desktop app not found; skipped")


def uninstall() -> None:
    say("Uninstalling MOODscroll")
    if APP.exists():
        shutil.rmtree(APP)
        done(f"removed {APP}")
    if shutil.which("claude"):
        subprocess.run(["claude", "mcp", "remove", MCP_NAME, "--scope", "user"], capture_output=True)
        done("disconnected from Claude Code")
    if DESKTOP_CONFIG.exists():
        config = json.loads(DESKTOP_CONFIG.read_text())
        if config.get("mcpServers", {}).pop(MCP_NAME, None):
            _write_json(DESKTOP_CONFIG, config)
            done("disconnected from the Claude desktop app")
    note(f"Kept your notes ({library.DEFAULT_ROOT}) and your key ({KEY_FILE}).")
    note(f"Delete them yourself if you want them gone, and this folder: {REPO}")


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def main() -> None:
    p = argparse.ArgumentParser(prog="moodscroll-setup", description=__doc__.split("\n")[0])
    p.add_argument("--yes", action="store_true", help="accept every step without asking")
    p.add_argument("--uninstall", action="store_true", help="remove the app and the Claude connections")
    args = p.parse_args()
    if args.uninstall:
        uninstall()
        return
    try:
        whisper_model()
        ocr_helper()
        api_key(args.yes)
        mac_app(args.yes)
        claude_connections(args.yes)
    except KeyboardInterrupt:
        sys.exit("\nStopped. Run moodscroll-setup again any time; it picks up where it left off.")
    say("All set.")
    note(f"Your notes will be in {library.DEFAULT_ROOT}")


if __name__ == "__main__":
    main()
