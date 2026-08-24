"""The gate every tool call passes through.

Order matters and is not negotiable: agency, then existence, then schema, then
consent. Each check is cheap and refuses before the next one runs, so a call
that shouldn't happen dies as early as possible.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .proposals import Proposal, ProposalStore
from .tools import Agency, Tool, ToolRegistry, ToolResult

log = logging.getLogger("jarvis.toolbox")

Outcome = Union[ToolResult, Proposal]


@dataclass
class Toolbox:
    registry: ToolRegistry
    agency: Agency = Agency.ADVISORY
    proposals: ProposalStore = field(default_factory=ProposalStore)

    # ---- what the model is allowed to know about ----
    def schemas(self) -> List[Dict[str, Any]]:
        return self.registry.schemas(self.agency)

    def catalogue(self) -> str:
        """Rendered for the system prompt. One source of truth for both the
        parser and the model's idea of what it can do."""
        tools = self.registry.available(self.agency)
        if not tools:
            return "You have no tools available."
        return "\n".join(f"- {t.name}: {t.description}" for t in sorted(
            tools, key=lambda t: t.name))

    # ---- the gate ----
    def invoke(self, name: str, args: Optional[Dict[str, Any]] = None) -> Outcome:
        args = dict(args or {})
        tool = self.registry.get(name)

        # 1. Existence and agency, in that order but reported the same way:
        #    never reveal that a tool exists above the user's agency level.
        if tool is None or tool.min_agency > self.agency:
            return ToolResult(False, error=f"no such tool: {name}")

        # 2. Schema.
        if (problem := tool.validate(args)):
            return ToolResult(False, error=problem)

        # 3. Consent.
        if tool.mutates:
            return self.proposals.create(tool, args, self._summarise(tool, args))

        return self._run(tool, args)

    def confirm(self, proposal_id: str) -> Proposal:
        def execute(p: Proposal) -> ToolResult:
            tool = self.registry.get(p.tool)
            if tool is None or tool.min_agency > self.agency:
                return ToolResult(False, error="tool is no longer available")
            return self._run(tool, p.args)
        return self.proposals.confirm(proposal_id, execute)

    def decline(self, proposal_id: str) -> Optional[Proposal]:
        return self.proposals.decline(proposal_id)

    # ---- execution ----
    @staticmethod
    def _run(tool: Tool, args: Dict[str, Any]) -> ToolResult:
        try:
            return ToolResult(True, value=tool.handler(**args))
        except Exception as exc:
            log.exception("tool %s failed", tool.name)
            return ToolResult(False, error=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _summarise(tool: Tool, args: Dict[str, Any]) -> str:
        rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(args.items()))
        return f"{tool.description}" + (f" ({rendered})" if rendered else "")
