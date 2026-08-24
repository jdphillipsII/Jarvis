"""Hand landmarks -> gesture labels.

Pure geometry over MediaPipe's 21-point hand model. No camera, no MediaPipe
import, no numpy — so the whole classifier is testable with hand-written
coordinate sets.

Landmark indices (MediaPipe Hands):

     0  wrist
     4  thumb tip        3  thumb ip
     8  index tip        6  index pip
    12  middle tip      10  middle pip
    16  ring tip        14  ring pip
    20  pinky tip       18  pinky pip

Everything is scale-normalised against hand span, because a hand at arm's
length and a hand near the lens must classify identically. Thresholds are
expressed as fractions of that span, never in pixels.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]

WRIST = 0
TIPS = {"thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20}
PIPS = {"thumb": 3, "index": 6, "middle": 10, "ring": 14, "pinky": 18}
MCP_INDEX, MCP_PINKY = 5, 17


class Gesture(str, Enum):
    OPEN_PALM = "open_palm"      # push away  -> dismiss
    FIST = "fist"                # clench     -> mute / interrupt
    PINCH = "pinch"              # thumb+index-> grab and drag the model
    POINT = "point"              # index only -> focus
    PEACE = "peace"              # two fingers-> switch activity


@dataclass(frozen=True)
class HandReading:
    gesture: Optional[Gesture]
    confidence: float = 0.0
    centroid: Point = (0.0, 0.0)     # for drag deltas
    span: float = 0.0


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hand_span(lm: Sequence[Point]) -> float:
    """Reference length: wrist to the furthest knuckle. Everything scales to it."""
    return max(_dist(lm[WRIST], lm[MCP_INDEX]), _dist(lm[WRIST], lm[MCP_PINKY]), 1e-6)


def extended(lm: Sequence[Point], finger: str) -> bool:
    """A finger is extended when its tip is further from the wrist than its
    middle joint. Orientation-free, so it survives a rotated hand."""
    span = hand_span(lm)
    tip, pip = lm[TIPS[finger]], lm[PIPS[finger]]
    return (_dist(lm[WRIST], tip) - _dist(lm[WRIST], pip)) / span > 0.12


def pinch_gap(lm: Sequence[Point]) -> float:
    return _dist(lm[TIPS["thumb"]], lm[TIPS["index"]]) / hand_span(lm)


def centroid(lm: Sequence[Point]) -> Point:
    xs = [p[0] for p in lm]
    ys = [p[1] for p in lm]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def classify(lm: Optional[Sequence[Point]]) -> HandReading:
    """One frame in, one reading out. None when nothing is recognised —
    the debouncer treats that as a broken streak, so an unrecognised frame
    is never mistaken for a gesture ending."""
    if not lm or len(lm) < 21:
        return HandReading(None)

    fingers = {name: extended(lm, name) for name in TIPS}
    up = [n for n in ("index", "middle", "ring", "pinky") if fingers[n]]
    gap = pinch_gap(lm)
    here, span = centroid(lm), hand_span(lm)

    # Pinch is checked first: thumb and index touching is unambiguous, and it
    # would otherwise read as a two-finger pose while the drag is in progress.
    if gap < 0.28 and not fingers["middle"] and not fingers["ring"]:
        return HandReading(Gesture.PINCH, _conf(0.28 - gap, 0.28), here, span)

    if len(up) == 4 and fingers["thumb"]:
        return HandReading(Gesture.OPEN_PALM, 0.95, here, span)
    if not up and not fingers["thumb"]:
        return HandReading(Gesture.FIST, 0.95, here, span)
    if up == ["index"]:
        return HandReading(Gesture.POINT, 0.9, here, span)
    if up == ["index", "middle"]:
        return HandReading(Gesture.PEACE, 0.9, here, span)
    return HandReading(None)


def _conf(margin: float, scale: float) -> float:
    return max(0.6, min(1.0, 0.6 + 0.4 * margin / scale))


# ---- drag ------------------------------------------------------------------

@dataclass
class DragTracker:
    """Turns a held pinch into orbit deltas.

    Deltas are normalised by hand span, so moving your hand six inches means
    the same rotation whether you are near the lens or across the room.
    """
    origin: Optional[Point] = None
    span: float = 1.0

    def start(self, reading: HandReading) -> None:
        self.origin, self.span = reading.centroid, max(reading.span, 1e-6)

    def delta(self, reading: HandReading) -> Tuple[float, float]:
        if self.origin is None:
            self.start(reading)
            return (0.0, 0.0)
        dx = (reading.centroid[0] - self.origin[0]) / self.span
        dy = (reading.centroid[1] - self.origin[1]) / self.span
        self.origin = reading.centroid
        return (round(dx, 4), round(dy, 4))

    def stop(self) -> None:
        self.origin = None


# ---- mapping to intents ----------------------------------------------------

GESTURE_INTENTS = {
    Gesture.OPEN_PALM: "window.dismiss",
    Gesture.FIST: "mic.mute",
    Gesture.POINT: "window.focus",
    Gesture.PEACE: "workspace.next",
    # PINCH is deliberately absent: it is a continuous drag, not a discrete
    # event, and is published as model.orbit from the daemon instead.
}
