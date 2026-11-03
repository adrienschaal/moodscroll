"""moodscroll-setup: everything after the code is downloaded. install.sh runs it;
it is safe to run again (each step skips what is already done).

    moodscroll-setup               # asks before each optional step
    moodscroll-setup --yes         # accepts every step, never asks
    moodscroll-setup --uninstall   # removes the app and the Claude Code / Codex connections
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

from . import KEY_FILE, keys, library, media
from .notes import ASK_PHRASE

REPO = Path(__file__).resolve().parents[2]
APP = Path.home() / "Applications" / "MOODscroll.app"
ICON = REPO / "assets" / "AppIcon.icns"
DESKTOP_CONFIG = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
# Codex ships inside the ChatGPT desktop app; a separate CLI install may also exist.
CODEX_BINARIES = ("/Applications/ChatGPT.app/Contents/Resources/codex", "/Applications/Codex.app/Contents/Resources/codex")
# Codex stops waiting on a tool after 60 s by default; a long video takes longer.
CODEX_TIMEOUTS = 'startup_timeout_sec = 60\ntool_timeout_sec = 900\n'
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
    try:
        answer = input(f"  {question} [Y/n] ").strip().lower()
    except EOFError:  # no keyboard (run from a script): don't change anything
        print()
        return False
    return answer in ("", "y", "yes")


def uv() -> str:
    return shutil.which("uv") or "/opt/homebrew/bin/uv"


def mcp_command() -> dict:
    return {"command": uv(), "args": ["--directory", str(REPO), "run", "moodscroll-mcp"]}


def codex() -> str | None:
    return shutil.which("codex") or next((c for c in CODEX_BINARIES if os.access(c, os.X_OK)), None)


def claude() -> str | None:
    return shutil.which("claude") or next(
        (str(c) for c in (Path.home() / ".local/bin/claude", Path.home() / ".claude/local/claude") if c.exists()), None)


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
    say("5/5  Claude API key (optional)")
    note("Not needed if you use Claude Code or Codex: they write the notes on your subscription.")
    note("With a key, the MOODscroll app also writes notes by itself, about $0.04 a video.")
    note("You can switch between the two any time, in the app.")
    if keys.active():
        done(f"already on ({KEY_FILE if KEY_FILE.exists() else 'environment'})")
        return
    if yes:
        note("skipped")
        return
    note("Create one at https://platform.claude.com/settings/keys")
    key = getpass.getpass("  Paste it here (typing is hidden), or press Enter to skip: ").strip()
    if not key:
        note("skipped; videos you add in the app wait for Claude Code or Codex to write their notes")
        return
    try:
        keys.check(key)
    except keys.KeyProblem as e:
        note(f"{e} Nothing saved; you can add a key later in the app.")
        return
    keys.save(key)
    done(f"saved to {KEY_FILE} (readable only by you)")


def mac_app(yes: bool) -> None:
    say("3/5  MOODscroll app (Applications, Spotlight, Launchpad, Dock)")
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


def connect_assistants(yes: bool) -> None:
    say("4/5  Connect it to Claude Code and Codex (your subscription writes the notes, no API key)")
    found = False
    if c := claude():
        found = True
        if ask("Connect it to Claude Code?", yes):
            subprocess.run([c, "mcp", "remove", MCP_NAME, "--scope", "user"], capture_output=True)
            cmd = mcp_command()
            r = subprocess.run([c, "mcp", "add", MCP_NAME, "--scope", "user", "--",
                                cmd["command"], *cmd["args"]], capture_output=True, text=True)
            done("Claude Code: connected") if r.returncode == 0 else note(f"Claude Code: failed: {r.stderr.strip()}")
        # The Claude desktop app's chat reads its own config, not Claude Code's.
        if DESKTOP_CONFIG.parent.exists():
            config = json.loads(DESKTOP_CONFIG.read_text()) if DESKTOP_CONFIG.exists() else {}
            if DESKTOP_CONFIG.exists():
                shutil.copy2(DESKTOP_CONFIG, DESKTOP_CONFIG.with_name(DESKTOP_CONFIG.name + ".bak"))
            config.setdefault("mcpServers", {})[MCP_NAME] = mcp_command()
            _write_json(DESKTOP_CONFIG, config)
    if c := codex():
        found = True
        if ask("Connect it to Codex?", yes):
            ok = connect_codex(c)
            done("Codex: connected") if ok else note("Codex: failed; see the README to add it by hand")
    if not found:
        note("Neither Claude Code nor Codex found. Install one, then run this again;")
        note("or add an API key above so the MOODscroll app writes notes by itself.")
    else:
        note("Quit and reopen Claude / ChatGPT (⌘Q) so they load it.")


def connect_codex(binary: str) -> bool:
    subprocess.run([binary, "mcp", "remove", MCP_NAME], capture_output=True)
    cmd = mcp_command()
    r = subprocess.run([binary, "mcp", "add", MCP_NAME, "--", cmd["command"], *cmd["args"]],
                       capture_output=True, text=True)
    if r.returncode != 0 or not CODEX_CONFIG.exists():
        return False
    # Give it time to finish long videos: add the timeouts under its table.
    header = f"[mcp_servers.{MCP_NAME}]\n"
    text = CODEX_CONFIG.read_text()
    if header in text and "tool_timeout_sec" not in text.split(header, 1)[1].split("\n[", 1)[0]:
        CODEX_CONFIG.write_text(text.replace(header, header + CODEX_TIMEOUTS, 1))
    return True


def uninstall() -> None:
    say("Uninstalling MOODscroll")
    if APP.exists():
        shutil.rmtree(APP)
        done(f"removed {APP}")
    if c := claude():
        subprocess.run([c, "mcp", "remove", MCP_NAME, "--scope", "user"], capture_output=True)
        done("disconnected from Claude Code")
    if c := codex():
        subprocess.run([c, "mcp", "remove", MCP_NAME], capture_output=True)
        done("disconnected from Codex")
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
    p.add_argument("--uninstall", action="store_true", help="remove the app and the Claude Code / Codex connections")
    args = p.parse_args()
    if args.uninstall:
        uninstall()
        return
    try:
        whisper_model()
        ocr_helper()
        mac_app(args.yes)
        connect_assistants(args.yes)
        api_key(args.yes)
    except KeyboardInterrupt:
        sys.exit("\nStopped. Run moodscroll-setup again any time; it picks up where it left off.")
    say("All set.")
    print("  Open MOODscroll: ⌘ Space, type MOODscroll, Return.")
    print('  In Claude Code or Codex, say: "make notes from <a link>", or after adding videos')
    print(f'  in the app: "{ASK_PHRASE}".')
    note(f"Your notes are saved in {library.DEFAULT_ROOT}")


if __name__ == "__main__":
    main()
