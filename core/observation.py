"""What a watcher noticed. The unit of proactive intelligence."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from .policy import Urgency


@dataclass(frozen=True)
class Observation:
    text: str                       # what JARVIS would say, already phrased
    urgency: Urgency = Urgency.INFO
    category: str = "general"       # for muting and cooldown scoping
    key: str = ""                   # STABLE identity — cooldowns hash on this,
                                    # so it must not contain changing values
    detail: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("observation needs text")
