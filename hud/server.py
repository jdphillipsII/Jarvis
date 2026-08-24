#!/usr/bin/env python3
"""Serves the HUD and bridges it to the intent bus.

Stdlib only — http.server plus Server-Sent Events. SSE rather than WebSockets
because the traffic is one-directional apart from two button presses, and not
adding a dependency to the thing that must always be running is worth more
than the elegance.

    GET  /            the HUD
    GET  /events      SSE stream of state snapshots
    POST /answer      {"id": ..., "answer": "confirm"|"decline"}

Binds to 127.0.0.1 only. This exposes proposal confirmation, so it must not be
reachable from the network.
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.hud_state import Card, HudState
from core.intent import Intent
from core.policy import Urgency

HERE = os.path.dirname(os.path.abspath(__file__))


class Hub:
    """Fan-out to connected browsers. Slow clients get dropped, never queued
    forever — a stalled tab must not grow memory without bound."""

    def __init__(self, state: HudState):
        self.state = state
        self._clients: List[queue.Queue] = []
        self._lock = threading.Lock()
        self.on_answer: Optional[Callable[[str, str], None]] = None

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=32)
        with self._lock:
            self._clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)

    def broadcast(self) -> None:
        payload = json.dumps(self.state.snapshot())
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                self.unsubscribe(q)

    # ---- bus entry points ----
    def on_intent(self, intent: Intent) -> None:
        args = intent.args
        kind = "offer" if intent.intent == "jarvis.offer" else "badge"
        self.state.add(Card(
            id=args.get("id") or f"{args.get('category','general')}:{args.get('text','')[:24]}",
            text=args.get("text", ""),
            urgency=Urgency(args.get("urgency", "info")),
            category=args.get("category", "general"),
            reason=args.get("reason", ""), kind=kind, ts=time.time()))
        self.broadcast()

    def on_presence(self, intent: Intent) -> None:
        self.state.present = intent.intent == "presence.arrived"
        self.broadcast()

    def set_telemetry(self, data: Dict[str, Any]) -> None:
        self.state.telemetry = data
        self.broadcast()


def make_handler(hub: Hub):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):        # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/events"):
                return self._stream()
            if self.path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as fh:
                    return self._send(200, fh.read(), "text/html; charset=utf-8")
            if self.path == "/state":
                return self._send(200, json.dumps(hub.state.snapshot()).encode(),
                                  "application/json")
            self._send(404, b"not found", "text/plain")

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = hub.subscribe()
            try:
                self.wfile.write(f"data: {json.dumps(hub.state.snapshot())}\n\n"
                                 .encode())
                self.wfile.flush()
                while True:
                    try:
                        payload = q.get(timeout=15)
                        self.wfile.write(f"data: {payload}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")   # keep proxies honest
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                hub.unsubscribe(q)

        def do_POST(self):
            if self.path != "/answer":
                return self._send(404, b"not found", "text/plain")
            length = int(self.headers.get("Content-Length", 0) or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, b'{"ok":false}', "application/json")
            offer_id, answer = str(body.get("id", "")), str(body.get("answer", ""))
            if answer not in ("confirm", "decline"):
                return self._send(400, b'{"ok":false}', "application/json")
            hub.state.resolve(offer_id)
            if hub.on_answer:
                hub.on_answer(offer_id, answer)
            hub.broadcast()
            self._send(200, b'{"ok":true}', "application/json")
    return Handler


def serve(hub: Hub, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(hub))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True,
                     name="jarvis-hud").start()
    return httpd
