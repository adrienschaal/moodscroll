"""vnotes <file-or-link> — turn a video into notes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import library, pipeline, sources

# The API key lives in a private file, never in the code: ./.env when run from the
# repo, or ~/.config/vnotes/.env when installed. Real environment variables win.
load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.home() / ".config" / "vnotes" / ".env")

DEFAULT_OUT = library.DEFAULT_ROOT


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vnotes", description="Turn a video into notes, locally.")
    p.add_argument("source", nargs="+", help="video file(s) or link(s): Instagram, TikTok, YouTube...")
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT, help=f"output folder (default {DEFAULT_OUT})")
    p.add_argument("--no-notes", action="store_true", help="skip the Claude step; stay fully offline after download")
    p.add_argument("--keep-video", action="store_true", help="keep downloaded videos next to the notes")
    args = p.parse_args(argv)

    failed = 0
    for src in args.source:
        print(f"\n▶ {src}")
        try:
            out = pipeline.run(src, args.out, with_notes=not args.no_notes,
                               keep_video=args.keep_video, progress=lambda m: print(f"  {m}"))
            print(f"  ✓ {out / 'note.md'}")
        except sources.SourceError as e:
            failed += 1
            print(f"  ✗ {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
