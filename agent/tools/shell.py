"""Run shell commands (git, pip, npm, build tools...). Always asks first."""
from __future__ import annotations

import subprocess

from . import ToolError, tool


def format_process(proc: subprocess.CompletedProcess) -> str:
    parts = [f"exit code: {proc.returncode}"]
    if proc.stdout.strip():
        parts.append(f"stdout:\n{proc.stdout.strip()}")
    if proc.stderr.strip():
        parts.append(f"stderr:\n{proc.stderr.strip()}")
    return "\n".join(parts)


@tool(
    "run_shell",
    "Run a shell command in the workspace folder and return its output. "
    "Good for git, installing packages, running tests or builds. Avoid interactive commands.",
    {"command": {"type": "string"}},
    confirm=True,
)
def run_shell(ctx, command: str) -> str:
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=ctx.workspace,
            capture_output=True,
            text=True,
            timeout=ctx.command_timeout,
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"Command timed out after {ctx.command_timeout}s.")
    return format_process(proc)
