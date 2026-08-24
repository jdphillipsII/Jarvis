"""The one message shape that crosses the bus.

Sources publish Intents; actuators subscribe. Nothing else is allowed on the
wire. See intents/CONTRACT.md.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict

# Sources are advisory labels only — never use one for authorization.
SOURCES = ("gesture", "voice", "presence", "system", "test")


class InvalidIntent(ValueError):
    """Malformed message. Sources get this; the bus never propagates it."""


@dataclass(frozen=True)
class Intent:
    intent: str
    source: str = "system"
    confidence: float = 1.0
    args: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.intent or "." not in self.intent:
            raise InvalidIntent(f"intent must be namespaced 'group.verb': {self.intent!r}")
        if self.source not in SOURCES:
            raise InvalidIntent(f"unknown source {self.source!r}, expected one of {SOURCES}")
        if not 0.0 <= self.confidence <= 1.0:
            raise InvalidIntent(f"confidence out of range: {self.confidence}")
        if not isinstance(self.args, dict):
            raise InvalidIntent("args must be a dict")

    # ---- wire format: one JSON object per line ----
    def to_line(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_line(cls, line: str) -> "Intent":
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            raise InvalidIntent(f"not JSON: {e}") from e
        if not isinstance(raw, dict):
            raise InvalidIntent("wire message must be a JSON object")
        known = {"intent", "source", "confidence", "args", "ts"}
        unknown = set(raw) - known
        if unknown:
            raise InvalidIntent(f"unknown fields: {sorted(unknown)}")
        return cls(**raw)
