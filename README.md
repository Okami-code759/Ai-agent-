# AI Agent

A general-purpose AI agent in Python, powered by Claude or Google Gemini (free tier). Chat with it in your terminal and it
can search the web, read pages, write and edit files, run code and shell commands, manage your
GitHub repos, issues and pull requests, do exact maths, and remember things between sessions.
It can also run **on GitHub itself**: comment `/agent <request>` on any issue or PR and it replies.

## What it can do

| Area | Tools |
|---|---|
| Web | `web_search` (built into Claude) or `search_web` (free, DuckDuckGo, used with Gemini), `fetch_url` |
| Files (sandboxed to `workspace/`) | `list_dir`, `read_file`, `write_file`, `edit_file`, `search_files`, `delete_file`* |
| Code | `run_python`*, `run_shell`* |
| GitHub | `github_list_my_repos`, `github_create_repo`*, `github_read_file`, `github_list_issues`, `github_get_issue`, `github_create_issue`*, `github_comment`*, `github_list_pulls`, `github_get_pr_diff`, `github_search` |
| Memory | `remember`, `recall`, `forget`, `task_add`, `task_list`, `task_complete` |
| Utilities | `calculate`, `current_datetime` |

\* asks for your permission before running.

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

Then open `.env` and add **one** model key:

- `GEMINI_API_KEY` — **free**. Get one at https://aistudio.google.com/apikey. Rate-limited, and
  Google may use free-tier conversations to improve its products, so don't send private data.
- `ANTHROPIC_API_KEY` — paid, and stronger at long multi-step tasks. Create one in the Claude
  Console (platform.claude.com). Billed separately from a Claude.ai subscription.

If you set both, Claude is used; force one with `AGENT_PROVIDER=gemini` or `--provider gemini`.
- `GITHUB_TOKEN` (optional) — a GitHub personal access token so the agent can use your repos.
  A classic token with the `repo` scope is simplest.

## Usage

```bash
python run.py                                  # interactive chat
python run.py "summarise the top 3 posts on news.ycombinator.com"   # one-shot
python run.py --workspace ~/projects/my-app    # let it work on an existing project
```

Chat commands: `/tools`, `/reset`, `/help`, `/exit`. Press Ctrl+C to interrupt a task.

Some things to try:

- "Make a Flask to-do app in the workspace, then run its tests"
- "Create a private GitHub repo called notes-app and list my open issues across repos"
- "Remember that I prefer Python type hints" (it'll recall this next session)
- "Review PR #3 in myname/myrepo and point out bugs"

## Put it on GitHub

Create an **empty** repository on github.com (no README), then from this folder:

```bash
git init
git add .
git commit -m "Initial commit: AI agent"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ai-agent.git
git push -u origin main
```

Or, with the GitHub CLI: `gh repo create ai-agent --private --source=. --push`

`.env` is in `.gitignore`, so your keys stay on your machine.

## Run it on GitHub (issue/PR bot)

1. In your repo: **Settings → Secrets and variables → Actions → New repository secret**,
   name it `GEMINI_API_KEY` (free) or `ANTHROPIC_API_KEY` (Claude) and paste your key.
2. Comment on any issue or pull request: `/agent explain what this PR changes and flag any bugs`
3. The agent reacts with 👀, does the work, and replies in a comment.

Copy `.github/workflows/agent.yml` plus the `agent/` folder and `requirements.txt` into any other
repo to add the bot there too. To change the model or provider, set repository **variables** `AGENT_MODEL` / `AGENT_PROVIDER`.

## Adding your own tools

Create a function in `agent/tools/` (or an existing file) and decorate it:

```python
from . import tool

@tool("reverse_text", "Reverse a string.", {"text": {"type": "string"}}, ci=True)
def reverse_text(ctx, text: str) -> str:
    return text[::-1]
```

If it's a new file, add it to the import line in `load_tools()` in `agent/tools/__init__.py`.
Use `confirm=True` for anything risky and `ci=True` if it's safe to run in GitHub Actions.

## Configuration

All settings live in `.env` (see `.env.example`): model, max tokens, max steps per request,
workspace folder, memory file location, web search on/off, command timeout, and
`AGENT_AUTO_APPROVE` (skips permission prompts; leave off unless you're sure).

## Security notes

- File tools can't leave the workspace folder and can't touch `.git` or `.env`.
- Shell, Python, deletes and GitHub write actions ask first in the terminal.
- In GitHub Actions, only the repo owner, org members and collaborators can trigger the agent,
  and it gets a restricted tool set: no shell, no Python, no file writes, no URL fetching.
  The checkout doesn't store the GitHub token, and the comment text is read from the event file
  rather than inserted into a shell script, which avoids workflow script injection.
- Web pages and issue text can contain prompt-injection attempts. The agent is told to treat
  them as data, but keep the permission prompts on when it's reading untrusted content.

## Project layout

```
run.py                     entry point
agent/core.py              the agent loop (model <-> tools)
agent/providers.py         Claude and Gemini backends
agent/cli.py               terminal interface
agent/github_action.py     GitHub Actions entry point
agent/config.py            settings from .env
agent/tools/               all the tools
.github/workflows/agent.yml
```
