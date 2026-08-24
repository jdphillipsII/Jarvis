"""Is the user at the desk?

Naive presence ("a face was detected this frame") is unusable: detectors drop
frames constantly, so raw output flaps between present and away several times a
minute. Two pieces of hysteresis fix it.

    arrival   requires N consecutive detections  — rejects a passer-by
    departure requires sustained absence         — leaning out of frame to
                                                   reach for coffee is not
                                                   leaving

And one piece of manners: coming back after twenty seconds should NOT be
greeted. `should_greet` gates that on how long they were actually gone, which
is the difference between an assistant that welcomes you back and one that
says 'welcome back, sir' every time you stretch.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class PresenceState(str, Enum):
    AWAY = "away"
    PRESENT = "present"


class PresenceEventType(str, Enum):
    ARRIVED = "arrived"
    LEFT = "left"


@dataclass(frozen=True)
class PresenceEvent:
    type: PresenceEventType
    seconds: float          # ARRIVED: how long they were away. LEFT: how long present.
    should_greet: bool = False


@dataclass(frozen=True)
class PresenceConfig:
    arrive_frames: int = 4          # consecutive hits before believing it
    leave_grace_s: float = 45.0     # sustained absence before declaring departure
    regreet_after_s: float = 300.0  # gone this long to earn a greeting


class PresenceTracker:
    """Feed one detection per frame; get an event on a confirmed transition."""

    def __init__(self, config: Optional[PresenceConfig] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.cfg = config or PresenceConfig()
        self._clock = clock
        self.state = PresenceState.AWAY
        self._streak = 0
        self._absent_since: Optional[float] = None
        self._state_since = clock()

    def feed(self, detected: bool) -> Optional[PresenceEvent]:
        now = self._clock()

        if self.state is PresenceState.AWAY:
            if not detected:
                self._streak = 0
                return None
            self._streak += 1
            if self._streak < self.cfg.arrive_frames:
                return None
            away_for = now - self._state_since
            self._enter(PresenceState.PRESENT, now)
            return PresenceEvent(PresenceEventType.ARRIVED, away_for,
                                 should_greet=away_for >= self.cfg.regreet_after_s)

        # PRESENT
        if detected:
            self._absent_since = None
            return None
        if self._absent_since is None:
            self._absent_since = now
            return None
        if now - self._absent_since < self.cfg.leave_grace_s:
            return None                       # still within the grace window

        present_for = self._absent_since - self._state_since
        # Backdate the away clock to when they actually vanished, not to when
        # we got around to believing it — otherwise every departure loses
        # `leave_grace_s` of away time and short trips never earn a greeting.
        self._enter(PresenceState.AWAY, self._absent_since)
        return PresenceEvent(PresenceEventType.LEFT, present_for)

    def _enter(self, state: PresenceState, at: float) -> None:
        self.state = state
        self._state_since = at
        self._streak = 0
        self._absent_since = None

    @property
    def is_present(self) -> bool:
        return self.state is PresenceState.PRESENT
