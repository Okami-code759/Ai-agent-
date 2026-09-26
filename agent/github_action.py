"""GitHub Actions entry point.

Comment `/agent <request>` on any issue or pull request and the agent replies.
Only the repo owner, org members and collaborators can trigger it, and it runs with a
restricted tool set (read-only files, GitHub read + create issue, web search, maths).
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path

import requests

from .config import Config
from .core import Agent

TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
TRIGGER = "/agent"


class LogUI:
    def thinking(self):
        return nullcontext()

    def text(self, text: str) -> None:
        print(f"[agent] {text}\n", flush=True)

    def tool_call(self, name: str, args: dict) -> None:
        print(f"[tool] {name} {json.dumps(args)[:300]}", flush=True)

    def tool_result(self, name: str, result: str, is_error: bool) -> None:
        print(f"  -> {'ERROR ' if is_error else ''}{result[:300]}", flush=True)

    def confirm(self, name: str, args: dict) -> bool:
        return True  # only CI-safe tools are loaded in this mode


def _api(method: str, path: str, token: str, **kwargs):
    resp = requests.request(method, f"https://api.github.com{path}", timeout=30, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
    }, **kwargs)
    resp.raise_for_status()
    return resp


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    comment, issue = event.get("comment"), event.get("issue")

    if not comment or not issue:
        sys.exit("This entry point expects an issue_comment event.")
    body = (comment.get("body") or "").strip()
    if not body.startswith(TRIGGER):
        print("No /agent command; nothing to do.")
        return
    if comment.get("author_association") not in TRUSTED:
        print(f"Ignoring request from untrusted user {comment['user']['login']}.")
        return

    number = issue["number"]
    kind = "pull request" if "pull_request" in issue else "issue"
    request = body[len(TRIGGER):].strip() or f"Help with this {kind}."
    _api("POST", f"/repos/{repo}/issues/comments/{comment['id']}/reactions", token, json={"content": "eyes"})

    config = Config(ci=True, github_token=token, workspace=Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve())
    config.validate()
    prompt = (
        f"You were invoked from {kind} #{number} in the GitHub repo {repo}.\n"
        f"The repo is checked out in your workspace. Title: {issue['title']}\n\n"
        f"Request from @{comment['user']['login']}:\n{request}\n\n"
        f"Use github_get_issue to read the full thread"
        f"{' and github_get_pr_diff to review the changes' if kind == 'pull request' else ''}. "
        "Your final message will be posted as a reply comment, so don't post comments yourself."
    )

    try:
        answer = Agent(config, LogUI()).run(prompt) or "Done."
    except Exception as e:  # tell the user something went wrong instead of failing silently
        answer = f"Sorry, I hit an error: `{type(e).__name__}: {e}`"
        _api("POST", f"/repos/{repo}/issues/{number}/comments", token, json={"body": answer})
        raise

    _api("POST", f"/repos/{repo}/issues/{number}/comments", token,
         json={"body": f"{answer}\n\n<sub>🤖 AI agent · model `{config.model}`</sub>"})


if __name__ == "__main__":
    main()
