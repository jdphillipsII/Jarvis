"""The proactive loop: watch, judge, offer.

    watchers -> Observations -> SpeakPolicy -> Delivery -> intent bus

Nothing here decides *what* to say (watchers do) or *whether the moment allows
it* (policy does). This is only the wiring, plus the briefing queue that holds
everything policy deferred.
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from core.bus import Bus
from core.intent import Intent
from core.observation import Observation
from core.policy import Delivery, DeliveryContext, SpeakPolicy, Urgency
from core.sources import CollectResult, SourceRunner, SourceSpec

_DELIVERY_INTENT = {
    Delivery.CHIME: "jarvis.offer",
    Delivery.BADGE: "jarvis.badge",
    Delivery.BATCH: "jarvis.batch",
}


@dataclass
class Briefing:
    """What policy deferred, waiting to be read back on request."""
    held: List[Observation] = field(default_factory=list)

    def add(self, obs: Observation) -> None:
        self.held.append(obs)

    def drain(self) -> List[Observation]:
        out, self.held = self.held, []
        return out

    def summary(self) -> str:
        if not self.held:
            return "Nothing held, sir."
        by_urgency = sorted(self.held, key=lambda o: list(Urgency).index(o.urgency),
                            reverse=True)
        lines = "; ".join(o.text for o in by_urgency[:5])
        extra = f" And {len(self.held) - 5} more." if len(self.held) > 5 else ""
        return f"While you were away, sir: {lines}.{extra}"

    def __len__(self) -> int:
        return len(self.held)


@dataclass
class ProactiveDaemon:
    bus: Bus
    policy: SpeakPolicy = field(default_factory=SpeakPolicy)
    runner: SourceRunner = field(default_factory=SourceRunner)
    briefing: Briefing = field(default_factory=Briefing)
    context_fn: Callable[[], DeliveryContext] = DeliveryContext.from_clock

    def tick(self, specs: Optional[List[SourceSpec]] = None) -> CollectResult:
        """One pass: collect, judge each observation, route the survivors."""
        result = self.runner.collect(specs)
        ctx = self.context_fn()

        for obs in result.observations:
            decision = self.policy.decide(obs.urgency, ctx,
                                          category=obs.category, key=obs.key)
            if decision.delivery is Delivery.SUPPRESS:
                continue

            self.policy.record(obs.category, obs.key)

            if decision.delivery is Delivery.BATCH:
                self.briefing.add(obs)

            self.bus.publish(Intent(
                _DELIVERY_INTENT[decision.delivery],
                source="system",
                confidence=1.0,
                args={"text": obs.text, "urgency": obs.urgency.value,
                      "category": obs.category, "reason": decision.reason},
            ))
        return result
