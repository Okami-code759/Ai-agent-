"""GitHub tools: repos, files, issues, pull requests and search.

Needs GITHUB_TOKEN for anything private or any write action.
"""
from __future__ import annotations

import requests

from . import ToolError, tool

API = "https://api.github.com"
REPO = {"type": "string", "description": "Repository as 'owner/name'"}


def _gh(ctx, method: str, path: str, accept: str = "application/vnd.github+json", **kwargs):
    headers = {"Accept": accept}
    if ctx.github_token:
        headers["Authorization"] = f"Bearer {ctx.github_token}"
    try:
        resp = requests.request(method, API + path, headers=headers, timeout=30, **kwargs)
    except requests.RequestException as e:
        raise ToolError(f"GitHub request failed: {e}")
    if resp.status_code >= 400:
        raise ToolError(f"GitHub API error {resp.status_code}: {resp.text[:500]}")
    return resp


def _need_token(ctx) -> None:
    if not ctx.github_token:
        raise ToolError("GITHUB_TOKEN is not set. Add a GitHub personal access token to .env.")


@tool("github_list_my_repos", "List your GitHub repositories, most recently updated first.",
      {"limit": {"type": "integer", "description": "Max repos (default 30)"}}, required=[])
def github_list_my_repos(ctx, limit: int = 30) -> str:
    _need_token(ctx)
    repos = _gh(ctx, "GET", "/user/repos", params={"sort": "updated", "per_page": min(limit, 100)}).json()
    return "\n".join(
        f"{r['full_name']} ({'private' if r['private'] else 'public'}) - {r.get('description') or ''}"
        for r in repos
    ) or "No repositories."


@tool(
    "github_create_repo",
    "Create a new repository on your GitHub account.",
    {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "private": {"type": "boolean", "description": "Default true"},
    },
    required=["name"],
    confirm=True,
)
def github_create_repo(ctx, name: str, description: str = "", private: bool = True) -> str:
    _need_token(ctx)
    repo = _gh(ctx, "POST", "/user/repos", json={
        "name": name, "description": description, "private": private, "auto_init": True,
    }).json()
    return f"Created {repo['full_name']}: {repo['html_url']}\nClone: {repo['clone_url']}"


@tool(
    "github_read_file",
    "Read a file (or list a folder) from a GitHub repository without cloning it.",
    {"repo": REPO, "path": {"type": "string"}, "ref": {"type": "string", "description": "Branch/tag/commit"}},
    required=["repo", "path"],
    ci=True,
)
def github_read_file(ctx, repo: str, path: str, ref: str = "") -> str:
    params = {"ref": ref} if ref else None
    resp = _gh(ctx, "GET", f"/repos/{repo}/contents/{path.lstrip('/')}",
               accept="application/vnd.github.raw+json", params=params)
    if resp.headers.get("content-type", "").startswith("application/json"):
        data = resp.json()
        if isinstance(data, list):  # a folder
            return "\n".join(f"{i['path']}{'/' if i['type'] == 'dir' else ''}" for i in data)
    return resp.text[:60_000]


@tool(
    "github_list_issues",
    "List issues in a repository (pull requests are marked [PR]).",
    {"repo": REPO, "state": {"type": "string", "enum": ["open", "closed", "all"]}},
    required=["repo"],
    ci=True,
)
def github_list_issues(ctx, repo: str, state: str = "open") -> str:
    items = _gh(ctx, "GET", f"/repos/{repo}/issues", params={"state": state, "per_page": 30}).json()
    return "\n".join(
        f"#{i['number']} {'[PR] ' if 'pull_request' in i else ''}{i['title']} (by {i['user']['login']})"
        for i in items
    ) or "No issues."


@tool(
    "github_get_issue",
    "Get an issue or pull request's description and its comments.",
    {"repo": REPO, "number": {"type": "integer"}},
    ci=True,
)
def github_get_issue(ctx, repo: str, number: int) -> str:
    issue = _gh(ctx, "GET", f"/repos/{repo}/issues/{number}").json()
    comments = _gh(ctx, "GET", f"/repos/{repo}/issues/{number}/comments", params={"per_page": 50}).json()
    out = [f"#{number}: {issue['title']} [{issue['state']}] by {issue['user']['login']}",
           issue.get("body") or "(no description)", "", f"--- {len(comments)} comments ---"]
    out += [f"@{c['user']['login']}: {c['body']}" for c in comments]
    return "\n".join(out)


@tool(
    "github_create_issue",
    "Open a new issue in a repository.",
    {"repo": REPO, "title": {"type": "string"}, "body": {"type": "string"}},
    confirm=True,
    ci=True,
)
def github_create_issue(ctx, repo: str, title: str, body: str) -> str:
    _need_token(ctx)
    issue = _gh(ctx, "POST", f"/repos/{repo}/issues", json={"title": title, "body": body}).json()
    return f"Created issue #{issue['number']}: {issue['html_url']}"


@tool(
    "github_comment",
    "Post a comment on an issue or pull request.",
    {"repo": REPO, "number": {"type": "integer"}, "body": {"type": "string"}},
    confirm=True,
)
def github_comment(ctx, repo: str, number: int, body: str) -> str:
    _need_token(ctx)
    c = _gh(ctx, "POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body}).json()
    return f"Commented: {c['html_url']}"


@tool(
    "github_list_pulls",
    "List pull requests in a repository.",
    {"repo": REPO, "state": {"type": "string", "enum": ["open", "closed", "all"]}},
    required=["repo"],
    ci=True,
)
def github_list_pulls(ctx, repo: str, state: str = "open") -> str:
    prs = _gh(ctx, "GET", f"/repos/{repo}/pulls", params={"state": state, "per_page": 30}).json()
    return "\n".join(
        f"#{p['number']} {p['title']} ({p['head']['ref']} -> {p['base']['ref']}) by {p['user']['login']}"
        for p in prs
    ) or "No pull requests."


@tool(
    "github_get_pr_diff",
    "Get the code diff of a pull request, for reviewing changes.",
    {"repo": REPO, "number": {"type": "integer"}},
    ci=True,
)
def github_get_pr_diff(ctx, repo: str, number: int) -> str:
    diff = _gh(ctx, "GET", f"/repos/{repo}/pulls/{number}", accept="application/vnd.github.diff").text
    return diff[:60_000] + ("\n... (diff truncated)" if len(diff) > 60_000 else "")


@tool(
    "github_search",
    "Search GitHub for repositories, code or issues. Code search needs a token.",
    {"query": {"type": "string"}, "kind": {"type": "string", "enum": ["repositories", "code", "issues"]}},
    required=["query"],
    ci=True,
)
def github_search(ctx, query: str, kind: str = "repositories") -> str:
    items = _gh(ctx, "GET", f"/search/{kind}", params={"q": query, "per_page": 15}).json().get("items", [])
    if kind == "repositories":
        lines = [f"{i['full_name']} ★{i['stargazers_count']} - {i.get('description') or ''}" for i in items]
    elif kind == "code":
        lines = [f"{i['repository']['full_name']}: {i['path']}" for i in items]
    else:
        lines = [f"{i['html_url']} - {i['title']}" for i in items]
    return "\n".join(lines) or "No results."
