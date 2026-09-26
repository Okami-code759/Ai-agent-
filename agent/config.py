"""Settings, loaded from environment variables or a .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini-flash-latest",  # free tier via Google AI Studio
}


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip() or default


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    provider: str = field(default_factory=lambda: _env("AGENT_PROVIDER").lower())  # anthropic | gemini
    api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY"))
    model: str = field(default_factory=lambda: _env("AGENT_MODEL"))
    max_tokens: int = field(default_factory=lambda: int(_env("AGENT_MAX_TOKENS", "8000")))
    max_steps: int = field(default_factory=lambda: int(_env("AGENT_MAX_STEPS", "30")))
    workspace: Path = field(default_factory=lambda: Path(_env("AGENT_WORKSPACE", "workspace")).expanduser().resolve())
    memory_file: Path = field(default_factory=lambda: Path(_env("AGENT_MEMORY_FILE", "~/.ai_agent/memory.json")).expanduser())
    github_token: str = field(default_factory=lambda: _env("GITHUB_TOKEN"))
    web_search: bool = field(default_factory=lambda: _bool("AGENT_WEB_SEARCH", True))
    auto_approve: bool = field(default_factory=lambda: _bool("AGENT_AUTO_APPROVE", False))
    command_timeout: int = field(default_factory=lambda: int(_env("AGENT_COMMAND_TIMEOUT", "60")))
    safe_mode: bool = field(default_factory=lambda: _bool("AGENT_SAFE_MODE", False))  # no shell/Python/deletes
    ci: bool = False  # True when running inside GitHub Actions (restricted tool set)

    def __post_init__(self) -> None:
        if not self.provider:  # pick whichever key is set, preferring Claude
            self.provider = "gemini" if self.gemini_api_key and not self.api_key else "anthropic"
        self.model = self.model or DEFAULT_MODELS.get(self.provider, "")

    def use_provider(self, provider: str) -> None:
        """Switch provider (from a command-line flag) and reset the model to its default."""
        if provider and provider != self.provider:
            self.provider, self.model = provider, ""
            self.__post_init__()

    def validate(self) -> None:
        if self.provider not in DEFAULT_MODELS:
            raise SystemExit(f"Unknown AGENT_PROVIDER '{self.provider}'. Use: {', '.join(DEFAULT_MODELS)}.")
        if self.provider == "anthropic" and not self.api_key:
            raise SystemExit("No API key found. Add ANTHROPIC_API_KEY (or GEMINI_API_KEY for the free option) to .env.")
        if self.provider == "gemini" and not self.gemini_api_key:
            raise SystemExit("AGENT_PROVIDER is gemini but GEMINI_API_KEY is not set in .env.")
        self.workspace.mkdir(parents=True, exist_ok=True)
