"""Consent for anything that changes the world.

Three behaviours taken from Axon's orchestrator, each of which exists because
the naive version is actively bad:

    expiry is a STATE, not an error  — confirming something from an hour ago
                                       should read 'that's expired, sir', not
                                       throw
    re-confirming is idempotent      — a second confirm (from voice and the
                                       HUD at once) returns the original
                                       result rather than running it twice
    confirm never raises             — it returns a status, always, so a
                                       broken handler cannot crash the surface
                                       that called it
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

from .tools import Tool, ToolResult


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    EXECUTED = "executed"
    EXPIRED = "expired"
    FAILED = "failed"
    DECLINED = "declined"


@dataclass
class Proposal:
    id: str
    tool: str
    args: Dict[str, Any]
    summary: str
    confirm_label: str = "Confirm"
    risk: str = ""
    status: ProposalStatus = ProposalStatus.PROPOSED
    created_at: float = 0.0
    expires_at: float = 0.0
    result: Optional[ToolResult] = None

    @property
    def is_terminal(self) -> bool:
        return self.status is not ProposalStatus.PROPOSED


class ProposalStore:
    """In-memory. A desktop assistant restarting is a fine reason to forget
    what it was about to do."""

    def __init__(self, ttl_s: float = 300.0,
                 clock: Callable[[], float] = time.monotonic):
        self.ttl_s = ttl_s
        self._clock = clock
        self._items: Dict[str, Proposal] = {}

    def create(self, tool: Tool, args: Dict[str, Any], summary: str) -> Proposal:
        now = self._clock()
        p = Proposal(id=uuid.uuid4().hex[:12], tool=tool.name, args=dict(args),
                     summary=summary, confirm_label=tool.confirm_label,
                     risk=tool.risk, created_at=now, expires_at=now + self.ttl_s)
        self._items[p.id] = p
        return p

    def get(self, proposal_id: str) -> Optional[Proposal]:
        return self._items.get(proposal_id)

    def pending(self) -> list:
        return [p for p in self._items.values()
                if p.status is ProposalStatus.PROPOSED and not self._is_expired(p)]

    def decline(self, proposal_id: str) -> Optional[Proposal]:
        p = self._items.get(proposal_id)
        if p and not p.is_terminal:
            p.status = ProposalStatus.DECLINED
        return p

    def _is_expired(self, p: Proposal) -> bool:
        return self._clock() >= p.expires_at

    def confirm(self, proposal_id: str,
                execute: Callable[[Proposal], ToolResult]) -> Proposal:
        """Never raises. Always returns a Proposal carrying a status."""
        p = self._items.get(proposal_id)
        if p is None:
            return Proposal(id=proposal_id, tool="", args={},
                            summary="No such proposal, sir.",
                            status=ProposalStatus.EXPIRED)
        if p.is_terminal:
            return p                                   # idempotent
        if self._is_expired(p):
            p.status = ProposalStatus.EXPIRED
            return p
        try:
            p.result = execute(p)
            p.status = (ProposalStatus.EXECUTED if p.result.ok
                        else ProposalStatus.FAILED)
        except Exception as exc:                       # a broken handler must
            p.result = ToolResult(False, error=str(exc))   # not crash the caller
            p.status = ProposalStatus.FAILED
        return p
