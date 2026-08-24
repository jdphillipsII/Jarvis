"""What JARVIS says when you sit down.

Subscribes to presence and turns arrival into either silence, a greeting, or a
greeting plus everything policy held while you were gone.

The restraint here is the whole point. Three separate gates have to agree
before he says anything: you were away long enough to warrant it (tracker),
the hour allows it (policy), and there is something worth saying. Any one of
them failing produces silence, which is the correct default.
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from typing import Callable, Optional

from core.bus import Bus
from core.intent import Intent
from core.policy import Delivery, DeliveryContext, SpeakPolicy, TimeOfDay, Urgency
from core.presence import PresenceEvent, PresenceEventType
from daemon.proactive import Briefing

_SALUTATION = {
    TimeOfDay.EARLY_MORNING: "Morning, sir. You're up early.",
    TimeOfDay.MORNING: "Good morning, sir.",
    TimeOfDay.AFTERNOON: "Afternoon, sir.",
    TimeOfDay.EVENING: "Evening, sir.",
    TimeOfDay.NIGHT: "Still up, sir?",
}


@dataclass
class Greeter:
    bus: Bus
    briefing: Briefing
    policy: SpeakPolicy = field(default_factory=SpeakPolicy)
    context_fn: Callable[[], DeliveryContext] = DeliveryContext.from_clock

    def attach(self) -> "Greeter":
        self.bus.subscribe("presence.arrived", self._on_arrived, "greeter")
        return self

    # ---- bus entry point ----
    def _on_arrived(self, intent: Intent) -> None:
        self.handle(PresenceEvent(
            PresenceEventType.ARRIVED,
            seconds=float(intent.args.get("away_seconds", 0.0)),
            should_greet=bool(intent.args.get("should_greet", False)),
        ))

    def handle(self, event: PresenceEvent) -> Optional[str]:
        """Returns the text offered, or None if he stayed quiet."""
        if event.type is not PresenceEventType.ARRIVED or not event.should_greet:
            return None

        ctx = self.context_fn()
        held = len(self.briefing)

        # A greeting answers the user's own arrival, so it is not unsolicited
        # in the way a watcher alert is — they are present and, by definition,
        # available. That makes it WARN rather than INFO, which is the
        # difference between a cue and a silent badge nobody notices. The hour
        # still gets the final say: policy badges this at night and defers it
        # entirely during quiet hours.
        urgency = Urgency.WARN
        decision = self.policy.decide(urgency, ctx, category="greeting", key="arrival")
        if decision.delivery in (Delivery.SUPPRESS, Delivery.BATCH):
            return None

        text = _SALUTATION[ctx.time_of_day]
        if held:
            text += " " + self.briefing.summary()
            self.briefing.drain()

        self.policy.record("greeting", "arrival")
        self.bus.publish(Intent(
            "jarvis.offer" if decision.delivery is Delivery.CHIME else "jarvis.badge",
            source="system", confidence=1.0,
            args={"text": text, "urgency": urgency.value,
                  "category": "greeting", "reason": decision.reason},
        ))
        return text
