"""Did the user say yes?

Same discipline as core/interrupt.py, and for the same reason: this gates
whether a proposed action actually runs, so a loose match here means JARVIS
does something you did not ask for. Only a short, standalone utterance whose
whole content is agreement counts.

Anything that is neither yes nor no is treated as a new request, not as
consent. Silence is never consent.
"""
from __future__ import annotations

import re

MAX_LEN = 40

_YES = re.compile(
    r"^\s*(?:yes|yeah|yep|yup|sure|ok|okay|affirmative|correct|confirm(?:ed)?|"
    r"do\s+it|go\s+ahead|please\s+do|go\s+on|proceed|make\s+it\s+so)"
    r"\s*[.!]?\s*$", re.IGNORECASE)

_NO = re.compile(
    r"^\s*(?:no|nope|nah|negative|don'?t|do\s+not|cancel|forget\s+it|"
    r"leave\s+it|never\s*mind|not\s+now|stop|abort)"
    r"\s*[.!]?\s*$", re.IGNORECASE)


def is_affirmative(text: str) -> bool:
    return bool(text) and len(text) <= MAX_LEN and bool(_YES.match(text))


def is_negative(text: str) -> bool:
    return bool(text) and len(text) <= MAX_LEN and bool(_NO.match(text))
