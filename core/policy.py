"""When may JARVIS interrupt?

The governing rule, taken from Axon's voice module and adopted wholesale:

    NO URGENCY LEVEL UNLOCKS AUTO-SPEECH.

Even a critical event only earns a cue. Speech happens after the user accepts.
A speaker in a room at 2am is not a dashboard, and an assistant that talks at
you unprompted gets muted within a week — at which point its judgment is moot.

So this module never returns SPEAK for proactive content. It grades an event
down a ladder of decreasing intrusiveness and stops at the first level the
current moment can justify.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Optional


class TimeOfDay(str, Enum):
    EARLY_MORNING = "early_morning"   # 05-08
    MORNING = "morning"               # 08-12
    AFTERNOON = "afternoon"           # 12-17
    EVENING = "evening"               # 17-22
    NIGHT = "night"                   # 22-05


class DayType(str, Enum):
    WORKDAY = "workday"
    FRIDAY = "friday"
    WEEKEND = "weekend"


class Urgency(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class Delivery(str, Enum):
    """Descending intrusiveness. CHIME is the ceiling for anything proactive."""
    CHIME = "chime"        # soft cue + visible offer; speaks only if accepted
    BADGE = "badge"        # silent visual mark on the HUD
    BATCH = "batch"        # hold for the next briefing
    SUPPRESS = "suppress"  # drop entirely


@dataclass(frozen=True)
class DeliveryContext:
    time_of_day: TimeOfDay
    day_type: DayType
    local_hour: int
    hour_of_week: int              # weekday*24 + hour, 0..167
    is_quiet_hours: bool = False
    is_focused: bool = False       # deep work — the signal Axon's version lacked
    user_present: bool = True      # from presence detection

    @classmethod
    def from_clock(cls, now: Optional[datetime] = None, *,
                   is_quiet_hours: bool = False, is_focused: bool = False,
                   user_present: bool = True) -> "DeliveryContext":
        now = now or datetime.now().astimezone()
        h = now.hour
        tod = (TimeOfDay.NIGHT if h >= 22 or h < 5 else
               TimeOfDay.EARLY_MORNING if h < 8 else
               TimeOfDay.MORNING if h < 12 else
               TimeOfDay.AFTERNOON if h < 17 else
               TimeOfDay.EVENING)
        wd = now.weekday()
        day = (DayType.WEEKEND if wd >= 5 else
               DayType.FRIDAY if wd == 4 else DayType.WORKDAY)
        return cls(time_of_day=tod, day_type=day, local_hour=h,
                   hour_of_week=wd * 24 + h, is_quiet_hours=is_quiet_hours,
                   is_focused=is_focused, user_present=user_present)


@dataclass(frozen=True)
class Decision:
    delivery: Delivery
    reason: str                    # always populated: policy must be explainable

    def __bool__(self) -> bool:
        return self.delivery is not Delivery.SUPPRESS


class Cooldown:
    """Per-identity silence window, so one flapping condition can't nag.

    Identity is hashed from (category, key) rather than the rendered text, so
    rewording the same alert does not defeat it.
    """

    def __init__(self, seconds: float = 1800.0,
                 clock: Callable[[], float] = None):
        import time as _t
        self.seconds = seconds
        self._clock = clock or _t.monotonic
        self._last: Dict[str, float] = {}

    @staticmethod
    def identity(category: str, key: str) -> str:
        return hashlib.sha1(f"{category}:{key}".encode()).hexdigest()[:16]

    def is_cooling(self, category: str, key: str) -> bool:
        last = self._last.get(self.identity(category, key))
        return last is not None and (self._clock() - last) < self.seconds

    def mark(self, category: str, key: str) -> None:
        self._last[self.identity(category, key)] = self._clock()


@dataclass
class SpeakPolicy:
    """Grades an event down the ladder; first justifiable level wins."""
    cooldown: Cooldown = field(default_factory=Cooldown)
    muted_categories: frozenset = frozenset()

    def decide(self, urgency: Urgency, ctx: DeliveryContext, *,
               category: str = "general", key: str = "") -> Decision:
        # 1. Explicit mute beats everything except critical.
        if category in self.muted_categories and urgency is not Urgency.CRITICAL:
            return Decision(Delivery.SUPPRESS, f"category '{category}' muted")

        # 2. Repeat of something already raised recently.
        if key and self.cooldown.is_cooling(category, key):
            return Decision(Delivery.SUPPRESS, "within cooldown for this item")

        # 3. Nobody there. Never talk to an empty room; save it for their return.
        if not ctx.user_present:
            return Decision(Delivery.BATCH, "user away from desk")

        # 4. Quiet hours. Critical still gets a silent mark, nothing more.
        if ctx.is_quiet_hours:
            return (Decision(Delivery.BADGE, "quiet hours: critical badged only")
                    if urgency is Urgency.CRITICAL
                    else Decision(Delivery.BATCH, "quiet hours"))

        # 5. Deep work is expensive to break. This is the check Axon was missing.
        if ctx.is_focused:
            if urgency is Urgency.CRITICAL:
                return Decision(Delivery.CHIME, "critical overrides focus")
            if urgency is Urgency.WARN:
                return Decision(Delivery.BADGE, "focused: warn badged")
            return Decision(Delivery.BATCH, "focused: info deferred")

        # 6. Night, when present and unfocused: still restrained.
        if ctx.time_of_day is TimeOfDay.NIGHT:
            if urgency is Urgency.CRITICAL:
                return Decision(Delivery.CHIME, "critical at night")
            return (Decision(Delivery.BADGE, "night: warn badged")
                    if urgency is Urgency.WARN
                    else Decision(Delivery.SUPPRESS, "night: info dropped"))

        # 7. Off-hours social windows: don't nag about nothing.
        if urgency is Urgency.INFO:
            if ctx.day_type is DayType.WEEKEND:
                return Decision(Delivery.BATCH, "weekend: info deferred")
            if ctx.day_type is DayType.FRIDAY and ctx.time_of_day is TimeOfDay.AFTERNOON:
                return Decision(Delivery.BATCH, "friday afternoon: info deferred")
            if ctx.time_of_day is TimeOfDay.EVENING:
                return Decision(Delivery.BADGE, "evening: info badged")

        # 8. Normal working moment.
        return (Decision(Delivery.CHIME, "attention available")
                if urgency in (Urgency.WARN, Urgency.CRITICAL)
                else Decision(Delivery.BADGE, "routine info"))

    def record(self, category: str, key: str) -> None:
        """Call after actually surfacing, to start the cooldown."""
        if key:
            self.cooldown.mark(category, key)
