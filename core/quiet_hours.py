"""Quiet hours you don't have to configure.

A start/end time can't express "quiet on Sunday morning but not Wednesday
morning", so this keeps a 168-bucket hour-of-week histogram of what the user
dismissed vs. what was shown, and reports the buckets they reliably reject.

Policy, inherited from Axon's version and worth keeping: learned hours are
NEVER applied silently. `suggestions()` is something JARVIS offers - "you've
waved me off every weekday before 9; want me to stay quiet then?" - and the
user confirms. An assistant that silently decides when to stop talking is
indistinguishable from one that's broken.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def hour_of_week(weekday: int, hour: int) -> int:
    """Monday=0 .. Sunday=6, hour 0..23  ->  bucket 0..167."""
    if not 0 <= weekday <= 6 or not 0 <= hour <= 23:
        raise ValueError(f"bad weekday/hour: {weekday}/{hour}")
    return weekday * 24 + hour


def describe(bucket: int) -> str:
    days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    return f"{days[bucket // 24]} {bucket % 24:02d}:00"


@dataclass
class QuietHourLearner:
    dismissal_threshold: float = 0.80    # reject this often -> they mean it
    min_samples: int = 3                 # ...and enough times to be a pattern
    buckets: Dict[int, Dict[str, int]] = field(default_factory=dict)

    def record(self, bucket: int, dismissed: bool) -> None:
        b = self.buckets.setdefault(bucket, {"shown": 0, "dismissed": 0})
        b["shown"] += 1
        if dismissed:
            b["dismissed"] += 1

    def rate(self, bucket: int) -> Optional[float]:
        b = self.buckets.get(bucket)
        if not b or b["shown"] < self.min_samples:
            return None
        return b["dismissed"] / b["shown"]

    def suggestions(self) -> List[int]:
        """Buckets the user reliably rejects. Offer these; never auto-apply."""
        return sorted(bk for bk in self.buckets
                      if (r := self.rate(bk)) is not None
                      and r >= self.dismissal_threshold)

    def explain(self) -> List[str]:
        return [f"{describe(bk)} - dismissed "
                f"{self.buckets[bk]['dismissed']}/{self.buckets[bk]['shown']}"
                for bk in self.suggestions()]

    # ---- persistence: a JSON file, not a database ----
    def to_json(self) -> str:
        return json.dumps({"dismissal_threshold": self.dismissal_threshold,
                           "min_samples": self.min_samples,
                           "buckets": {str(k): v for k, v in self.buckets.items()}})

    @classmethod
    def from_json(cls, blob: str) -> "QuietHourLearner":
        raw = json.loads(blob)
        return cls(dismissal_threshold=raw.get("dismissal_threshold", 0.80),
                   min_samples=raw.get("min_samples", 3),
                   buckets={int(k): v for k, v in raw.get("buckets", {}).items()})
