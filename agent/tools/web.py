"""Web page reader. (Web *search* is a built-in Claude server tool enabled in core.py.)"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from . import ToolError, tool

MAX_CHARS = 25_000


@tool(
    "fetch_url",
    "Download a web page, text file or JSON API response and return its readable text.",
    {"url": {"type": "string", "description": "Full http(s) URL"}},
)
def fetch_url(ctx, url: str) -> str:
    if urlparse(url).scheme not in ("http", "https"):
        raise ToolError("Only http(s) URLs are allowed.")
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (ai-agent)"})
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ToolError(f"Could not fetch {url}: {e}")

    title = ""
    if "html" in resp.headers.get("content-type", ""):
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
            tag.decompose()
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        text = re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n")).strip()
    else:
        text = resp.text

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n... (truncated)"
    return f"URL: {resp.url}\nTitle: {title}\n\n{text}"


@tool(
    "search_web",
    "Search the web (DuckDuckGo) and return the top results with links and snippets. "
    "Use fetch_url to read a result in full.",
    {"query": {"type": "string"}},
    ci=True,
)
def search_web(ctx, query: str) -> str:
    try:
        from ddgs import DDGS
    except ImportError:
        raise ToolError("Web search needs the 'ddgs' package: pip install ddgs")
    try:
        results = DDGS().text(query, max_results=8)
    except Exception as e:
        raise ToolError(f"Search failed: {e}")
    return "\n\n".join(
        f"{r.get('title', '')}\n{r.get('href', '')}\n{r.get('body', '')}" for r in results
    ) or "No results."
