"""What the HUD is showing, as data.

The operational state is the single most important value here: it drives the
entire visual language, so it must be derived from one place with one rule
rather than re-decided by whatever widget happens to be rendering.

    CRITICAL  something needs you now
    FOCUSED   deep work — the HUD goes quiet even if there is pending noise
    ELEVATED  something wants attention when convenient
    CALM      nothing to say

Precedence is deliberate: CRITICAL outranks FOCUSED, because the one thing
allowed to break flow is the thing that would cost more to miss. FOCUSED
outranks ELEVATED, because a warning you have already decided to defer should
not keep the room amber while you work.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

from .policy import Urgency

MAX_FEED = 40


class OpState(str, Enum):
    CALM = "calm"
    ELEVATED = "elevated"
    CRITICAL = "critical"
    FOCUSED = "focused"


@dataclass
class Card:
    """One thing on the HUD. An offer is a card you can answer."""
    id: str
    text: str
    urgency: Urgency = Urgency.INFO
    category: str = "general"
    reason: str = ""
    kind: str = "badge"                 # badge | offer
    ts: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text, "urgency": self.urgency.value,
                "category": self.category, "reason": self.reason,
                "kind": self.kind, "ts": self.ts}


@dataclass
class HudState:
    offers: List[Card] = field(default_factory=list)
    feed: Deque[Card] = field(default_factory=lambda: deque(maxlen=MAX_FEED))
    telemetry: Dict[str, Any] = field(default_factory=dict)
    present: bool = True
    focused: bool = False
    listening: bool = False
    held: int = 0

    # ---- mutation ----
    def add(self, card: Card) -> None:
        if card.kind == "offer":
            self.offers = [o for o in self.offers if o.id != card.id] + [card]
        self.feed.appendleft(card)

    def resolve(self, offer_id: str) -> Optional[Card]:
        for i, offer in enumerate(self.offers):
            if offer.id == offer_id:
                return self.offers.pop(i)
        return None

    # ---- derivation ----
    def op_state(self) -> OpState:
        if any(o.urgency is Urgency.CRITICAL for o in self.offers):
            return OpState.CRITICAL
        if self.focused:
            return OpState.FOCUSED
        if self.offers:
            return OpState.ELEVATED
        return OpState.CALM

    def snapshot(self) -> Dict[str, Any]:
        return {"state": self.op_state().value,
                "offers": [o.as_dict() for o in self.offers],
                "feed": [c.as_dict() for c in list(self.feed)[:12]],
                "telemetry": self.telemetry, "present": self.present,
                "focused": self.focused, "listening": self.listening,
                "held": self.held}
