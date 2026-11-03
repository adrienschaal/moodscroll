# MOODscroll

**Turn the videos you saved into notes you'll actually reread.**

Paste an Instagram, TikTok or YouTube link, or drop in a video file. MOODscroll
transcribes it on your Mac, reads the text on screen and picks the key frames. Then
Claude Code or Codex writes the note: a summary, the key points, the exact quantities
and steps, and the claims worth checking. Every note goes into one library you can
search, and clicking any line of the transcript jumps the video to that moment.

It runs on your Mac. There's no account and no server, and your library is a folder of
Markdown files.

---

## How it works

```
  MOODscroll app                           Claude Code or Codex
  ──────────────                           ────────────────────
  paste links, drop videos                 "make notes from <link>"
  read notes next to the video             "finish my MOODscroll notes"
  search everything                        "what was that pizza recipe I saved?"
            │                                         │
            └──────────►  ~/Moodscroll  ◄─────────────┘
                      one library, shared
```

- **The MOODscroll app** is where your library lives. You add videos, read the notes
  beside the video and search them.
- **Claude Code or Codex** writes the notes, on the subscription you already pay for.
  You don't need an API key.

Two ways to add a video:

1. **In Claude Code or Codex:** say *"make notes from https://…"*. The note appears in
   the app.
2. **In the app:** paste a link or drop a file. MOODscroll does the transcript and the
   frames right away, and the video shows **Waiting for notes**. Whenever you like, tell
   Claude Code or Codex *"finish my MOODscroll notes"*. It writes the note for every
   waiting video, and the app fills in by itself.

**Prefer the app to write the notes by itself?** Click **Use a Claude API key** in
the app and paste a key from [platform.claude.com](https://platform.claude.com/settings/keys).
After that, videos you add in the app get their notes in about 30 seconds, for about
$0.04 a video, and any videos already waiting get a **Write them now** button.

**Switch to Claude Code / Codex** turns the key off again without deleting it, so you
can switch back with one click. API credit is billed separately from a Claude
subscription, and $5 covers more than 100 videos. All of this is optional: everything
else works without a key.

The key is checked with Anthropic, then saved only on your Mac, in
`~/.config/moodscroll/.env`, which only your user account can read. It is never shown
again or sent anywhere else.

## Install (about 5 minutes)

You need:

- a Mac with Apple Silicon (M1 or later)
- [Homebrew](https://brew.sh)
- [Claude Code](https://claude.com/claude-code) or Codex (the Codex app or the Codex
  CLI), signed in

Open **Terminal** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/adrienschaal/moodscroll/main/install.sh | bash
```

The installer explains each step and asks before the optional ones:

1. It installs `uv` (manages Python for you) and `ffmpeg` (reads video) through
   Homebrew, if you don't have them yet.
2. It downloads MOODscroll to `~/.local/share/moodscroll`.
3. It downloads the speech-to-text model (about 1.6 GB, one time only).
4. It adds **MOODscroll** to your Applications folder.
5. It connects MOODscroll to Claude Code and Codex, whichever you have.
6. It offers to add a Claude API key. You can skip this and add one later in the app.

**Then quit Claude Code or Codex completely (⌘Q) and reopen it**, so it loads
MOODscroll.

If Apple's Command Line Tools are missing, the installer opens Apple's installer for
them. Run MOODscroll's installer again once that finishes. You can run it as often as
you like: it skips whatever is already done and updates MOODscroll to the latest version.

## Use it

### The app

Open **MOODscroll**: press ⌘ Space, type `MOODscroll`, then press Return. It opens in
your browser at `http://127.0.0.1:8765`, an address that works only on your own Mac.

- **Paste a link** and click **Make notes**. Or drag a video file (mp4, mov, m4v, webm,
  mkv) onto the box.
- **Open a note** to read it next to the video. Click any transcript line, key frame or
  piece of on-screen text to jump the video to that moment.
- **Search** at the top looks through every note's title, summary, key points,
  transcript and on-screen text.
- **Copy Markdown** puts the whole note on your clipboard, ready to paste into Notes,
  Obsidian or Notion.
- **Quit MOODscroll** at the bottom of the page stops it.

To keep MOODscroll in your Dock, open it once, then drag it from Applications onto the
Dock.

### Claude Code and Codex

Talk to it the way you'd talk to a person:

| Say | What happens |
|---|---|
| *make notes from https://www.instagram.com/reel/…* | MOODscroll processes the video on your Mac, then the assistant writes and saves the note |
| *finish my MOODscroll notes* | notes for every video waiting in the app |
| *what was that BBQ pizza recipe I saved?* | searches your library and reads you the note |
| *redo the notes for the gnocchi video, shorter* | rewrites a note you already have |

**Codex asks before it saves a note.** That's normal for any tool that writes files.
Approve it. The tools only write inside your `~/Moodscroll` library.

If you use the Claude desktop app's chat, the installer connects it too.

### Command line (optional)

```bash
cd ~/.local/share/moodscroll
uv run moodscroll "https://www.instagram.com/reel/…" another.mp4
```

| Option | What it does |
|---|---|
| `-o FOLDER` | saves somewhere other than `~/Moodscroll` |
| `--no-notes` | skips the notes, so nothing leaves your Mac after the download |
| `--keep-video` | keeps the downloaded video next to the note |

Without an API key, the videos are left waiting for Claude Code or Codex, just as in
the app.

## Where your notes live

Each video gets its own folder in `~/Moodscroll/`, for example
`2026-11-03-meal-prep-bbq-chicken-baguette-pizzas/`. Each folder holds:

- `note.md`, the note in plain Markdown, which any app can open
- `frames/`, the key frames
- `transcript.json`, `ocr.json`, `notes.json` and `meta.json`, the raw material the
  note was built from
- the video itself, if you added a file or used `--keep-video`

To keep the library somewhere else, set `MOODSCROLL_DIR=/path/to/folder`.

## What runs where

| Step | Where | How |
|---|---|---|
| Download | the internet | [yt-dlp](https://github.com/yt-dlp/yt-dlp), with Instagram's public embed page as a fallback. Or your own file. |
| Speech to text | **your Mac** | Whisper large-v3-turbo on Apple Silicon ([mlx-whisper](https://github.com/ml-explore/mlx-examples)) |
| Key frames | **your Mac** | ffmpeg: one frame at each scene change, and at least one every 8 seconds |
| On-screen text | **your Mac** | Apple Vision, the same text recognition Photos uses |
| The written note | Claude Code, Codex, or the Claude API | gets the transcript, on-screen text, caption and 4 frames |

**What leaves your Mac:** only the last step. It sends the transcript, the on-screen
text, the caption and four frames, either to the assistant you're chatting with or to
the Claude API if you added a key. The video itself is never uploaded.

**Why the transcripts hold up:** Whisper tends to invent sentences over background
music. MOODscroll drops a segment when:

- it repeats itself
- the model rated it very unlikely (real speech scores about −0.1 log-probability,
  invented lines about −5)
- it is timed after the video ends

## Troubleshooting

| Problem | Fix |
|---|---|
| Claude Code or Codex doesn't know about MOODscroll | Quit it with ⌘Q (closing the window isn't enough), then reopen it. In Claude Code, `/mcp` should list `moodscroll`. In Codex, run `codex mcp list`. |
| It looks for files instead of using MOODscroll | Mention MOODscroll by name, as in *"finish my MOODscroll notes"* or *"use MOODscroll to make notes from …"*. |
| The app opens a page that won't load | Wait a few seconds and reload, since the first start is the slowest. If it still won't load, check `~/Library/Logs/MOODscroll.log`. |
| "Address already in use" | MOODscroll is already running. Open `http://127.0.0.1:8765`, or click **Quit MOODscroll** there and open the app again. |
| A link won't download | The video may be private or deleted, or the creator may have turned off embedding. Save it with the platform's own download button, then drop the file in. |
| Notes failed with an API error | Check your key and credit at platform.claude.com. The video stays waiting: click **Write them now** to retry, or say *"finish my MOODscroll notes"* in Claude Code or Codex. |
| A note looks out of date, or a fix doesn't show | After updating MOODscroll, quit Claude Code or Codex (⌘Q) and reopen it. They keep running the version that was there when they started. |
| Anything else | Run the installer again. It repairs whatever is missing. |

## Uninstall

```bash
cd ~/.local/share/moodscroll && uv run moodscroll-setup --uninstall
```

This removes the app and disconnects MOODscroll from Claude Code and Codex. Your notes
(`~/Moodscroll`) and your key (`~/.config/moodscroll`) stay. To remove everything else:

```bash
rm -rf ~/.local/share/moodscroll ~/.config/moodscroll ~/.cache/moodscroll
```

## For developers

```bash
git clone https://github.com/adrienschaal/moodscroll && cd moodscroll
./install.sh          # sets up this clone instead of downloading another
uv run pytest
```

| File | What it does |
|---|---|
| `pipeline.py` | runs the steps |
| `sources.py` | downloads the video |
| `media.py` | Whisper, ffmpeg and OCR |
| `notes.py` | the note schema, the prompt, and the optional API call |
| `render.py` | turns a note into Markdown |
| `library.py` | search, and the list of videos waiting for notes |
| `keys.py` | the optional API key: check, save, switch off and on |
| `web.py`, `static/` | the app: a FastAPI server bound to 127.0.0.1 that refuses requests from other websites |
| `mcp_server.py` | the Claude Code / Codex connection |
| `cli.py` | the command line |
| `setup_mac.py` | the second half of the installer |

The MCP server has six tools: `process_video`, `list_waiting`, `get_video`,
`save_notes`, `search_notes` and `read_note`. It never calls an AI API itself. The
assistant writes the notes and saves them with `save_notes`.

To connect it by hand:

```bash
claude mcp add moodscroll --scope user -- uv --directory ~/.local/share/moodscroll run moodscroll-mcp
codex mcp add moodscroll -- uv --directory ~/.local/share/moodscroll run moodscroll-mcp
```

For Codex, also add `tool_timeout_sec = 900` under `[mcp_servers.moodscroll]` in
`~/.codex/config.toml`. Codex gives up on a tool after 60 seconds by default, and a long
video takes longer than that.

Environment variables:

| Variable | Sets | Default |
|---|---|---|
| `MOODSCROLL_DIR` | where the library lives | `~/Moodscroll` |
| `MOODSCROLL_MODEL` | the Claude model, when using an API key | `claude-opus-5-5` |
| `MOODSCROLL_EFFORT` | how hard Claude works on each note | `medium` |
| `MOODSCROLL_WHISPER_MODEL` | the speech-to-text model | Whisper large-v3-turbo |

---

Download only what you have the right to keep, and respect each platform's terms.

MIT License · © 2026 Adrien Schaal · Made in Cambridge, MA.
