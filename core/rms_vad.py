"""A probability source for the endpointer, built from plain signal energy.

Endpointer wants P(voice) per window. Silero gives that directly but costs a
torch dependency; RMS is free and already in the audio loop. The trick is that
a fixed RMS threshold is useless across rooms and microphones, so calibrate a
noise floor from ambient audio and judge every window relative to it.

Swapping in Silero later means replacing `probability()` and nothing else.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional


class RmsVad:
    """Relative-energy voice probability.

    `onset` and `full` are multiples of the measured noise floor: below `onset`
    is silence, at or above `full` is certainly voice, and the band between
    ramps smoothly so the endpointer's threshold behaves sensibly.
    """

    def __init__(self, onset: float = 2.0, full: float = 6.0,
                 floor: float = 1e-4):
        if not 0 < onset < full:
            raise ValueError("require 0 < onset < full")
        self.onset, self.full = onset, full
        self.noise_floor = floor
        self._min_floor = floor

    def calibrate(self, rms_windows: Iterable[float]) -> float:
        """Measure ambient. Uses the median so a cough during calibration
        doesn't permanently deafen the detector."""
        vals = sorted(v for v in rms_windows if not math.isnan(v))
        if vals:
            median = vals[len(vals) // 2]
            self.noise_floor = max(median, self._min_floor)
        return self.noise_floor

    def probability(self, rms: float) -> float:
        ratio = rms / max(self.noise_floor, self._min_floor)
        if ratio <= self.onset:
            return 0.0
        if ratio >= self.full:
            return 1.0
        return (ratio - self.onset) / (self.full - self.onset)
