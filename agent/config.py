"""Settings, loaded from environment variables or a .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "").strip())
    model: str = field(default_factory=lambda: _env("AGENT_MODEL", "claude-sonnet-5"))
    max_tokens: int = field(default_factory=lambda: int(_env("AGENT_MAX_TOKENS", "8000")))
    max_steps: int = field(default_factory=lambda: int(_env("AGENT_MAX_STEPS", "30")))
    workspace: Path = field(default_factory=lambda: Path(_env("AGENT_WORKSPACE", "workspace")).expanduser().resolve())
    memory_file: Path = field(default_factory=lambda: Path(_env("AGENT_MEMORY_FILE", "~/.ai_agent/memory.json")).expanduser())
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", "").strip())
    web_search: bool = field(default_factory=lambda: _bool("AGENT_WEB_SEARCH", True))
    auto_approve: bool = field(default_factory=lambda: _bool("AGENT_AUTO_APPROVE", False))
    command_timeout: int = field(default_factory=lambda: int(_env("AGENT_COMMAND_TIMEOUT", "60")))
    ci: bool = False  # True when running inside GitHub Actions (restricted tool set)

    def validate(self) -> None:
        if not self.api_key:
            raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
        self.workspace.mkdir(parents=True, exist_ok=True)
