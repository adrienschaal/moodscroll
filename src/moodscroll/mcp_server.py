"""moodscroll as an MCP server, so Claude Desktop or Claude Code can use it directly.

In this mode moodscroll never calls the Claude API. It does the local work and hands
Claude the transcript, on-screen text and key frames; Claude writes the notes in
the conversation (on the user's own Claude plan) and saves them back with
save_notes. No API key needed.

    claude mcp add moodscroll -- uv --directory /path/to/moodscroll run moodscroll-mcp
"""

from __future__ import annotations

import json

import anyio
from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import library, pipeline
from .media import subsample
from .notes import CATEGORIES, SYSTEM, Notes, build_prompt

FRAMES_FOR_CLAUDE = 4

server = MCPServer(
    name="moodscroll",
    instructions=f"""moodscroll turns videos (Instagram, TikTok, YouTube, local files) into notes.
To make notes: call process_video, read what it returns, then call save_notes with
notes you write yourself. {SYSTEM}
Categories: {", ".join(CATEGORIES)}.
To find something the user saved before: search_notes, then read_note.""",
)


@server.tool(
    annotations=ToolAnnotations(title="Process a video", readOnlyHint=False, openWorldHint=True),
    structured_output=False,
)
async def process_video(source: str, ctx: Context) -> list:
    """Download (if a link) and analyse a video on this Mac: speech transcript,
    on-screen text, key frames. Takes ~20 s per minute of video. Returns the
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
            lambda: pipeline.extract(source, library.DEFAULT_ROOT, progress=progress))
    except Exception as e:  # tell Claude what went wrong instead of a bare crash
        raise ToolError(f"could not process {source}: {e}") from e

    d = pipeline.load(folder)
    text = (f"folder: {folder.name}\n\n"
            + build_prompt(d["meta"], d["transcript"], d["ocr"])
            + "\n\nNow write the notes and call save_notes with this folder name.")
    images = [Image(path=folder / "frames" / f["file"])
              for f in subsample(d["frames"], FRAMES_FOR_CLAUDE)]
    return [text, *images]


def _folder(name: str):
    try:
        return library.resolve_folder(name)
    except ValueError as e:
        raise ToolError(str(e)) from e


@server.tool(annotations=ToolAnnotations(title="Save notes", readOnlyHint=False, idempotentHint=True))
def save_notes(folder: str, notes: Notes) -> str:
    """Save the notes you wrote for a processed video. Renders note.md and renames
    the folder after the notes' title. Returns the note's path."""
    out = pipeline.add_notes(_folder(folder), notes, usage={"model": "via MCP"})
    return str(out / "note.md")


@server.tool(annotations=ToolAnnotations(title="Search saved videos", readOnlyHint=True))
def search_notes(query: str, limit: int = 10) -> str:
    """Search every processed video (titles, tags, summaries, transcripts,
    on-screen text). Returns the best matches with their folder names."""
    return json.dumps(library.search(query, limit=limit), ensure_ascii=False, indent=2)


@server.tool(annotations=ToolAnnotations(title="Read a note", readOnlyHint=True))
def read_note(folder: str) -> str:
    """Return the full note (Markdown) for a folder name from search_notes."""
    return (_folder(folder) / "note.md").read_text()


def main() -> None:
    server.run()  # stdio: Claude starts this process and talks to it over stdin/stdout


if __name__ == "__main__":
    main()
