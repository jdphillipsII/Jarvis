"""Source-side debouncing. Per the contract, sources debounce, not actuators.

A vision model emitting 30 frames/sec will happily fire the same gesture 30
times. Debouncer collapses that into one event, and requires a gesture to be
stable across N consecutive frames before it counts at all.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, Optional


class Debouncer:
    """Confirm-then-cooldown gate.

    - `stable_frames`: how many consecutive reads must agree before firing.
    - `cooldown_s`: silence window after a fire, per intent name.
    """

    def __init__(self, stable_frames: int = 3, cooldown_s: float = 0.8,
                 clock: Callable[[], float] = time.monotonic):
        if stable_frames < 1:
            raise ValueError("stable_frames must be >= 1")
        self.stable_frames = stable_frames
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._candidate: Optional[str] = None
        self._streak = 0
        self._last_fired: Dict[str, float] = {}

    def feed(self, name: Optional[str]) -> Optional[str]:
        """Push one observation. Returns the intent name exactly once per gesture."""
        if name is None:                      # nothing detected — break the streak
            self._candidate, self._streak = None, 0
            return None

        if name == self._candidate:
            self._streak += 1
        else:
            self._candidate, self._streak = name, 1

        if self._streak < self.stable_frames:
            return None

        now = self._clock()
        last = self._last_fired.get(name)
        if last is not None and now - last < self.cooldown_s:
            return None                        # still cooling down

        self._last_fired[name] = now
        self._streak = 0                       # require re-confirmation to repeat
        return name

    def reset(self) -> None:
        self._candidate, self._streak = None, 0
        self._last_fired.clear()
