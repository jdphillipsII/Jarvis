"""Speaking MCP to somebody else's server.

`mcp_server.py` publishes our body to other agents. This is the mirror: it
lets JARVIS consume tools that live somewhere else — a build123d server, a
FreeCAD driver, or the SolidWorks bridge on the Windows half of the dual boot.

The survey in docs/PRIOR_ART.md is the reason this exists. The CAD-driver
layer is commodity; writing our own would be a waste. But a borrowed tool
arrives with no idea what it is allowed to do, so nothing here decides that —
see `bridges.py`, which refuses to mount a tool it has not been told how to
classify. This module only moves bytes.

Protocol handling is pure: `McpClient` takes a transport, and the transport is
a callable in the tests. No pipes, no sockets, no CAD program.
"""
from __future__ import annotations

import json
import logging
import subprocess
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

log = logging.getLogger("jarvis.mcp_client")

PROTOCOL_VERSION = "2024-11-05"


class McpError(RuntimeError):
    """The far end said no, or said something unintelligible."""


@dataclass(frozen=True)
class RemoteTool:
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    annotations: Dict[str, Any] = field(default_factory=dict)

    @property
    def properties(self) -> Dict[str, Any]:
        return dict(self.input_schema.get("properties") or {})

    @property
    def required(self) -> tuple:
        return tuple(self.input_schema.get("required") or ())

    @property
    def read_only(self) -> Optional[bool]:
        """What the server claims about itself, or None if it claims nothing.

        Advisory only — `bridges.py` uses it to catch a *disagreement* with our
        own classification, never as the classification itself.
        """
        hint = self.annotations.get("readOnlyHint")
        if isinstance(hint, bool):
            return hint
        destructive = self.annotations.get("destructiveHint")
        if isinstance(destructive, bool):
            return not destructive
        return None


# A transport maps one JSON-RPC request object to one response object.
Transport = Callable[[Dict[str, Any]], Dict[str, Any]]


class McpClient:
    def __init__(self, transport: Transport, name: str = "remote"):
        self._transport = transport
        self.name = name
        self._id = 0
        self.server_info: Dict[str, Any] = {}

    # ---- JSON-RPC ----
    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._id += 1
        request = {"jsonrpc": "2.0", "id": self._id, "method": method,
                   "params": params or {}}
        response = self._transport(request)
        if not isinstance(response, dict):
            raise McpError(f"{self.name}: malformed response to {method}")
        if "error" in response:
            err = response["error"] or {}
            raise McpError(f"{self.name}: {err.get('message', 'unknown error')}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise McpError(f"{self.name}: no result in response to {method}")
        return result

    # ---- handshake ----
    def initialize(self) -> Dict[str, Any]:
        result = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "jarvis", "version": "0.1.0"}})
        self.server_info = dict(result.get("serverInfo") or {})
        return self.server_info

    def list_tools(self) -> List[RemoteTool]:
        out: List[RemoteTool] = []
        for raw in self._rpc("tools/list").get("tools") or []:
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            out.append(RemoteTool(
                name=str(raw["name"]),
                description=str(raw.get("description") or ""),
                input_schema=dict(raw.get("inputSchema") or {}),
                annotations=dict(raw.get("annotations") or {})))
        return out

    def call_tool(self, name: str, args: Optional[Dict[str, Any]] = None) -> Any:
        result = self._rpc("tools/call", {"name": name, "arguments": args or {}})
        body = _content(result)
        if result.get("isError"):
            raise McpError(body if isinstance(body, str) else json.dumps(body))
        return body


def _content(result: Dict[str, Any]) -> Any:
    """MCP returns content blocks. Give back structure when there is any.

    A server that answers with a JSON document should reach our tool layer as a
    dict, not as a string that happens to look like one — the model reads it
    either way, but only one of them can be indexed downstream.
    """
    blocks = result.get("content")
    if not isinstance(blocks, list):
        return result
    texts = [b.get("text", "") for b in blocks
             if isinstance(b, dict) and b.get("type") == "text"]
    body = "\n".join(t for t in texts if t)
    if not body:
        return result
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        return body


# ---------------------------------------------------------------- transports

class StdioTransport:
    """A server we launch ourselves and talk to over its pipes.

    Non-JSON lines on stdout are skipped rather than treated as a frame: a
    surprising number of servers print a banner before they start speaking.
    """

    def __init__(self, command: Sequence[str], cwd: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None):
        self.command = list(command)
        self._proc = subprocess.Popen(
            self.command, cwd=cwd, env=env, text=True, bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)

    def __call__(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if self._proc.poll() is not None:
            raise McpError(f"{self.command[0]} exited (rc={self._proc.returncode})")
        assert self._proc.stdin and self._proc.stdout
        self._proc.stdin.write(json.dumps(request) + "\n")
        self._proc.stdin.flush()
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise McpError(f"{self.command[0]} closed its output")
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


class HttpTransport:
    """A server reachable over the network — the SolidWorks bridge, over the
    tailnet, on the Windows side of the dual boot."""

    def __init__(self, url: str, timeout_s: float = 30.0,
                 headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.timeout_s = timeout_s
        self.headers = {"Content-Type": "application/json", **(headers or {})}

    def __call__(self, request: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(request).encode()
        req = urllib.request.Request(self.url, data=body, headers=self.headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode())
        except OSError as exc:
            raise McpError(f"{self.url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise McpError(f"{self.url}: response was not JSON") from exc

    def close(self) -> None:
        pass
