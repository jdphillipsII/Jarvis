"""Talking to a running JARVIS, when there is one.

The CLI prefers the daemon and falls back to building its own. That is not
only about speed — though a command that reaches a warm process answers
instantly instead of importing the world. It is that **a proposal raised in
one process cannot be confirmed in another**, so a CLI that always built its
own could never answer something the voice loop had asked.

Nothing here is required. If no daemon is listening, every call raises
`NotRunning` and the caller does what it always did.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from daemon.service import DEFAULT_PORT, read_token


class NotRunning(RuntimeError):
    """Nothing is listening. Not an error — a fact to branch on."""


class Client:
    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                 token: Optional[str] = None, timeout: float = 5.0):
        self.base = f"http://{host}:{port}"
        self.token = token if token is not None else read_token()
        self.timeout = timeout

    def _call(self, method: str, path: str,
              body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json",
                     "X-Jarvis-Token": self.token})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as reply:
                return json.loads(reply.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read().decode() or "{}")
            except ValueError:
                return {"error": f"HTTP {exc.code}"}
        except OSError as exc:
            raise NotRunning(str(exc)) from exc

    def running(self) -> bool:
        try:
            self._call("GET", "/api/state")
            return True
        except NotRunning:
            return False

    def state(self) -> Dict[str, Any]:
        return self._call("GET", "/api/state")

    def tools(self) -> Dict[str, Any]:
        return self._call("GET", "/api/tools")

    def proposals(self) -> Dict[str, Any]:
        return self._call("GET", "/api/proposals")

    def invoke(self, tool: str, args: Optional[Dict[str, Any]] = None):
        return self._call("POST", "/api/invoke", {"tool": tool, "args": args or {}})

    def answer(self, proposal_id: str, answer: str) -> Dict[str, Any]:
        return self._call("POST", "/api/answer",
                          {"id": proposal_id, "answer": answer})
