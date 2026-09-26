"""Model backends. Each one keeps the conversation in its own API's format and exposes:

    add_user(text)             -> None
    step(system)               -> Step (text + any tool calls the model wants)
    add_tool_results(results)  -> None
    messages                   -> the history list (used to roll back on errors)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import requests

from .config import Config
from .tools import Tool


class ProviderError(Exception):
    """A readable error from the model API (bad key, rate limit, etc.)."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    id: str
    name: str
    output: str
    is_error: bool


@dataclass
class Step:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop: str = "end"  # end | tool_use | continue | max_tokens


def make_backend(config: Config, tools: dict[str, Tool]):
    if config.provider == "gemini":
        return GeminiBackend(config, tools)
    return AnthropicBackend(config, tools)


# --------------------------------------------------------------------------- Claude

class AnthropicBackend:
    has_server_search = True

    def __init__(self, config: Config, tools: dict[str, Tool]):
        import anthropic

        self.anthropic = anthropic
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.api_key)
        self.messages: list[dict[str, Any]] = []
        self.schemas = [t.schema() for t in tools.values()]
        if config.web_search:
            # Server-side tool: Anthropic runs the search, no extra key needed.
            self.schemas.append({"type": "web_search_20250305", "name": "web_search", "max_uses": 5})

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def step(self, system: str) -> Step:
        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system,
                tools=self.schemas,
                messages=self.messages,
            )
        except self.anthropic.APIError as e:
            raise ProviderError(f"Claude API error: {e}") from e

        if self.messages[-1]["role"] == "assistant":  # continuing after pause_turn
            self.messages[-1]["content"] = list(self.messages[-1]["content"]) + list(response.content)
        else:
            self.messages.append({"role": "assistant", "content": response.content})

        text = "".join(b.text for b in response.content if b.type == "text").strip()
        calls = [ToolCall(b.id, b.name, dict(b.input or {})) for b in response.content if b.type == "tool_use"]
        stop = {"tool_use": "tool_use", "pause_turn": "continue", "max_tokens": "max_tokens"}.get(
            response.stop_reason, "end")
        return Step(text, calls, stop)

    def add_tool_results(self, results: list[ToolResult]) -> None:
        self.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r.id, "content": r.output, "is_error": r.is_error}
            for r in results
        ]})


# --------------------------------------------------------------------------- Gemini

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a JSON schema to the subset Gemini's function declarations accept."""
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "type":
            out["type"] = value.upper()
        elif key == "properties":
            out["properties"] = {name: gemini_schema(p) for name, p in value.items()}
        elif key == "items":
            out["items"] = gemini_schema(value)
        elif key in ("description", "enum") or (key == "required" and value):
            out[key] = value
    return out


class GeminiBackend:
    has_server_search = False

    def __init__(self, config: Config, tools: dict[str, Tool]):
        self.config = config
        self.messages: list[dict[str, Any]] = []  # Gemini calls these "contents"
        self.declarations = [
            {"name": t.name, "description": t.description, "parameters": gemini_schema(t.schema()["input_schema"])}
            for t in tools.values()
        ]
        self._call_ids: dict[str, bool] = {}  # which calls came with an id we must echo back

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "parts": [{"text": text}]})

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = GEMINI_URL.format(model=self.config.model)
        headers = {"x-goog-api-key": self.config.gemini_api_key, "Content-Type": "application/json"}
        for attempt in range(4):
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=180)
            except requests.RequestException as e:
                raise ProviderError(f"Could not reach Gemini: {e}") from e
            if resp.status_code in (429, 500, 503) and attempt < 3:
                time.sleep(10 * 2 ** attempt)  # free tier rate limits: wait 10s, 20s, 40s
                continue
            if resp.status_code >= 400:
                try:
                    message = resp.json()["error"]["message"]
                except (ValueError, KeyError, TypeError):
                    message = resp.text[:500]
                raise ProviderError(f"Gemini API error {resp.status_code}: {message}")
            return resp.json()
        raise ProviderError("Gemini is rate-limiting requests. Wait a minute and try again.")

    def step(self, system: str) -> Step:
        data = self._post({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": self.messages,
            "tools": [{"functionDeclarations": self.declarations}],
            "generationConfig": {"maxOutputTokens": self.config.max_tokens},
        })
        candidate = (data.get("candidates") or [{}])[0]
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            reason = (data.get("promptFeedback") or {}).get("blockReason") or candidate.get("finishReason", "unknown")
            parts = [{"text": f"(Gemini returned no answer: {reason})"}]
        # Store the model's turn exactly as returned so hidden thought signatures are preserved.
        self.messages.append({**content, "role": "model", "parts": parts})

        text = "".join(p["text"] for p in parts if "text" in p and not p.get("thought")).strip()
        calls = []
        for i, part in enumerate(parts):
            if "functionCall" in part:
                fc = part["functionCall"]
                call_id = fc.get("id") or f"call_{len(self.messages)}_{i}"
                self._call_ids[call_id] = "id" in fc
                calls.append(ToolCall(call_id, fc["name"], dict(fc.get("args") or {})))

        if calls:
            return Step(text, calls, "tool_use")
        return Step(text, [], "max_tokens" if candidate.get("finishReason") == "MAX_TOKENS" else "end")

    def add_tool_results(self, results: list[ToolResult]) -> None:
        parts = []
        for r in results:
            response = {"name": r.name, "response": {"error" if r.is_error else "result": r.output}}
            if self._call_ids.pop(r.id, False):
                response["id"] = r.id
            parts.append({"functionResponse": response})
        self.messages.append({"role": "user", "parts": parts})
