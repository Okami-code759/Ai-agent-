"""Interactive terminal interface."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from .config import Config
from .core import Agent

console = Console()

HELP = """[bold]Commands[/bold]
  /tools   list everything the agent can do
  /reset   start a fresh conversation
  /exit    quit
Anything else is sent to the agent. Ctrl+C interrupts a running task."""


def _short(value, limit: int = 60) -> str:
    s = value if isinstance(value, str) else json.dumps(value)
    s = s.replace("\n", "\\n")
    return s if len(s) <= limit else s[: limit - 1] + "…"


class RichUI:
    def thinking(self):
        return console.status("[cyan]Thinking…[/cyan]", spinner="dots")

    def text(self, text: str) -> None:
        console.print(Markdown(text))

    def tool_call(self, name: str, args: dict) -> None:
        preview = ", ".join(f"{k}={_short(v)}" for k, v in args.items())
        console.print(f"[dim]🔧 {escape(name)}({escape(preview)})[/dim]")

    def tool_result(self, name: str, result: str, is_error: bool) -> None:
        first = result.strip().splitlines()[0] if result.strip() else "(no output)"
        style = "red" if is_error else "green"
        console.print(f"   [{style}]↳ {escape(_short(first, 100))}[/{style}]")

    def confirm(self, name: str, args: dict) -> bool:
        body = "\n".join(f"[bold]{escape(k)}[/bold]: {escape(str(v))[:1500]}" for k, v in args.items())
        console.print(Panel(body or "(no arguments)", title=f"Allow {escape(name)}?", border_style="yellow"))
        return Confirm.ask("Run it?", default=False)


def _show_tools(agent: Agent) -> None:
    table = Table("Tool", "What it does", "Asks first")
    for t in agent.tools.values():
        table.add_row(t.name, t.description, "yes" if t.confirm else "")
    if agent.config.web_search:
        table.add_row("web_search", "Search the web (built into Claude)", "")
    console.print(table)


def _ask(agent: Agent, prompt: str) -> None:
    try:
        agent.run(prompt)
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow]")
    except anthropic.APIError as e:
        console.print(f"[red]API error:[/red] {escape(str(e))}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="General-purpose AI agent powered by Claude")
    parser.add_argument("prompt", nargs="*", help="Run a single request and exit")
    parser.add_argument("--model", help="Override AGENT_MODEL")
    parser.add_argument("--workspace", help="Folder the agent works in")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Run shell/Python/delete/GitHub-write tools without asking (careful!)")
    args = parser.parse_args(argv)

    config = Config()
    if args.model:
        config.model = args.model
    if args.workspace:
        config.workspace = Path(args.workspace).expanduser().resolve()
    if args.auto_approve:
        config.auto_approve = True
    config.validate()

    agent = Agent(config, RichUI())
    if args.prompt:
        _ask(agent, " ".join(args.prompt))
        return

    console.print(Panel.fit(
        f"[bold]AI Agent[/bold]  model [cyan]{escape(config.model)}[/cyan]\n"
        f"workspace [cyan]{escape(str(config.workspace))}[/cyan]\nType /help for commands."
    ))
    while True:
        try:
            user = console.input("\n[bold green]you ›[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not user:
            continue
        if user in ("/exit", "/quit"):
            break
        if user == "/help":
            console.print(HELP)
        elif user == "/tools":
            _show_tools(agent)
        elif user == "/reset":
            agent.reset()
            console.print("[dim]Conversation cleared.[/dim]")
        else:
            _ask(agent, user)
