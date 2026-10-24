"""One JARVIS, so the surfaces are views of the same thing.

Until now every command built its own: `jarvis chat` had a toolbox, `jarvis
watch` had another, the MCP server a third. That is survivable for a CLI and
fatal for a front end, because **a proposal is state**. `ProposalStore` is in
memory, so a proposal raised by voice cannot be confirmed from a window in a
different process — and "re-confirming is idempotent, from voice and the HUD
at once" is a promise the consent model makes and a split process cannot keep.

So: one process holds the bus, the registry, the toolbox and its proposals,
the HUD state and the agent. Everything else — the CLI, the app window, the
companion overlay, the voice loop — is a client of it.

Two things are kept deliberately:

**The handler is pure.** `Api.handle(method, path, body)` maps a request to a
response with no socket anywhere near it, the same way `mcp_server.handle`
does, so the whole surface is tested without binding a port.

**Reading is open on loopback; acting is not.** A token is generated at start,
written 0600, and required on anything that mutates. Loopback alone is the bar
for showing state; it is not the bar for confirming a proposal that may reach
a shell. Any local process can open a socket — not every local process should
be able to execute a pending command.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

class PortBusy(OSError):
    """Something already holds the port. Named, because the bare OSError says
    'Address already in use' and nothing about which address or whose."""

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        super().__init__(f"{host}:{port} is already in use")

    def hint(self) -> str:
        return f"ss -ltnp 'sport = :{self.port}'"


def state_dir(platform: Optional[str] = None) -> str:
    """Where the token lives, in the place each OS puts such things.

    ~/.local/state is the XDG answer and means nothing on Windows, where a
    dotted folder in the profile root is somewhere nothing looks and nothing
    cleans up.
    """
    if (platform or ("windows" if os.name == "nt" else "posix")) == "windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "jarvis")
    return os.path.expanduser("~/.local/state/jarvis")


STATE_DIR = state_dir()
TOKEN_FILE = os.path.join(STATE_DIR, "token")
DEFAULT_PORT = 8787

Body = Optional[Dict[str, Any]]
Reply = Tuple[int, Dict[str, Any]]


def read_token(path: str = TOKEN_FILE) -> str:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def write_token(path: str = TOKEN_FILE) -> str:
    """A fresh token each start, readable only by its owner."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    token = secrets.token_urlsafe(24)
    with open(path, "w") as fh:
        fh.write(token + "\n")
    if os.name != "nt":
        # 0600 means nothing useful on Windows, where the profile directory
        # already carries the ACL. Attempting it there just fails quietly.
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return token


# ---------------------------------------------------------------- the whole

@dataclass
class Jarvis:
    """The long-lived assistant. One of these per machine."""
    toolbox: Any
    state: Any
    bus: Any = None
    briefing: Any = None
    agent: Any = None
    token: str = ""
    started: float = field(default_factory=time.time)

    @classmethod
    def start(cls, agency: Optional[str] = None, heavy: Optional[str] = None,
              token: Optional[str] = None) -> "Jarvis":
        from core.bus import Bus
        from core.config import cfg
        from core.hud_state import HudState
        from core.registry import Registry
        from core.toolbox import Toolbox
        from core.tools import Agency
        from daemon.proactive import Briefing
        from daemon.toolbox.builtin import build

        level = Agency.parse(agency or cfg("JARVIS_AGENCY", "advisory"))
        bus = Bus(registry=Registry.load())
        briefing = Briefing()
        heavy_model = heavy if heavy is not None else cfg("JARVIS_HEAVY_MODEL", "")
        heavy_chat = None
        if heavy_model:
            from core.ollama import OllamaChat
            heavy_chat = OllamaChat(heavy_model)
        registry = build(bus=bus, briefing=briefing, heavy_chat=heavy_chat)
        return cls(toolbox=Toolbox(registry=registry, agency=level),
                   state=HudState(), bus=bus, briefing=briefing,
                   token=token if token is not None else write_token())

    # ---- what a surface asks for ----
    def snapshot(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "agency": self.toolbox.agency.name.lower(),
            "uptime_s": round(time.time() - self.started, 1),
            "proposals": [_proposal(p) for p in self.pending()],
        }
        for name in ("as_dict", "snapshot"):
            renderer = getattr(self.state, name, None)
            if callable(renderer):
                out["hud"] = renderer()
                break
        else:
            out["hud"] = {"state": str(getattr(self.state, "state", "calm"))}
        return out

    def tools(self) -> List[Dict[str, Any]]:
        return [{"name": t.name, "description": t.description,
                 "mutates": t.mutates, "risk": t.risk}
                for t in sorted(self.toolbox.registry.available(self.toolbox.agency),
                                key=lambda t: t.name)]

    def pending(self) -> List[Any]:
        store = getattr(self.toolbox, "proposals", None)
        items = getattr(store, "_items", {}) if store else {}
        return [p for p in items.values() if not p.is_terminal]

    # ---- what a surface does ----
    def invoke(self, name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from core.proposals import Proposal
        outcome = self.toolbox.invoke(name, args or {})
        if isinstance(outcome, Proposal):
            return {"kind": "proposal", "proposal": _proposal(outcome)}
        return {"kind": "result", "ok": outcome.ok,
                "value": outcome.value, "error": outcome.error}

    def answer(self, proposal_id: str, answer: str) -> Dict[str, Any]:
        if answer == "confirm":
            return {"proposal": _proposal(self.toolbox.confirm(proposal_id))}
        declined = self.toolbox.decline(proposal_id)
        return {"proposal": _proposal(declined) if declined else None}

    def say(self, text: str) -> Dict[str, Any]:
        if self.agent is None:
            return {"error": "no model attached"}
        turn = self.agent.say(text)
        return {"text": turn.text,
                "proposal": _proposal(turn.proposal) if turn.proposal else None,
                "tools_used": list(turn.tools_used)}


def _proposal(p: Any) -> Optional[Dict[str, Any]]:
    if p is None:
        return None
    return {"id": p.id, "tool": p.tool, "summary": p.summary,
            "risk": p.risk, "confirm_label": p.confirm_label,
            "status": p.status.value,
            "expires_in_s": max(0.0, round(p.expires_at - p.created_at, 1))}


# ---------------------------------------------------------------- the api

WRITES = ("/api/say", "/api/invoke", "/api/answer", "/api/intent", "/api/agency")


class Api:
    """Pure: a request in, a response out. No socket, no threads, no files."""

    def __init__(self, jarvis: Jarvis):
        self.jarvis = jarvis

    def handle(self, method: str, path: str, body: Body = None,
               token: str = "") -> Reply:
        path = path.split("?", 1)[0].rstrip("/") or "/"
        if path in WRITES and not self._allowed(token):
            # Same wording whether the token is absent or wrong: a caller
            # probing for the difference learns nothing from the answer.
            return 403, {"error": "not permitted"}

        if method == "GET":
            if path == "/api/state":
                return 200, self.jarvis.snapshot()
            if path == "/api/tools":
                return 200, {"tools": self.jarvis.tools()}
            if path == "/api/proposals":
                return 200, {"proposals": [_proposal(p)
                                           for p in self.jarvis.pending()]}
            return 404, {"error": f"no such path: {path}"}

        if method != "POST":
            return 405, {"error": f"{method} not allowed"}
        data = body or {}

        if path == "/api/say":
            text = str(data.get("text") or "").strip()
            if not text:
                return 400, {"error": "say what?"}
            return 200, self.jarvis.say(text)
        if path == "/api/invoke":
            name = str(data.get("tool") or "")
            if not name:
                return 400, {"error": "which tool?"}
            return 200, self.jarvis.invoke(name, data.get("args") or {})
        if path == "/api/answer":
            answer = str(data.get("answer") or "")
            if answer not in ("confirm", "decline"):
                return 400, {"error": "answer is confirm or decline"}
            return 200, self.jarvis.answer(str(data.get("id") or ""), answer)
        if path == "/api/intent":
            name = str(data.get("intent") or "")
            if not name or self.jarvis.bus is None:
                return 400, {"error": "no intent, or no bus"}
            from core.intent import Intent
            rejection = self.jarvis.bus.publish(Intent(
                name, source=str(data.get("source") or "ui"),
                confidence=float(data.get("confidence", 1.0)),
                args=data.get("args") or {}))
            return 200, {"published": not rejection, "why": str(rejection or "")}
        if path == "/api/agency":
            # Deliberately absent. Raising the ceiling is a deliberate act by
            # the user at the machine, not something a surface can ask for —
            # least of all one reachable over a socket.
            return 403, {"error": "agency is set in config/jarvis.env, "
                                  "not over the API"}
        return 404, {"error": f"no such path: {path}"}

    def _allowed(self, token: str) -> bool:
        expected = self.jarvis.token
        if not expected:
            return False
        return secrets.compare_digest(str(token), expected)


# ---------------------------------------------------------------- the socket

class Hub:
    """Fan-out to connected surfaces. A stalled window must not grow memory."""

    MAX_QUEUED = 32

    def __init__(self) -> None:
        import queue
        import threading
        self._queue = queue
        self._clients: List[Any] = []
        self._lock = threading.Lock()

    def subscribe(self):
        channel = self._queue.Queue(maxsize=self.MAX_QUEUED)
        with self._lock:
            self._clients.append(channel)
        return channel

    def unsubscribe(self, channel) -> None:
        with self._lock:
            if channel in self._clients:
                self._clients.remove(channel)

    def push(self, payload: Dict[str, Any]) -> None:
        line = json.dumps(payload, default=str)
        with self._lock:
            channels = list(self._clients)
        for channel in channels:
            try:
                channel.put_nowait(line)
            except Exception:
                self.unsubscribe(channel)          # too slow: dropped, not queued


def serve(jarvis: Jarvis, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
          app_dir: str = ""):
    """Bind the API. Loopback only — this can confirm a pending command."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    api = Api(jarvis)
    hub = Hub()
    here = app_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hud")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):            # quiet
            pass

        def _json(self, code: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _token(self) -> str:
            header = self.headers.get("X-Jarvis-Token") or ""
            if header:
                return header
            auth = self.headers.get("Authorization") or ""
            return auth[7:] if auth.startswith("Bearer ") else ""

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/events":
                return self._stream()
            if path.startswith("/api/"):
                code, payload = api.handle("GET", self.path, token=self._token())
                return self._json(code, payload)
            return self._page(path)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                return self._json(400, {"error": "body is not JSON"})
            code, payload = api.handle("POST", self.path, body, self._token())
            self._json(code, payload)

        def _page(self, path: str) -> None:
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            target = os.path.normpath(os.path.join(here, name))
            if not target.startswith(here) or not os.path.isfile(target):
                return self._json(404, {"error": "no such page"})
            with open(target, "rb") as fh:
                body = fh.read()
            if target.endswith(".html"):
                # The page is served by the same process that minted the
                # token, so it can carry it. Nothing else can read it.
                body = body.replace(
                    b"</head>",
                    f'<script>window.JARVIS_TOKEN="{jarvis.token}";'
                    f'</script></head>'.encode(), 1)
            kind = ("text/html" if target.endswith(".html")
                    else "text/css" if target.endswith(".css")
                    else "application/javascript" if target.endswith(".js")
                    else "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream(self) -> None:
            channel = hub.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self.wfile.write(
                    f"data: {json.dumps(jarvis.snapshot(), default=str)}\n\n"
                    .encode())
                self.wfile.flush()
                while True:
                    try:
                        line = channel.get(timeout=20.0)
                    except Exception:
                        self.wfile.write(b": keep-alive\n\n")
                    else:
                        self.wfile.write(f"data: {line}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                hub.unsubscribe(channel)

    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        if exc.errno in (98, 48):            # EADDRINUSE on Linux, macOS
            raise PortBusy(host, port) from exc
        raise
    server.daemon_threads = True
    server.jarvis = jarvis          # type: ignore[attr-defined]
    server.hub = hub                # type: ignore[attr-defined]
    return server
