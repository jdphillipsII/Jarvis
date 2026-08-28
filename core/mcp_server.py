"""Exposing JARVIS's tools over MCP.

MCP is the interface Hermes Agent, Claude Desktop and most other agents already
speak, so publishing the toolbox this way makes JARVIS's body — desktop
control, the workshop, notes, telemetry — available to any of them without
writing a bespoke bridge for each.

The consent model survives the crossing, which is the part that matters. A
mutating tool called over MCP does NOT execute: it returns a proposal and an
id, and a separate confirm call runs it. An external agent therefore cannot do
anything irreversible without a second, deliberate act — the same guarantee the
voice path has.

Stdlib only: MCP over stdio is newline-delimited JSON-RPC 2.0, which is not
worth a dependency in the thing that has to be running for everything else.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional, TextIO

from .proposals import Proposal, ProposalStatus
from .toolbox import Toolbox
from .tools import ToolResult

PROTOCOL_VERSION = "2024-11-05"

# MCP tool names are conventionally underscore-separated; ours are dotted.
def _external(name: str) -> str:
    return name.replace(".", "_")


CONFIRM = "jarvis_confirm"
DECLINE = "jarvis_decline"


class McpServer:
    """Protocol handling is pure — `handle` maps a request to a response, so
    the whole surface is tested without pipes or a client."""

    def __init__(self, toolbox: Toolbox, name: str = "jarvis",
                 version: str = "0.1.0"):
        self.toolbox = toolbox
        self.name, self.version = name, version

    # ---- tool listing ----
    def _tools(self) -> List[Dict[str, Any]]:
        out = []
        for tool in self.toolbox.registry.available(self.toolbox.agency):
            desc = tool.description
            if tool.mutates:
                desc += (" — returns a proposal that must be confirmed with "
                         f"{CONFIRM}; calling this does not execute anything.")
            out.append({"name": _external(tool.name), "description": desc,
                        "inputSchema": {"type": "object",
                                        "properties": tool.parameters,
                                        "required": list(tool.required)}})
        out.append({
            "name": CONFIRM,
            "description": "Execute a previously returned proposal by its id.",
            "inputSchema": {"type": "object",
                            "properties": {"proposal_id": {"type": "string"}},
                            "required": ["proposal_id"]}})
        out.append({
            "name": DECLINE,
            "description": "Discard a proposal without executing it.",
            "inputSchema": {"type": "object",
                            "properties": {"proposal_id": {"type": "string"}},
                            "required": ["proposal_id"]}})
        return out

    def _internal(self, external: str) -> Optional[str]:
        for tool in self.toolbox.registry.available(self.toolbox.agency):
            if _external(tool.name) == external:
                return tool.name
        return None

    # ---- dispatch ----
    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name == CONFIRM:
            done = self.toolbox.confirm(str(args.get("proposal_id", "")))
            return self._render_proposal(done)
        if name == DECLINE:
            p = self.toolbox.decline(str(args.get("proposal_id", "")))
            return _text("Declined." if p else "No such proposal.")

        internal = self._internal(name)
        if internal is None:
            # Same wording whether it is unknown or above this agency level —
            # never confirm the existence of a capability that is gated off.
            return _text(f"no such tool: {name}", is_error=True)

        outcome = self.toolbox.invoke(internal, args)
        if isinstance(outcome, Proposal):
            return _text(json.dumps({
                "status": "proposal", "proposal_id": outcome.id,
                "summary": outcome.summary, "risk": outcome.risk,
                "confirm_with": CONFIRM}, indent=2))
        return self._render_result(outcome)

    @staticmethod
    def _render_result(r: ToolResult) -> Dict[str, Any]:
        if not r.ok:
            return _text(r.error, is_error=True)
        value = r.value
        if not isinstance(value, str):
            try:
                value = json.dumps(value, default=str, indent=2)
            except (TypeError, ValueError):
                value = str(value)
        return _text(value)

    @staticmethod
    def _render_proposal(p: Proposal) -> Dict[str, Any]:
        if p.status is ProposalStatus.EXECUTED and p.result:
            return McpServer._render_result(p.result)
        detail = p.result.error if p.result else ""
        return _text(f"{p.status.value}{': ' + detail if detail else ''}",
                     is_error=p.status is not ProposalStatus.EXECUTED)

    # ---- JSON-RPC ----
    def handle(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """None means 'notification, no reply'."""
        method, rid = request.get("method"), request.get("id")
        params = request.get("params") or {}

        if method == "initialize":
            result = {"protocolVersion": PROTOCOL_VERSION,
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": self.name, "version": self.version}}
        elif method == "tools/list":
            result = {"tools": self._tools()}
        elif method == "tools/call":
            result = self.call_tool(params.get("name", ""),
                                    params.get("arguments") or {})
        elif method == "ping":
            result = {}
        elif rid is None:
            return None                        # any other notification
        else:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"unknown method: {method}"}}

        if rid is None:
            return None
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    # ---- stdio loop ----
    def serve(self, stdin: TextIO = None, stdout: TextIO = None) -> None:
        stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue                        # malformed frame: ignore, stay up
            try:
                response = self.handle(request)
            except Exception as exc:            # a bad call must not end the session
                response = {"jsonrpc": "2.0", "id": request.get("id"),
                            "error": {"code": -32603, "message": str(exc)}}
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()


def _text(body: str, is_error: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {"content": [{"type": "text", "text": body}]}
    if is_error:
        out["isError"] = True
    return out
