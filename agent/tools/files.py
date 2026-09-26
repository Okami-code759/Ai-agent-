"""File tools. Everything is sandboxed to the agent's workspace folder."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from . import ToolError, tool

MAX_READ_CHARS = 60_000
BLOCKED = {".git", ".env"}  # never readable or writable by the agent


def resolve(ctx, path: str) -> Path:
    root = ctx.workspace
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ToolError(f"'{path}' is outside the workspace ({root}).")
    if BLOCKED & set(target.relative_to(root).parts):
        raise ToolError(f"Access to '{path}' is blocked for safety.")
    return target


def _visible(ctx, p: Path) -> bool:
    return not (BLOCKED & set(p.relative_to(ctx.workspace).parts))


@tool(
    "list_dir",
    "List files and folders in the workspace. Use '.' for the workspace root.",
    {
        "path": {"type": "string", "description": "Relative folder path"},
        "recursive": {"type": "boolean", "description": "Include nested files (default false)"},
    },
    required=["path"],
    ci=True,
)
def list_dir(ctx, path: str = ".", recursive: bool = False) -> str:
    base = resolve(ctx, path)
    if not base.is_dir():
        raise ToolError(f"Not a folder: {path}")
    items = base.rglob("*") if recursive else base.iterdir()
    lines = []
    for p in sorted(items):
        if not _visible(ctx, p):
            continue
        rel = p.relative_to(ctx.workspace)
        lines.append(f"{rel}/" if p.is_dir() else f"{rel}  ({p.stat().st_size} bytes)")
        if len(lines) >= 500:
            lines.append("... (truncated at 500 entries)")
            break
    return "\n".join(lines) or "(empty folder)"


@tool(
    "read_file",
    "Read a text file from the workspace, optionally only a range of lines.",
    {
        "path": {"type": "string"},
        "start_line": {"type": "integer", "description": "First line to read (1-based)"},
        "end_line": {"type": "integer", "description": "Last line to read (inclusive)"},
    },
    required=["path"],
    ci=True,
)
def read_file(ctx, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    target = resolve(ctx, path)
    if not target.is_file():
        raise ToolError(f"File not found: {path}")
    text = target.read_text(encoding="utf-8", errors="replace")
    if start_line or end_line:
        lines = text.splitlines()
        start = max((start_line or 1) - 1, 0)
        end = end_line or len(lines)
        text = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines[start:end], start))
    if len(text) > MAX_READ_CHARS:
        text = text[:MAX_READ_CHARS] + "\n... (truncated; read a line range to see more)"
    return text or "(empty file)"


@tool(
    "write_file",
    "Create or overwrite a file in the workspace. Parent folders are created automatically.",
    {"path": {"type": "string"}, "content": {"type": "string"}},
)
def write_file(ctx, path: str, content: str) -> str:
    target = resolve(ctx, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    target.write_text(content, encoding="utf-8")
    return f"{'Overwrote' if existed else 'Created'} {path} ({len(content)} chars)."


@tool(
    "edit_file",
    "Replace an exact snippet of text in a file. old_text must appear exactly once.",
    {
        "path": {"type": "string"},
        "old_text": {"type": "string", "description": "Exact text to find"},
        "new_text": {"type": "string", "description": "Replacement text"},
    },
)
def edit_file(ctx, path: str, old_text: str, new_text: str) -> str:
    target = resolve(ctx, path)
    if not target.is_file():
        raise ToolError(f"File not found: {path}")
    text = target.read_text(encoding="utf-8")
    count = text.count(old_text)
    if count != 1:
        raise ToolError(f"old_text found {count} times; it must match exactly once. Include more context.")
    target.write_text(text.replace(old_text, new_text), encoding="utf-8")
    return f"Edited {path}."


@tool(
    "search_files",
    "Search file contents in the workspace with a regular expression (like grep).",
    {
        "pattern": {"type": "string", "description": "Regular expression"},
        "path": {"type": "string", "description": "Folder to search (default '.')"},
        "file_glob": {"type": "string", "description": "Only search matching files, e.g. '*.py'"},
    },
    required=["pattern"],
    ci=True,
)
def search_files(ctx, pattern: str, path: str = ".", file_glob: str = "*") -> str:
    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise ToolError(f"Invalid regex: {e}")
    base = resolve(ctx, path)
    hits = []
    for p in base.rglob("*"):
        if not p.is_file() or not _visible(ctx, p) or not fnmatch.fnmatch(p.name, file_glob):
            continue
        try:
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{p.relative_to(ctx.workspace)}:{n}: {line.strip()[:200]}")
        except (UnicodeDecodeError, OSError):
            continue  # skip binary / unreadable files
        if len(hits) >= 200:
            hits.append("... (truncated at 200 matches)")
            break
    return "\n".join(hits) or "No matches."


@tool(
    "delete_file",
    "Delete a file or an empty folder from the workspace.",
    {"path": {"type": "string"}},
    confirm=True,
)
def delete_file(ctx, path: str) -> str:
    target = resolve(ctx, path)
    if target == ctx.workspace:
        raise ToolError("Refusing to delete the workspace root.")
    if target.is_dir():
        target.rmdir()
    elif target.exists():
        target.unlink()
    else:
        raise ToolError(f"Not found: {path}")
    return f"Deleted {path}."
