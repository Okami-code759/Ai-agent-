"""Persistent notes and a to-do list, saved to a JSON file between sessions."""
from __future__ import annotations

import json
from datetime import datetime

from . import ToolError, tool


def _load(ctx) -> dict:
    if ctx.memory_file.exists():
        try:
            return json.loads(ctx.memory_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"notes": {}, "tasks": []}


def _save(ctx, data: dict) -> None:
    ctx.memory_file.parent.mkdir(parents=True, exist_ok=True)
    ctx.memory_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def memory_summary(ctx, limit: int = 40) -> str:
    """Short list of saved notes, injected into the system prompt."""
    notes = _load(ctx)["notes"]
    lines = [f"- {k}: {v}" for k, v in list(notes.items())[:limit]]
    return "\n".join(lines) or "(none yet)"


@tool("remember", "Save a note that persists across sessions (e.g. the user's preferences or facts).",
      {"key": {"type": "string", "description": "Short label"}, "value": {"type": "string"}})
def remember(ctx, key: str, value: str) -> str:
    data = _load(ctx)
    data["notes"][key] = value
    _save(ctx, data)
    return f"Saved note '{key}'."


@tool("recall", "Look up saved notes. Leave query empty to list them all.",
      {"query": {"type": "string"}}, required=[])
def recall(ctx, query: str = "") -> str:
    notes = _load(ctx)["notes"]
    q = query.lower()
    hits = {k: v for k, v in notes.items() if q in k.lower() or q in v.lower()}
    return "\n".join(f"{k}: {v}" for k, v in hits.items()) or "No matching notes."


@tool("forget", "Delete a saved note.", {"key": {"type": "string"}})
def forget(ctx, key: str) -> str:
    data = _load(ctx)
    if data["notes"].pop(key, None) is None:
        raise ToolError(f"No note called '{key}'.")
    _save(ctx, data)
    return f"Forgot '{key}'."


@tool("task_add", "Add an item to the user's to-do list.",
      {"title": {"type": "string"}, "due": {"type": "string", "description": "Optional due date"}},
      required=["title"])
def task_add(ctx, title: str, due: str = "") -> str:
    data = _load(ctx)
    task_id = max((t["id"] for t in data["tasks"]), default=0) + 1
    data["tasks"].append({"id": task_id, "title": title, "due": due, "done": False,
                          "created": datetime.now().isoformat(timespec="minutes")})
    _save(ctx, data)
    return f"Added task #{task_id}: {title}"


@tool("task_list", "Show the to-do list.",
      {"show_done": {"type": "boolean", "description": "Include completed tasks"}}, required=[])
def task_list(ctx, show_done: bool = False) -> str:
    tasks = [t for t in _load(ctx)["tasks"] if show_done or not t["done"]]
    return "\n".join(
        f"#{t['id']} [{'x' if t['done'] else ' '}] {t['title']}" + (f" (due {t['due']})" if t["due"] else "")
        for t in tasks
    ) or "No tasks."


@tool("task_complete", "Mark a to-do item as done.", {"task_id": {"type": "integer"}})
def task_complete(ctx, task_id: int) -> str:
    data = _load(ctx)
    for t in data["tasks"]:
        if t["id"] == task_id:
            t["done"] = True
            _save(ctx, data)
            return f"Completed #{task_id}: {t['title']}"
    raise ToolError(f"No task #{task_id}.")
