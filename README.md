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

## Two ways to run it

| | Who writes the notes | Pays | Good for |
|---|---|---|---|
| **MCP server** in Claude Desktop or Claude Code | Claude, in your conversation | your Claude plan, no API key | asking Claude "make notes from this reel", "find that pasta recipe I saved" |
| **Command line** | vnotes, through the Claude API | API key, a few cents a video | batches, scripts, running unattended |

Either way, add `--no-notes` (CLI) or skip `save_notes` (MCP) and nothing leaves your Mac.

## Install

Requires macOS on Apple Silicon, [uv](https://docs.astral.sh/uv/) and ffmpeg.

```bash
brew install uv ffmpeg
git clone https://github.com/adrienschaal/vnotes && cd vnotes
uv sync
```

**As an MCP server** (Claude Code; for Claude Desktop add the same command under
`mcpServers` in its config):

```bash
claude mcp add vnotes --scope user -- uv --directory "$PWD" run vnotes-mcp
```

Tools: `process_video` (returns transcript, on-screen text and 4 key frames as images),
`save_notes`, `search_notes`, `read_note`.

**From the command line:**

```bash
export ANTHROPIC_API_KEY=…   # from platform.claude.com; optional with --no-notes
uv run vnotes <link-or-file> [more ...]
```

Notes land in `~/vnotes/<date>-<title>/` (change with `-o` or `VNOTES_DIR`).

## Status

Early. Next: a local web app (drag and drop, live progress, library search).

Download only what you have the right to keep; respect each platform's terms.
