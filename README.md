# vnotes

Turn any video into notes you'll actually reread. Paste a link or drop a file;
get back a Markdown note with a summary, the key points, exact quantities and
steps, claims worth checking, key frames, the on-screen text and a timestamped
transcript.

```bash
vnotes "https://www.instagram.com/reel/…"   # or TikTok, YouTube, a local .mp4/.mov
```

## How it works

| Step | Runs | Tool |
|---|---|---|
| Fetch | network | [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Instagram's public embed page as a fallback), or your local file |
| Speech to text | **on your Mac** | Whisper large-v3-turbo on Apple Silicon via [mlx-whisper](https://github.com/ml-explore/mlx-examples) |
| Key frames | **on your Mac** | ffmpeg, one frame per scene change (at least every 8 s) |
| On-screen text | **on your Mac** | Apple Vision OCR |
| Notes | Claude API | transcript + on-screen text + caption + 4 frames → structured notes |

Only the last step leaves your machine, and `--no-notes` skips it.

Whisper makes up text over background music. vnotes drops segments that repeat,
that the model scored as very unlikely (real speech averages about -0.1 log-probability,
invented lines about -5), or that start after the video ends.

## Install

Requires macOS on Apple Silicon, [uv](https://docs.astral.sh/uv/) and ffmpeg.

```bash
brew install uv ffmpeg
git clone https://github.com/adrienschaal/vnotes && cd vnotes
uv sync
export ANTHROPIC_API_KEY=…   # from console.anthropic.com; optional with --no-notes
uv run vnotes <link-or-file>
```

Notes land in `~/vnotes/<date>-<title>/` (change with `-o` or `VNOTES_DIR`).

## Status

Early. Planned: a local web app (drag and drop, library search) and an MCP server
so Claude can search your saved videos.

Download only what you have the right to keep; respect each platform's terms.
