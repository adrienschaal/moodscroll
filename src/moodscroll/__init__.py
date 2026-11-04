"""MooDscroll: turn the videos you saved into notes you'll actually reread."""

import os
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "moodscroll"
KEY_FILE = CONFIG_DIR / ".env"

# Apps started from the Dock, Spotlight or Claude don't get the shell's PATH, so
# Homebrew's ffmpeg would be invisible. Add its usual homes once, here.
_path = os.environ.get("PATH", "").split(os.pathsep)
for _dir in ("/opt/homebrew/bin", "/usr/local/bin"):
    if _dir not in _path:
        _path.append(_dir)
os.environ["PATH"] = os.pathsep.join(_path)

# The Claude API key lives in a private file, never in the code. Real environment
# variables win over the file.
load_dotenv(KEY_FILE)
load_dotenv(Path.cwd() / ".env")
