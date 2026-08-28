"""What JARVIS can actually do.

Three layers of restraint, in order, before anything runs:

    1. AGENCY   a tool above the configured level is never even shown to the
                model. It cannot call what it cannot see, so a jailbroken
                prompt has nothing to reach for.
    2. SCHEMA   arguments are validated before the handler is entered.
    3. CONSENT  anything mutating returns a Proposal, not a result. The user
                confirms; only then does it execute.

Agency is the ceiling set in config/jarvis.env. Raising it is a deliberate act
by the user, never something the assistant can do for itself.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional


class Agency(IntEnum):
    """Ordered: each level includes everything below it."""
    ADVISORY = 0     # read and report, no side effects
    ACTUATOR = 1     # drive the desktop and the workshop, from a fixed list
    AGENTIC = 2      # arbitrary shell and filesystem

    @classmethod
    def parse(cls, text: str) -> "Agency":
        try:
            return cls[str(text).strip().upper()]
        except KeyError:
            return cls.ADVISORY          # unknown value fails closed


JSON_TYPES = {"string": str, "number": (int, float), "integer": int,
              "boolean": bool, "array": list, "object": dict}


@dataclass(frozen=True)
class Tool:
    name: str                                   # "workspace.activity"
    description: str                            # the model reads this
    handler: Callable[..., Any]
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    required: tuple = ()
    min_agency: Agency = Agency.ADVISORY
    mutates: bool = False                       # mutating => needs confirmation
    confirm_label: str = "Confirm"
    risk: str = ""

    def schema(self) -> Dict[str, Any]:
        """OpenAI/Ollama-style function schema."""
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.parameters,
                           "required": list(self.required)}}}

    def validate(self, args: Dict[str, Any]) -> Optional[str]:
        """None if valid, else a human-readable reason."""
        missing = [k for k in self.required if k not in args]
        if missing:
            return f"missing required argument(s): {', '.join(missing)}"
        unknown = [k for k in args if k not in self.parameters]
        if unknown:
            return f"unknown argument(s): {', '.join(sorted(unknown))}"
        for key, value in args.items():
            want = self.parameters[key].get("type")
            py = JSON_TYPES.get(want)
            if py and not isinstance(value, py):
                return f"argument '{key}' must be {want}"
            allowed = self.parameters[key].get("enum")
            if allowed and value not in allowed:
                return f"argument '{key}' must be one of {allowed}"
        return None


@dataclass
class ToolResult:
    ok: bool
    value: Any = None
    error: str = ""

    def __bool__(self) -> bool:
        return self.ok


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def add(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def register(self, name: str, description: str, **kw):
        """Decorator form."""
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.add(Tool(name=name, description=description, handler=fn, **kw))
            return fn
        return deco

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def available(self, agency: Agency) -> List[Tool]:
        """Only what this agency level permits — the model sees nothing else."""
        return [t for t in self._tools.values() if t.min_agency <= agency]

    def schemas(self, agency: Agency) -> List[Dict[str, Any]]:
        return [t.schema() for t in self.available(agency)]

    def __len__(self) -> int:
        return len(self._tools)
