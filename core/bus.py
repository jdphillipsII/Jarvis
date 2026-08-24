"""In-process pub/sub plus a line-oriented socket transport.

Design rule from the contract: an actuator that raises must never take down the
bus or starve its siblings. Each handler is isolated; failures are counted and
reported, never propagated.
"""
from __future__ import annotations

import logging
import socket
import threading
from typing import Callable, Dict, List, Optional, Tuple

from .intent import Intent, InvalidIntent
from .registry import Registry, Rejection

log = logging.getLogger("jarvis.bus")

Handler = Callable[[Intent], None]


def matches(pattern: str, name: str) -> bool:
    """Hierarchical match:  '*' -> everything,  'model.*' -> the model group."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return name.startswith(pattern[:-1])
    return pattern == name


class Bus:
    """Subscribers register an exact intent, a 'group.*' prefix, or '*'."""

    def __init__(self, registry: Optional[Registry] = None, enforce: bool = True):
        self.registry = registry
        self.enforce = enforce
        self._subs: List[Tuple[str, str, Handler]] = []   # (id, pattern, handler)
        self._lock = threading.RLock()
        self._n = 0
        self.delivered = 0
        self.rejected: List[Tuple[Intent, str]] = []
        self.errors: List[Tuple[str, BaseException]] = []

    # ---- wiring ----
    def subscribe(self, pattern: str, handler: Handler, subscriber_id: str = "") -> str:
        with self._lock:
            self._n += 1
            sid = subscriber_id or f"sub-{self._n}"
            self._subs.append((sid, pattern, handler))
        return sid

    def unsubscribe(self, subscriber_id: str) -> bool:
        with self._lock:
            before = len(self._subs)
            self._subs = [s for s in self._subs if s[0] != subscriber_id]
            return len(self._subs) != before

    def on(self, pattern: str) -> Callable[[Handler], Handler]:
        """Decorator form:  @bus.on("workspace.*")"""
        def deco(fn: Handler) -> Handler:
            self.subscribe(pattern, fn)
            return fn
        return deco

    # ---- dispatch ----
    def publish(self, intent: Intent) -> bool:
        """True if delivered, False if the registry refused it."""
        if self.enforce and self.registry is not None:
            reason: Optional[Rejection] = self.registry.check(intent)
            if reason:
                self.rejected.append((intent, str(reason)))
                log.info("rejected: %s", reason)
                return False

        # Snapshot under the lock, then call OUTSIDE it, so a handler that
        # re-publishes cannot deadlock the bus.
        with self._lock:
            handlers = [(sid, fn) for sid, pat, fn in self._subs
                        if matches(pat, intent.intent)]

        for sid, fn in handlers:
            try:
                fn(intent)
            except Exception as exc:                    # isolate: one bad actuator
                self.errors.append((sid, exc))          # must not starve the rest
                log.exception("handler %s failed on %s", sid, intent.intent)
        self.delivered += 1
        return True

    def publish_line(self, line: str) -> bool:
        """Parse a wire line and publish. Malformed input is dropped, not raised."""
        try:
            return self.publish(Intent.from_line(line))
        except InvalidIntent as exc:
            log.warning("dropped malformed intent: %s", exc)
            return False

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"subscribers": len(self._subs), "delivered": self.delivered,
                    "rejected": len(self.rejected), "errors": len(self.errors)}


class SocketSource(threading.Thread):
    """Reads newline-delimited intents from a unix socket into a Bus.

    Lets out-of-process sources (the vision daemon, a CLI, a KWin script)
    publish without importing anything.
    """

    def __init__(self, bus: Bus, path: str):
        super().__init__(daemon=True, name="jarvis-socket-source")
        self.bus, self.path = bus, path
        self._sock: Optional[socket.socket] = None
        self._stop = threading.Event()

    def start(self) -> "SocketSource":
        import os
        if os.path.exists(self.path):
            os.unlink(self.path)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self.path)
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        super().start()
        return self

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        with conn, conn.makefile("r") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    self.bus.publish_line(line)

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            self._sock.close()


def send(path: str, intent: Intent) -> None:
    """Fire-and-forget publish from another process."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(path)
        s.sendall((intent.to_line() + "\n").encode())
