"""Driving the figure pipeline from a model on one card.

Three jobs, and the model is only trusted with the two small ones.

**Describe.** Given a subject, say how it works in a closed vocabulary of
traits — accumulates, drains, has_ceiling, conditions_ordered. Not what object
to draw; just the shape. `figure_archetypes.select` does the matching, so the
model is never asked to be creative about metaphor.

**Bind.** Given an archetype whose genome already exists, say what this subject
makes of it: the question, the subject line, a few parameter values, a label
per part. **Not the layout.** The genome holds the parts and the compiler
solves their positions, so the model's output here is a few dozen tokens
against a schema generated from that specific genome — the exact parameter
names, the exact part ids. A grammar makes a wrong name unsayable.

**Nothing else.** It does not lay out parts, compute coordinates, choose an
object, or write kit code.

Two refusals it must be able to reach, and both are returned rather than
worked around:

    no mechanism     what you described does not work by parts moving
    not built yet    the shape is in the library but has no genome, so this
                     one needs building by hand first — after which it is
                     never hand-built again

The chat transport is the ChatFn signature the rest of the stack uses, so all
of this is tested against a scripted model and none of it needs a GPU.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import yaml

from . import figure_archetypes as fa
from .figure_compiler import CompileError, place
from .figure_genome import FigureGenome, load

ChatFn = Callable[..., Dict[str, Any]]

DESCRIBE = """You describe how things work, in a fixed vocabulary.

Given a subject, list the structural traits that are true of it. A trait is a
fact about the mechanism, never about the field it comes from.

{vocabulary}

Rules:
- Only traits from the list above. Nothing else is a trait.
- An EMPTY list is a correct and expected answer. Many subjects do not work by
  parts moving at all: an argument, a period of history, a poem, a judgement,
  a list of facts. Say so by listing no traits rather than reaching.
- Describe the mechanism, not the story around it.
"""

BIND = """You are fitting one subject onto a machine that already exists.

The machine: {object}
What moves: {moves}
It explains this shape: {relationship}
It teaches: {teaches}
It cannot show: {cannot_show}

The subject: {subject}

Give the figure its words and its numbers. You are NOT laying out parts — the
machine's parts and their positions are already decided. Only say what this
subject makes of them.
"""


@dataclass
class Draft:
    subject: str
    traits: List[str] = field(default_factory=list)
    lesson: str = ""
    archetype: Optional[fa.FigureArchetype] = None
    binding: Dict[str, Any] = field(default_factory=dict)
    document: Dict[str, Any] = field(default_factory=dict)
    genome: Optional[FigureGenome] = None
    refusal: str = ""
    faults: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.genome is not None and not self.refusal and not self.faults

    def summary(self) -> str:
        if self.refusal:
            return f"{self.subject}: {self.refusal}"
        if self.faults:
            return (f"{self.subject}: {self.archetype.id} — "
                    f"{len(self.faults)} fault(s); " + "; ".join(self.faults[:3]))
        return f"{self.subject}: {self.archetype.id}"


# ---------------------------------------------------------------- describing

def describe(subject: str, chat: ChatFn, context: str = "") -> Draft:
    """Ask the model what shape the subject is. Never what to draw."""
    body = subject if not context else f"{subject}\n\nWhat is known:\n{context}"
    answer = _ask(chat, DESCRIBE.format(vocabulary=fa.vocabulary()),
                  body, fa.schema())
    traits = [str(t) for t in (answer.get("traits") or [])]
    return Draft(subject=subject, traits=traits,
                 lesson=str(answer.get("lesson") or ""))


# ---------------------------------------------------------------- binding

def binding_schema(genome: FigureGenome) -> Dict[str, Any]:
    """A grammar cut to this exact genome.

    The parameter names are the genome's parameters and the labelled parts are
    the genome's parts, so a model cannot name one that is not there — the
    class of error that would otherwise need a round trip to discover.
    """
    return {
        "type": "object",
        "required": ["figure", "question", "subject"],
        "additionalProperties": False,
        "properties": {
            "figure": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$",
                       "description": "a short lower_snake_case name"},
            "question": {"type": "string",
                         "description": "the one thing the figure must teach"},
            "subject": {"type": "string",
                        "description": "what the lit part is, in a few words"},
            "params": {
                "type": "object", "additionalProperties": False,
                "properties": {name: {"type": "number"}
                               for name in sorted(genome.params)},
                "description": "only the values this subject changes"},
            "labels": {
                "type": "object", "additionalProperties": False,
                "properties": {part.id: {"type": "string"}
                               for part in genome.parts},
                "description": "what each part is, in this subject's words"},
        },
    }


def bind(subject: str, archetype: fa.FigureArchetype, genome: FigureGenome,
         chat: ChatFn, lesson: str = "") -> Dict[str, Any]:
    body = subject if not lesson else f"{subject}\n\nThe lesson: {lesson}"
    return _ask(chat, BIND.format(
        object=_flat(archetype.object), moves=_flat(archetype.moves),
        relationship=_flat(archetype.relationship),
        teaches=_flat(archetype.teaches),
        cannot_show=_flat(archetype.cannot_show), subject=_flat(subject)),
        body, binding_schema(genome))


def apply_binding(document: Mapping[str, Any],
                  binding: Mapping[str, Any]) -> Dict[str, Any]:
    """The archetype's genome, wearing this subject's words and numbers.

    Only the fields the binding schema allows are touched: the layout, the
    kinds, and every `sits_on` are the archetype's and stay the archetype's.
    """
    out = json.loads(json.dumps(dict(document)))      # a copy, cheaply
    for key in ("figure", "question", "subject"):
        if binding.get(key):
            out[key] = str(binding[key])
    params = dict(out.get("params") or {})
    for name, value in (binding.get("params") or {}).items():
        if name in params and isinstance(value, (int, float)):
            params[name] = float(value)
    out["params"] = params
    labels = binding.get("labels") or {}
    for part in out.get("parts") or []:
        note = labels.get(part.get("id"))
        if note:
            part["note"] = str(note)
    return out


# ---------------------------------------------------------------- the whole

def author(subject: str, library: fa.Library, chat: ChatFn,
           context: str = "") -> Draft:
    """Subject in, a genome that places out — or a refusal that says why."""
    draft = describe(subject, chat, context)
    choice = fa.select(library, draft.traits)
    if choice.verdict != fa.MATCHED:
        draft.refusal = choice.report()
        return draft

    archetype = choice.best
    draft.archetype = archetype
    if not archetype.built:
        draft.refusal = (
            f"{archetype.id} is the right shape — {_flat(archetype.object)} — "
            f"but no genome exists for it yet. Build that one by hand once; "
            f"every subject of this shape after it is automatic.")
        return draft

    with open(archetype.genome) as fh:
        document = yaml.safe_load(fh)
    genome, faults = load(document)
    if genome is None:
        draft.faults = [str(f) for f in faults]
        return draft

    draft.binding = bind(subject, archetype, genome, chat, draft.lesson)
    draft.document = apply_binding(document, draft.binding)

    bound, faults = load(draft.document)
    if bound is None:
        draft.faults = [str(f) for f in faults]
        return draft
    try:
        place(bound)
    except CompileError as exc:
        draft.faults = [str(exc)]
        return draft
    draft.genome = bound
    return draft


def _flat(text: str) -> str:
    return " ".join(str(text).split())


def _ask(chat: ChatFn, system: str, body: str,
         schema: Dict[str, Any]) -> Dict[str, Any]:
    """One structured turn. A model that answers with something other than the
    shape it was held to gets an empty answer rather than a crash."""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": body}]
    try:
        message = chat(messages, schema=schema)
    except TypeError:                       # a transport with no schema support
        message = chat(messages)
    content = (message or {}).get("content") or ""
    if isinstance(content, dict):
        return content
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
