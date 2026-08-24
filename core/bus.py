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


class Bus:
    """Subscribers register per-intent or with '*' for everything."""

    def __init__(self, registry: Optional[Registry] = None, enforce: bool = True):
        self.registry = registry
        self.enforce = enforce
        self._subs: Dict[str, List[Handler]] = {}
        self._lock = threading.RLock()
        self.rejected: List[Tuple[Intent, str]] = []
        self.errors: List[Tuple[str, BaseException]] = []

    # ---- wiring ----
    def subscribe(self, pattern: str, handler: Handler) -> Handler:
        with self._lock:
            self._subs.setdefault(pattern, []).append(handler)
        return handler

    def on(self, pattern: str) -> Callable[[Handler], Handler]:
        """Decorator form:  @bus.on("workspace.next")"""
        def deco(fn: Handler) -> Handler:
            self.subscribe(pattern, fn)
            return fn
        return deco

    # ---- dispatch ----
    def publish(self, intent: Intent) -> bool:
        """Returns True if delivered, False if the registry refused it."""
        if self.enforce and self.registry is not None:
            reason: Optional[Rejection] = self.registry.check(intent)
            if reason:
                self.rejected.append((intent, str(reason)))
                log.info("rejected: %s", reason)
                return False

        with self._lock:
            handlers = list(self._subs.get(intent.intent, ())) + list(self._subs.get("*", ()))

        for fn in handlers:
            try:
                fn(intent)
            except Exception as exc:                      # isolate: one bad actuator
                name = getattr(fn, "__name__", repr(fn))  # must not starve the rest
                self.errors.append((name, exc))
                log.exception("handler %s failed on %s", name, intent.intent)
        return True

    def publish_line(self, line: str) -> bool:
        """Parse a wire line and publish it. Malformed input is dropped, not raised."""
        try:
            return self.publish(Intent.from_line(line))
        except InvalidIntent as exc:
            log.warning("dropped malformed intent: %s", exc)
            return False


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
