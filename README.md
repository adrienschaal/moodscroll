# MOODscroll

**Turn the videos you saved into notes you'll actually reread.**

Paste an Instagram, TikTok or YouTube link, or drop in a video file. MOODscroll
transcribes it on your Mac, reads the text on screen, picks the key frames, and writes
a note: a summary, the key points, the exact quantities and steps, and the claims worth
checking. The transcript is kept too. Every note goes into one library you can search,
and clicking any line of the transcript jumps the video to that moment.

It runs on your Mac. Nothing is hosted, there's no account, and your library is just a
folder of Markdown files.

---

## Install (about 5 minutes)

You need a Mac with Apple Silicon (M1 or later) and [Homebrew](https://brew.sh).
Open **Terminal** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/adrienschaal/moodscroll/main/install.sh | bash
```

The installer tells you what each step is for and asks before the optional ones. It:

1. Installs `uv` (manages Python for you) and `ffmpeg` (reads video) through Homebrew,
   if you don't already have them.
2. Downloads MOODscroll to `~/.local/share/moodscroll`.
3. Downloads the speech-to-text model (about 1.6 GB, one time only).
4. Asks for a Claude API key. You can skip this step; see "Which way should I use it?"
   below.
5. Adds **MOODscroll** to your Applications folder.
6. Offers to connect MOODscroll to Claude Code and the Claude desktop app.

If Apple's Command Line Tools are missing, the installer opens Apple's own installer
for them. Run MOODscroll's installer again once that finishes.

You can run the installer as often as you like. It skips whatever is already done, and
it updates MOODscroll to the latest version.

## Use it

Open **MOODscroll**: press ⌘ Space, type `MOODscroll`, then press Return. It opens in
your browser at `http://127.0.0.1:8765`, an address that works only on your own Mac.

- **Paste a link** and click **Make notes**. Or drag a video file (mp4, mov, m4v, webm,
  mkv) onto the box.
- You can watch each step as it runs. A one-minute video takes about 30 seconds.
- **Open a note** to read it next to the video. Click any transcript line, key frame or
  piece of on-screen text to jump the video to that moment.
- **Search** at the top looks through every note's title, summary, key points,
  transcript and on-screen text.
- **Copy Markdown** puts the whole note on your clipboard, ready to paste into Notes,
  Obsidian or Notion.
- To stop MOODscroll, click **Quit MOODscroll** at the bottom of the page.

To keep it in your Dock, open it once, then drag MOODscroll from Applications onto the
Dock.

## Which way should I use it?

There are three ways to use MOODscroll. All three run the same engine and save to the
same library. What differs is who writes the notes:

| | Who writes the notes | What it costs | Best for |
|---|---|---|---|
| **The app** | MOODscroll, through the Claude API | your API key, about $0.04 a video | dropping videos in and reading notes beside them |
| **Inside Claude** (desktop app or Claude Code) | Claude, in your chat | your Claude plan covers it, no key needed | "make notes from this reel", "find that pasta recipe I saved" |
| **Command line** | MOODscroll, through the Claude API | your API key | lots of videos at once, or scripts |

**No API key?** The app and the command line still do the transcript, the frames and the
on-screen text. Only the written notes need a key. You can get one at
[platform.claude.com](https://platform.claude.com/settings/keys). Claude Pro and Max
subscriptions don't include API credit, and $5 covers more than 100 videos. Then run the
setup again to add the key:

```bash
cd ~/.local/share/moodscroll && uv run moodscroll-setup
```

The key is saved in `~/.config/moodscroll/.env`, and only your user account can read
that file.

### Inside Claude

If you let the installer connect it, quit Claude completely (⌘Q) and open it again.
Then ask:

> Make notes from https://www.instagram.com/reel/…
>
> What was that BBQ pizza recipe I saved?

Claude has your Mac download the video, transcribe it and read the on-screen text.
Then Claude writes the note itself and saves it to your library, so you'll find it in
the app afterwards.

### Command line

```bash
cd ~/.local/share/moodscroll
uv run moodscroll "https://www.instagram.com/reel/…" another.mp4
```

| Option | What it does |
|---|---|
| `-o FOLDER` | save the notes somewhere other than `~/Moodscroll` |
| `--no-notes` | skip the Claude step, so nothing leaves your Mac after the download |
| `--keep-video` | keep the downloaded video next to the note |

## Where your notes live

Each video gets its own folder in `~/Moodscroll/`, for example
`2026-11-03-meal-prep-bbq-chicken-baguette-pizzas/`. Each folder holds:

- `note.md`, the note in plain Markdown, which any app can open
- `frames/`, the key frames
- `transcript.json`, `ocr.json`, `notes.json` and `meta.json`, the raw material the
  note was built from
- the video itself, if you added a file or used `--keep-video`

To keep the library somewhere else, set `MOODSCROLL_DIR=/path/to/folder`.

## What it does, and where

| Step | Where it runs | How |
|---|---|---|
| Download | the internet | [yt-dlp](https://github.com/yt-dlp/yt-dlp), with Instagram's public embed page as a fallback. Or your own file. |
| Speech to text | **your Mac** | Whisper large-v3-turbo on Apple Silicon ([mlx-whisper](https://github.com/ml-explore/mlx-examples)) |
| Key frames | **your Mac** | ffmpeg: one frame at each scene change, and at least one every 8 seconds |
| On-screen text | **your Mac** | Apple Vision, the same text recognition that Photos uses |
| The written note | Claude | gets the transcript, the on-screen text, the caption and 4 frames |

**What leaves your Mac:** the last step sends the transcript, the on-screen text, the
caption and four frames to Claude. They go through your API key, or through your Claude
chat if you use MOODscroll inside Claude. The video itself is never uploaded. With
`--no-notes`, nothing leaves your Mac after the download.

**Why the transcripts can be trusted:** Whisper tends to make up sentences over
background music. MOODscroll drops a segment when:

- it repeats itself
- the model rated it very unlikely (real speech scores about −0.1 log-probability,
  invented lines about −5)
- it is timed after the video ends

## Troubleshooting

| Problem | Fix |
|---|---|
| The app opens a page that won't load | Wait a few seconds and reload. The first start is the slowest. If it still won't load, check `~/Library/Logs/MOODscroll.log`. |
| "Address already in use" | MOODscroll is already running. Open `http://127.0.0.1:8765`, or click **Quit MOODscroll** there and open the app again. |
| A link won't download | The video may be private or deleted, or the creator may have turned off embedding. Save the video with the platform's own download button, then drop the file in. |
| Notes say there's no API key | Add one with `uv run moodscroll-setup` (see above), or use MOODscroll inside Claude instead. |
| Claude doesn't see MOODscroll | Quit Claude with ⌘Q (closing the window isn't enough), then reopen it. |
| Anything else | Run the installer again. It fixes whatever is missing. |

## Uninstall

```bash
cd ~/.local/share/moodscroll && uv run moodscroll-setup --uninstall
```

This removes the app and disconnects MOODscroll from Claude. Your notes
(`~/Moodscroll`) and your key (`~/.config/moodscroll`) stay where they are. To remove
everything else as well:

```bash
rm -rf ~/.local/share/moodscroll ~/.config/moodscroll ~/.cache/moodscroll
```

## For developers

```bash
git clone https://github.com/adrienschaal/moodscroll && cd moodscroll
./install.sh          # sets up this clone instead of downloading another
uv run pytest
```

Where things are:

- `pipeline.py` runs the steps.
- `sources.py` downloads the video.
- `media.py` handles Whisper, ffmpeg and OCR.
- `notes.py` holds the Claude prompt and the note schema.
- `render.py` turns a note into Markdown.
- `library.py` handles search.
- The front ends:
  - `web.py` and `static/` are the app: a FastAPI server bound to 127.0.0.1 that
    refuses requests from other websites.
  - `mcp_server.py` is the Claude connection.
  - `cli.py` is the command line.
  - `setup_mac.py` is the second half of the installer.

Environment variables:

| Variable | Sets | Default |
|---|---|---|
| `MOODSCROLL_DIR` | where the library lives | `~/Moodscroll` |
| `MOODSCROLL_MODEL` | the Claude model | `claude-opus-5-5` |
| `MOODSCROLL_EFFORT` | how hard Claude works on each note | `medium` |
| `MOODSCROLL_WHISPER_MODEL` | the speech-to-text model | Whisper large-v3-turbo |

---

Download only what you have the right to keep, and respect each platform's terms.

MIT License · © 2026 Adrien Schaal · Made in Cambridge, MA.
