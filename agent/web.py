"""The agent as a web app: a chat interface in your browser, installable on your phone.

    python app.py                  # this computer only: http://127.0.0.1:8000
    python app.py --host 0.0.0.0   # other devices on your Wi-Fi too (needs APP_PASSWORD)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import secrets
import socket
import uuid
from concurrent.futures import Future, TimeoutError as FutureTimeout
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Config
from .core import Agent, Stopped
from .providers import ProviderError

STATIC = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("font/woff2", ".woff2")


class WebUI:
    """Streams agent events to the browser and waits for the user's answer on approvals."""

    def __init__(self, send):
        self.send = send
        self.pending: dict[str, Future] = {}

    @contextmanager
    def thinking(self):
        self.send({"type": "thinking", "value": True})
        try:
            yield
        finally:
            self.send({"type": "thinking", "value": False})

    def text(self, text: str) -> None:
        self.send({"type": "text", "text": text})

    def tool_call(self, name: str, args: dict) -> None:
        self.send({"type": "tool_call", "name": name, "args": args})

    def tool_result(self, name: str, result: str, is_error: bool) -> None:
        self.send({"type": "tool_result", "name": name, "result": result[:6000], "is_error": is_error})

    def confirm(self, name: str, args: dict) -> bool:
        confirm_id = uuid.uuid4().hex
        future: Future = Future()
        self.pending[confirm_id] = future
        self.send({"type": "confirm", "id": confirm_id, "name": name, "args": args})
        try:
            return bool(future.result(timeout=900))  # no answer in 15 minutes = don't run
        except FutureTimeout:
            return False
        finally:
            self.pending.pop(confirm_id, None)

    def answer(self, confirm_id: str, approved: bool) -> None:
        future = self.pending.get(confirm_id)
        if future and not future.done():
            future.set_result(approved)

    def deny_all(self) -> None:
        for future in list(self.pending.values()):
            if not future.done():
                future.set_result(False)


def create_app(config: Config, password: str = "") -> FastAPI:
    app = FastAPI(title="Agent", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/info")
    def info():
        return {"auth": bool(password), "provider": config.provider, "model": config.model,
                "safe_mode": config.safe_mode}

    @app.websocket("/ws")
    async def chat(ws: WebSocket):
        await ws.accept()
        if password and not secrets.compare_digest(ws.query_params.get("key", ""), password):
            await ws.close(code=4401, reason="Wrong password")
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def send(event: dict) -> None:  # safe to call from the agent's worker thread
            loop.call_soon_threadsafe(queue.put_nowait, event)

        ui = WebUI(send)
        agent = Agent(config, ui)  # one conversation per browser tab
        task: asyncio.Task | None = None

        async def writer():
            while True:
                await ws.send_json(await queue.get())

        async def run(text: str):
            send({"type": "busy", "value": True})
            try:
                await asyncio.to_thread(agent.run, text)
            except Stopped:
                send({"type": "stopped"})
            except ProviderError as e:
                send({"type": "error", "text": str(e)})
            except Exception as e:
                send({"type": "error", "text": f"Something went wrong: {type(e).__name__}: {e}"})
            finally:
                send({"type": "busy", "value": False})

        writer_task = asyncio.create_task(writer())
        send({"type": "hello", "provider": config.provider, "model": config.model,
              "safe_mode": config.safe_mode, "tools": sorted(agent.tools)})
        try:
            while True:
                try:
                    msg = json.loads(await ws.receive_text())
                except (ValueError, TypeError):
                    continue
                kind = msg.get("type")
                working = task is not None and not task.done()
                if kind == "message":
                    text = str(msg.get("text", "")).strip()[:20_000]
                    if not text:
                        continue
                    if working:
                        send({"type": "error", "text": "Still working on the last request. Stop it or wait."})
                        continue
                    task = asyncio.create_task(run(text))
                elif kind == "confirm":
                    ui.answer(str(msg.get("id")), bool(msg.get("approved")))
                elif kind == "stop":
                    agent.stop_event.set()
                    ui.deny_all()
                elif kind == "reset":
                    if working:
                        send({"type": "error", "text": "Stop the current request before starting a new chat."})
                    else:
                        agent.reset()
                        send({"type": "reset"})
        except WebSocketDisconnect:
            pass
        finally:
            agent.stop_event.set()
            ui.deny_all()
            writer_task.cancel()

    return app


def _lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "your-computer-ip"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the agent as a web app")
    parser.add_argument("--host", default=os.getenv("APP_HOST", "127.0.0.1"),
                        help="127.0.0.1 = this computer only; 0.0.0.0 = other devices too")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--provider", choices=["anthropic", "gemini"], help="Override AGENT_PROVIDER")
    args = parser.parse_args(argv)

    config = Config()
    if args.provider:
        config.use_provider(args.provider)

    password = os.getenv("APP_PASSWORD", "").strip()
    public = args.host not in LOCAL_HOSTS
    if public and len(password) < 8:
        raise SystemExit("Set APP_PASSWORD (8+ characters) in .env before opening the app to other devices.")
    if public and os.getenv("AGENT_SAFE_MODE", "").strip().lower() not in {"false", "0", "no", "off"}:
        config.safe_mode = True  # no shell/Python/deletes when reachable from outside, unless you opt out
    config.validate()

    print(f"\n  Agent app running ({config.provider}, {config.model})")
    print(f"  This computer:  http://127.0.0.1:{args.port}")
    if public:
        print(f"  Other devices:  http://{_lan_ip()}:{args.port}   (same Wi-Fi)")
        print(f"  Safe mode: {'on (no shell/Python/deletes)' if config.safe_mode else 'OFF'}")
    print("  Press Ctrl+C to stop.\n")

    import uvicorn

    uvicorn.run(create_app(config, password), host=args.host, port=args.port, log_level="warning")
