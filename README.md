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

## Three ways to use it

| | Who writes the notes | Pays | Good for |
|---|---|---|---|
| **Web app** (`vnotes-web`) | vnotes, through the Claude API | API key, ~$0.04 a video | dropping videos in, reading notes beside the video, searching your library |
| **Command line** (`vnotes`) | vnotes, through the Claude API | API key | batches, scripts, running unattended |
| **MCP server** in Claude Desktop or Claude Code | Claude, in your conversation | your Claude plan, no API key | "make notes from this reel", "find that pasta recipe I saved" |

All three share one engine and one library folder.

In MCP mode the transcript, on-screen text and four frames go to Claude as part of your
conversation. With the CLI's `--no-notes`, nothing leaves your Mac after the download.

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

**Web app** (opens http://127.0.0.1:8765, reachable from this Mac only):

```bash
echo "ANTHROPIC_API_KEY=…" > .env   # from platform.claude.com; git-ignored
uv run vnotes-web
```

Paste a link or drop a file, watch each step, then read the note next to the video:
every transcript line, on-screen text and key frame jumps the video to that moment.

**From the command line:**

```bash
uv run vnotes <link-or-file> [more ...]
```

Notes land in `~/vnotes/<date>-<title>/` (change with `-o` or `VNOTES_DIR`).

## Status

Early. Next: reach the Mac from a phone through a Cloudflare Tunnel.

Download only what you have the right to keep; respect each platform's terms.
