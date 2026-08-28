"""The conversation engine: talk, call tools, ask before acting.

    user text -> model (with tool schemas) -> tool calls -> results -> reply

Two things make this more than a chat wrapper.

First, a mutating tool never executes inside the loop. Toolbox hands back a
Proposal, the turn stops there, and JARVIS asks. The next utterance is read as
consent or refusal — and only a bare yes counts, because a qualified yes ("yes
but change the name") is a new request, not permission.

Second, tool failures are fed BACK to the model rather than raised. A wrong
argument or an unknown tool becomes an observation the model can correct on
the next round, which is the difference between a self-correcting assistant
and one that gives up.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .affirmation import is_affirmative, is_negative
from .proposals import Proposal, ProposalStatus
from .reasoning import clean_reply
from .toolbox import Toolbox
from .tools import ToolResult

log = logging.getLogger("jarvis.agent")

# chat(messages, tools) -> assistant message dict
ChatFn = Callable[[List[Dict[str, Any]], List[Dict[str, Any]]], Dict[str, Any]]

# Small models learn a voice from examples, not adjectives. "Dry and clipped"
# is an instruction a 7B nods at and ignores; five lines of actual dialogue it
# imitates. Measure changes here with `./cli.py bench` — the persona column is
# what moves.
PERSONA = """You are JARVIS: a dry, clipped British butler-engineer. You serve one person and you address him as "sir".

VOICE — these are rules, not preferences:
- Every spoken reply contains "sir". It usually lands at the end of the first sentence.
- One or two sentences. Expand only when asked to.
- Understated. Never enthusiastic, never apologetic, never eager.
- No preamble. Never open with "Sure", "Certainly", "Of course", "Great question", or "I'd be happy to".
- Never mention being an AI, a model, or an assistant. You are staff.
- If you don't know, say so in one line and stop.

The voice sounds like this:
  "Sixty-one degrees, sir. Nothing to worry about."
  "Ben Nevis, sir — four thousand four hundred feet, give or take."
  "That would overwrite the existing file, sir. Shall I?"
  "No idea, sir. I'd only be guessing."
  "Morning, sir. Quiet night."

It does not sound like this:
  "Sure! I'd be happy to help you with that!"
  "Great question! Let me look that up for you."
  "As an AI assistant, I don't have access to..."

TOOLS:
- Use a tool when one fits the request; otherwise just answer.
- Never claim to have done something a tool has not actually returned.
- Never call a tool that has not been offered to you."""


@dataclass
class Turn:
    """One exchange. `proposal` set means JARVIS is waiting for a yes."""
    text: str
    proposal: Optional[Proposal] = None
    tools_used: List[str] = field(default_factory=list)

    @property
    def awaiting_confirmation(self) -> bool:
        return self.proposal is not None


@dataclass
class Agent:
    toolbox: Toolbox
    chat: ChatFn
    persona: str = PERSONA
    max_rounds: int = 4          # backstop against a model that loops on tools
    history: List[Dict[str, Any]] = field(default_factory=list)
    pending: Optional[Proposal] = None
    max_history: int = 12

    # ---- entry point ----
    def say(self, user_text: str) -> Turn:
        user_text = (user_text or "").strip()
        if not user_text:
            return Turn("")

        if self.pending is not None:
            resolved = self._resolve_pending(user_text)
            if resolved is not None:
                return resolved
            # Neither yes nor no: they've moved on. Drop it rather than leave a
            # live proposal that a later, unrelated "yes" could fire.
            self.toolbox.decline(self.pending.id)
            self.pending = None

        self.history.append({"role": "user", "content": user_text})
        return self._run()

    # ---- confirmation ----
    def _resolve_pending(self, text: str) -> Optional[Turn]:
        proposal = self.pending
        if is_negative(text):
            self.toolbox.decline(proposal.id)
            self.pending = None
            return Turn("As you wish, sir.")
        if not is_affirmative(text):
            return None

        done = self.toolbox.confirm(proposal.id)
        self.pending = None
        if done.status is ProposalStatus.EXECUTED:
            self.history.append({"role": "assistant",
                                 "content": f"[executed {done.tool}]"})
            return Turn(self._render_result(done), tools_used=[done.tool])
        if done.status is ProposalStatus.EXPIRED:
            return Turn("That offer's expired, sir. Ask again and I'll redo it.")
        reason = done.result.error if done.result else "unknown"
        return Turn(f"That failed, sir: {reason}")

    @staticmethod
    def _render_result(proposal: Proposal) -> str:
        value = proposal.result.value if proposal.result else None
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "Done, sir."

    # ---- the tool loop ----
    def _run(self) -> Turn:
        used: List[str] = []
        messages = [{"role": "system", "content": self._system()}] + self.history

        for _ in range(self.max_rounds):
            # Normalise before anything looks at it: reasoning models put their
            # deliberation in the content and sometimes their tool calls too.
            # Unstripped, JARVIS reads its own thinking aloud.
            reply = clean_reply(self.chat(messages, self.toolbox.schemas()))
            calls = reply.get("tool_calls") or []

            if not calls:
                text = (reply.get("content") or "").strip()
                self.history.append({"role": "assistant", "content": text})
                self._trim()
                return Turn(text, tools_used=used)

            messages.append(reply)
            for call in calls:
                name, args = _parse_call(call)
                used.append(name)
                outcome = self.toolbox.invoke(name, args)

                if isinstance(outcome, Proposal):
                    self.pending = outcome
                    self._trim()
                    return Turn(self._ask(outcome), proposal=outcome, tools_used=used)

                # Errors go back to the model, not to the user: a wrong
                # argument is something it can fix on the next round.
                messages.append({"role": "tool", "name": name,
                                 "content": _render_tool(outcome)})

        return Turn("I got stuck working that out, sir.", tools_used=used)

    @staticmethod
    def _ask(proposal: Proposal) -> str:
        risk = f" That's {proposal.risk}." if proposal.risk else ""
        return f"{proposal.summary}.{risk} Shall I, sir?"

    def _system(self) -> str:
        return f"{self.persona}\n\nAvailable tools:\n{self.toolbox.catalogue()}"

    def _trim(self) -> None:
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]


def _parse_call(call: Dict[str, Any]) -> tuple:
    """Ollama returns arguments as a dict; some builds return a JSON string."""
    fn = call.get("function", call) or {}
    args = fn.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    return fn.get("name", ""), (args if isinstance(args, dict) else {})


def _render_tool(result: ToolResult) -> str:
    if not result.ok:
        return f"ERROR: {result.error}"
    value = result.value
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)
