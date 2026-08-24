"""Making JARVIS shut up.

Deliberately literal. No fuzzy intent detection, no LLM classification: the
cost of a false positive ("hold on, let me check that" silencing him
mid-answer) is far worse than the cost of a miss, and the user can always
just say it again more plainly.

The rule is: a short, standalone utterance whose whole content is a stop word.
"""
from __future__ import annotations

import re

_STOP = re.compile(
    r"^\s*(?:jarvis[,\s]+)?"
    r"(?:pause|stop|shush|hush|quiet|be\s+quiet|not\s+now|hold\s+on|"
    r"never\s+mind|nevermind|cancel|shut\s+up|enough)"
    r"\s*[.!]?\s*$",
    re.IGNORECASE,
)

MAX_LEN = 40


def is_pause_utterance(transcript: str) -> bool:
    """True only if the entire utterance is a stop command."""
    if not transcript or len(transcript) > MAX_LEN:
        return False
    return bool(_STOP.match(transcript))
