"""Tool registry.

Add a new capability by writing a function and decorating it with @tool.
Every tool receives the Config as its first argument and returns a string.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class ToolError(Exception):
    """Raise inside a tool to send a clean error message back to the model."""


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    required: list[str]
    fn: Callable[..., str]
    confirm: bool = False  # ask the user before running (terminal mode)
    ci: bool = False       # allowed when running inside GitHub Actions

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
            },
        }


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    required: list[str] | None = None,
    *,
    confirm: bool = False,
    ci: bool = False,
):
    """Register a function as a tool. `required` defaults to every parameter."""
    parameters = parameters or {}

    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            required=list(parameters) if required is None else required,
            fn=fn,
            confirm=confirm,
            ci=ci,
        )
        return fn

    return decorator


def load_tools(ci: bool = False) -> dict[str, Tool]:
    """Import every tool module (which registers its tools) and return the usable set."""
    from . import code, files, github, memory, shell, utils, web  # noqa: F401

    return {name: t for name, t in REGISTRY.items() if t.ci or not ci}
