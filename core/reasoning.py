"""Cleaning up after reasoning models.

Hybrid-reasoning models (Hermes 4, Qwen 3.x, and most others now) emit their
deliberation inline as <think>...</think>, and some emit tool calls as text in
<tool_call>...</tool_call> rather than in the API's structured field.

Both are fine for a chat window and both are wrong for a voice assistant:
unstripped reasoning gets read aloud, and a tool call the transport never
surfaced simply never runs. This module makes any such model behave like a
plain one.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

# Model families disagree on the tag. Match the ones in the wild.
_THINK = re.compile(
    r"<(think|thinking|reasoning|scratchpad)\b[^>]*>.*?</\1\s*>",
    re.DOTALL | re.IGNORECASE)

# A model cut off mid-thought leaves the block unclosed — drop the tail rather
# than speaking half a monologue.
_THINK_OPEN = re.compile(
    r"<(think|thinking|reasoning|scratchpad)\b[^>]*>.*$",
    re.DOTALL | re.IGNORECASE)

_TOOL_CALL = re.compile(r"<tool_call\b[^>]*>(.*?)</tool_call\s*>",
                        re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove deliberation, keep the answer."""
    if not text:
        return ""
    cleaned = _THINK.sub("", text)
    cleaned = _THINK_OPEN.sub("", cleaned)
    return cleaned.strip()


def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Pull text-form tool calls out, shaped like the API's own field.

    Returns [] for anything unparseable — a malformed call is dropped rather
    than guessed at, and the model gets another round to do it properly.
    """
    calls: List[Dict[str, Any]] = []
    for blob in _TOOL_CALL.findall(text or ""):
        try:
            parsed = json.loads(blob.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, dict):
            continue
        name = parsed.get("name") or parsed.get("function")
        args = parsed.get("arguments", parsed.get("parameters", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if name:
            calls.append({"function": {"name": name,
                                       "arguments": args if isinstance(args, dict) else {}}})
    return calls


def clean_reply(message: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise one assistant message: strip reasoning, surface text tool calls.

    The structured field always wins — only fall back to parsing text when the
    transport gave us nothing, so a model that does it properly is untouched.
    """
    content = message.get("content") or ""
    calls = list(message.get("tool_calls") or [])
    if not calls:
        calls = extract_tool_calls(content)
        if calls:
            content = _TOOL_CALL.sub("", content)

    out = dict(message)
    out["content"] = strip_reasoning(content)
    if calls:
        out["tool_calls"] = calls
    return out
