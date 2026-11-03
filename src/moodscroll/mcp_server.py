"""MOODscroll as an MCP server, so Claude Code or Codex can use it directly.

In this mode MOODscroll never calls an AI API. It does the local work (download,
transcript, on-screen text, key frames) and hands the assistant the material; the
assistant writes the notes in the chat, on the user's own subscription, and saves
them back with save_notes. Everything lands in the same library the MOODscroll app
shows. No API key needed.

    claude mcp add moodscroll -- uv --directory /path/to/moodscroll run moodscroll-mcp
    codex mcp add moodscroll -- uv --directory /path/to/moodscroll run moodscroll-mcp
"""

from __future__ import annotations

import json

import anyio
from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import library, pipeline
from .media import subsample
from .notes import ASK_PHRASE, CATEGORIES, SYSTEM, Notes, build_prompt

FRAMES_FOR_NOTES = 4

server = MCPServer(
    name="moodscroll",
    instructions=f"""MOODscroll turns videos (Instagram, TikTok, YouTube, local files) into notes,
saved in a library the user browses in the MOODscroll app.
- To make notes from a link or file: call process_video, read what it returns (text
  and key frames), write the notes yourself, then call save_notes.
- When the user asks you to "{ASK_PHRASE}" (or catch up, or similar): call
  list_waiting, then for each video call get_video and save_notes. Videos wait when
  they were added in the app without an API key.
- To find something saved before: search_notes, then read_note.
After saving, tell the user the note's title; it is already in the MOODscroll app.
How to write the notes: {SYSTEM}
Categories: {", ".join(CATEGORIES)}.""",
)


def _folder(name: str):
    try:
        return library.resolve_folder(name)
    except ValueError as e:
        raise ToolError(str(e)) from e


def _material(folder) -> list:
    """Everything needed to write a video's notes: the text, then 4 key frames."""
    d = pipeline.load(folder)
    text = (f"folder: {folder.name}\n\n"
            + build_prompt(d["meta"], d["transcript"], d["ocr"])
            + "\n\nNow write the notes and call save_notes with this folder name.")
    images = [Image(path=folder / "frames" / f["file"])
              for f in subsample(d["frames"], FRAMES_FOR_NOTES)]
    return [text, *images]


@server.tool(
    annotations=ToolAnnotations(title="Process a video", readOnlyHint=False, openWorldHint=True),
    structured_output=False,
)
async def process_video(source: str, ctx: Context) -> list:
    """MOODscroll: use when the user shares a video link or file and wants notes,
    a summary or to save it. Downloads (if a link) and analyses the video on this
    Mac: speech transcript, on-screen text, key frames. Takes ~30 s per minute of video. Returns the
    material plus a folder name; then write notes and call save_notes with it.

    source: a URL (Instagram, TikTok, YouTube, ...) or a local file path.
    """
    steps = ["fetching", "transcribing", "finding key frames", "reading on-screen text"]

    def progress(message: str) -> None:
        # Called from the worker thread; hop back to the event loop to report.
        done = steps.index(message.rstrip(".")) if message.rstrip(".") in steps else 0
        anyio.from_thread.run(ctx.report_progress, done, len(steps), message)

    try:
        folder = await anyio.to_thread.run_sync(
            lambda: pipeline.extract(source, library.DEFAULT_ROOT, keep_video=True, progress=progress))
    except Exception as e:  # tell the assistant what went wrong instead of a bare crash
        raise ToolError(f"could not process {source}: {e}") from e
    return _material(folder)


@server.tool(annotations=ToolAnnotations(title="List videos waiting for notes", readOnlyHint=True))
def list_waiting() -> str:
    """MOODscroll: use when the user says "finish my MOODscroll notes" (or asks to
    catch up on, finish or write their MOODscroll notes). Lists the videos added in
    the MOODscroll app that have no notes yet, oldest first. For each one, call
    get_video, write the notes, then call save_notes. No files to look for: these
    tools are the whole job."""
    items = [{k: v for k, v in s.items() if k in ("folder", "title", "author", "source", "duration_s")}
             for s in library.waiting()]
    return json.dumps(items, ensure_ascii=False, indent=2) if items else "Nothing is waiting for notes."


@server.tool(
    annotations=ToolAnnotations(title="Get a video's material", readOnlyHint=True),
    structured_output=False,
)
def get_video(folder: str) -> list:
    """The transcript, on-screen text and 4 key frames of a video already in the
    library, to write (or rewrite) its notes. Then call save_notes."""
    return _material(_folder(folder))


@server.tool(annotations=ToolAnnotations(title="Save notes", readOnlyHint=False, idempotentHint=True))
def save_notes(folder: str, notes: Notes) -> str:
    """Save the notes you wrote for a video. Renders note.md, renames the folder
    after the notes' title, and makes it show up in the MOODscroll app. Returns the
    note's path."""
    out = pipeline.add_notes(_folder(folder), notes, usage={"model": "via MCP"})
    return str(out / "note.md")


@server.tool(annotations=ToolAnnotations(title="Search saved videos", readOnlyHint=True))
def search_notes(query: str, limit: int = 10) -> str:
    """MOODscroll: search every saved video (titles, tags, summaries, transcripts, on-screen
    text). Returns the best matches with their folder names."""
    return json.dumps(library.search(query, limit=limit), ensure_ascii=False, indent=2)


@server.tool(annotations=ToolAnnotations(title="Read a note", readOnlyHint=True))
def read_note(folder: str) -> str:
    """Return the full note (Markdown) for a folder name from search_notes."""
    return (_folder(folder) / "note.md").read_text()


def main() -> None:
    server.run()  # stdio: the assistant starts this process and talks over stdin/stdout


if __name__ == "__main__":
    main()
