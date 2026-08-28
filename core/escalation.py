"""Handing the hard problems to the bigger model.

The fast model routes and answers; when a question genuinely exceeds it, it
escalates. Making that a TOOL rather than a heuristic is the point — the model
that has actually read the question decides, instead of a keyword list
guessing from outside. It also means escalation is measurable: `./cli.py bench`
scores whether a model escalates when it should and, just as importantly,
whether it resists escalating when it shouldn't.

The heavy model is given no tools. It is there to think, not to act — every
side effect stays on the fast path where the consent gate lives.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .tools import Agency, Tool

ChatFn = Callable[[List[Dict[str, Any]], Optional[List[Dict[str, Any]]]], Dict[str, Any]]

DEEP_PERSONA = (
    "You are the reasoning core behind JARVIS, a dry British assistant. "
    "Think the problem through properly, then answer in at most four sentences, "
    "addressing the user as 'sir'. No preamble, no restating the question."
)


def deep_thought_tool(heavy_chat: ChatFn, persona: str = DEEP_PERSONA,
                      name: str = "reason.deeply") -> Tool:
    """Build the escalation tool around a chat callable for the heavy model."""

    def handler(question: str) -> str:
        from .reasoning import clean_reply
        reply = clean_reply(heavy_chat(
            [{"role": "system", "content": persona},
             {"role": "user", "content": question}], None))
        return (reply.get("content") or "").strip() or "No answer, sir."

    return Tool(
        name=name,
        description=("Hand a genuinely hard question to the larger reasoning "
                     "model. Use it for analysis, planning, tradeoffs, debugging "
                     "and multi-step problems. Do NOT use it for greetings, "
                     "simple facts, or anything another tool already answers — "
                     "it is markedly slower."),
        handler=handler,
        parameters={"question": {"type": "string",
                                 "description": "the full question, self-contained"}},
        required=("question",),
        min_agency=Agency.ADVISORY,     # reasoning has no side effects
        mutates=False,
    )
