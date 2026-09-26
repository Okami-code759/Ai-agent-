"""Run Python code for calculations, data processing, charts, scripts..."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from . import ToolError, tool
from .shell import format_process


@tool(
    "run_python",
    "Execute a Python script (in the workspace folder) and return what it prints. "
    "Use print() to show results. Files it saves land in the workspace.",
    {"code": {"type": "string"}},
    confirm=True,
)
def run_python(ctx, code: str) -> str:
    fd, script = tempfile.mkstemp(suffix=".py", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        proc = subprocess.run(
            [sys.executable, script],
            cwd=ctx.workspace,
            capture_output=True,
            text=True,
            timeout=ctx.command_timeout,
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"Script timed out after {ctx.command_timeout}s.")
    finally:
        os.remove(script)
    return format_process(proc)
