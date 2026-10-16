"""What a local model is allowed to say when it designs a figure.

Measured against the eight shipped anatomy examples, a third of every build is
vector arithmetic — working out where each part goes. That is the part a model
running on one card is worst at, and it fails invisibly: a part two units
inside another part looks fine until something ray-casts it.

The skill already says what should replace it:

    Each part sits on another part.          — SKILL.md, the parts-list rule

That is a constraint, not a coordinate. A figure whose parts each declare what
they sit on can have its placement *solved*. So the model emits this — a closed,
typed declaration — and never emits kit code. The compiler does the trigonometry.

Two properties are worth the whole module:

**Forward references are impossible, so the support graph cannot cycle.** A
part may only sit on a part declared before it. There is no cycle check here
because there is no way to write a cycle; the same trick `core/topology.py`
uses to stop a pointer naming a face that does not exist yet.

**The schema is the prompt.** `schema()` returns JSON Schema, which llama.cpp
and Ollama can hold generation to. The model does not try to emit a valid
genome — under a grammar it cannot emit an invalid one. What is left for the
loader is everything a schema cannot say: that `on` resolves, that a role
exists on the kind it is pointed at, that exactly one part is the lit subject.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from .topology import Pointer, PointerError

GROUND = "ground"
_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_PARAM_REF = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

# The closed vocabulary. Each kind names the fields it cannot be drawn without,
# and the faces it makes — so a pointer at a face a kind does not have is
# refused before any geometry exists. Grown by appending, never by repurposing.
KINDS: Dict[str, Dict[str, Any]] = {
    "slab":     {"needs": ("plan", "height"),
                 "faces": ("top", "bottom", "side"),
                 "note": "a plate, a post, a rail — k.slabOf"},
    "cylinder": {"needs": ("radius", "height"),
                 "faces": ("top", "bottom", "side"),
                 "note": "a foot, a boss, a hub — k.cylinder"},
    "turned":   {"needs": ("profile",),
                 "faces": ("wall", "top", "bottom"),
                 "note": "a solid of revolution from a profile — G.lathe"},
    "disc":     {"needs": ("radius",),
                 "faces": ("face", "rim"), "note": "a flat round face"},
    "ring":     {"needs": ("radius",), "faces": (), "note": "an outline circle"},
    "rule":     {"needs": ("from", "to"), "faces": (),
                 "note": "a straight line both of whose ends must land on something"},
    "ticks":    {"needs": ("from", "to", "count"), "faces": (),
                 "note": "a graduation run; every tick ends on a rule"},
    "dots":     {"needs": ("at",), "faces": (), "note": "screws, bolt circles"},
    "knurl":    {"needs": ("radius", "height"), "faces": ("side",),
                 "note": "a gripped knob"},
    "pattern":  {"needs": ("of", "count"), "faces": (),
                 "note": "repeats an earlier part; its faces are that part's"},
}

TONES = ("lo", "mid", "hi")


class GenomeError(ValueError):
    """The genome is malformed in a way the loader will not guess past."""


@dataclass(frozen=True)
class Fault:
    path: str
    reason: str
    suggestion: str = ""

    def __str__(self) -> str:
        tail = f" ({self.suggestion})" if self.suggestion else ""
        return f"{self.path}: {self.reason}{tail}"


# The field is `sits_on`, not `on`. YAML 1.1 reads an unquoted `on:` key as
# the boolean True, so a hand-written genome silently loses every support
# declaration — anatomy's own pilot genome carries a comment about the same
# trap. `on` is still accepted (JSON has no such problem), and a genome that
# fell into it is told exactly what happened rather than being handed fifteen
# identical faults.
SUPPORT_KEYS = ("sits_on", "on")


@dataclass(frozen=True)
class Part:
    id: str
    kind: str
    on: str                                  # "ground", a part id, or @face:...
    fields: Dict[str, Any] = field(default_factory=dict)
    tone: str = "mid"
    lit: bool = False
    note: str = ""

    @property
    def host(self) -> Optional[str]:
        """The part this one sits on, or None when it sits on the ground."""
        if self.on == GROUND:
            return None
        if self.on.startswith("@"):
            return Pointer.parse(self.on).op_id
        return self.on


@dataclass(frozen=True)
class FigureGenome:
    figure: str
    question: str                            # the one thing it has to teach
    subject: str                             # what the lit part is, in words
    parts: Tuple[Part, ...]
    params: Dict[str, float] = field(default_factory=dict)
    archetype: str = ""
    size: str = "figure"
    camera: Dict[str, float] = field(default_factory=dict)

    def part(self, part_id: str) -> Optional[Part]:
        return next((p for p in self.parts if p.id == part_id), None)

    @property
    def lit(self) -> Optional[Part]:
        return next((p for p in self.parts if p.lit), None)

    def supports(self, part_id: str) -> List[str]:
        """The chain from a part down to the ground."""
        chain: List[str] = []
        here = self.part(part_id)
        while here is not None and here.host:
            chain.append(here.host)
            here = self.part(here.host)
        return chain


# ---------------------------------------------------------------- loading

def load(document: Mapping[str, Any]) -> Tuple[Optional[FigureGenome], List[Fault]]:
    """Collect every fault rather than stopping at the first.

    A model that emitted eleven mistakes should be told all eleven; sending it
    back one at a time is how a loop takes eleven round trips.
    """
    faults: List[Fault] = []
    for key in ("figure", "question", "subject"):
        if not str(document.get(key) or "").strip():
            faults.append(Fault(key, "required"))

    size = str(document.get("size", "figure"))
    if size not in ("figure", "hero", "epic"):
        faults.append(Fault("size", "must be figure, hero or epic"))

    params = {}
    for name, value in (document.get("params") or {}).items():
        if not _ID.match(str(name)):
            faults.append(Fault(f"params.{name}", "names are lower_snake_case"))
        elif not isinstance(value, (int, float)) or isinstance(value, bool):
            faults.append(Fault(f"params.{name}", "must be a number"))
        else:
            params[str(name)] = float(value)

    raw_parts = document.get("parts")
    if not isinstance(raw_parts, list) or not raw_parts:
        faults.append(Fault("parts", "a figure is a list of parts, and needs some"))
        return None, faults

    parts: List[Part] = []
    seen: Dict[str, int] = {}
    for index, raw in enumerate(raw_parts):
        where = f"parts[{index}]"
        part, part_faults = _part(where, raw, seen, parts, params)
        faults.extend(part_faults)
        if part is not None:
            seen[part.id] = index
            parts.append(part)

    lit = [p for p in parts if p.lit]
    if len(lit) != 1:
        faults.append(Fault(
            "parts", f"exactly one part is the lit subject, found {len(lit)}",
            "the subject is the one part the eye should go to"))

    if any(f for f in faults):
        return None, faults
    return FigureGenome(
        figure=str(document["figure"]), question=str(document["question"]),
        subject=str(document["subject"]), parts=tuple(parts), params=params,
        archetype=str(document.get("archetype") or ""), size=size,
        camera=dict(document.get("camera") or {})), faults


def _part(where: str, raw: Any, seen: Mapping[str, int], parts: Sequence[Part],
          params: Mapping[str, float]) -> Tuple[Optional[Part], List[Fault]]:
    faults: List[Fault] = []
    if not isinstance(raw, Mapping):
        return None, [Fault(where, "each part is a mapping")]

    part_id = str(raw.get("id") or "")
    if not _ID.match(part_id):
        faults.append(Fault(where, "every part needs a lower_snake_case id"))
    elif part_id in seen:
        faults.append(Fault(where, f"duplicate id '{part_id}'",
                            f"already used by parts[{seen[part_id]}]"))

    kind = str(raw.get("kind") or "")
    spec = KINDS.get(kind)
    if spec is None:
        faults.append(Fault(f"{where}.kind", f"unknown kind '{kind}'",
                            f"kinds: {', '.join(sorted(KINDS))}"))

    if True in raw and not any(k in raw for k in SUPPORT_KEYS):
        faults.append(Fault(
            where, "YAML read an unquoted `on:` as the boolean True",
            "write `sits_on:` — this is YAML 1.1, where on/off/yes/no are "
            "booleans"))
        on = ""
    else:
        on = str(next((raw[k] for k in SUPPORT_KEYS if raw.get(k)), "") or "")
    faults.extend(_support(where, on, seen, parts))

    fields = {k: v for k, v in raw.items()
              if k not in ("id", "kind", "tone", "lit", "note")
              and k not in SUPPORT_KEYS and k is not True}
    if spec is not None:
        missing = [n for n in spec["needs"] if n not in fields]
        if missing:
            faults.append(Fault(
                f"{where}.{kind}", f"needs {', '.join(missing)}",
                str(spec.get("note") or "")))
    for name in sorted(_refs(fields)):
        if name not in params:
            faults.append(Fault(where, f"references undeclared $" + name))

    tone = str(raw.get("tone", "mid"))
    if tone not in TONES:
        faults.append(Fault(f"{where}.tone", f"must be one of {', '.join(TONES)}"))

    if faults:
        return None, faults
    return Part(id=part_id, kind=kind, on=on, fields=fields, tone=tone,
                lit=bool(raw.get("lit", False)),
                note=str(raw.get("note") or "")), faults


def _support(where: str, on: str, seen: Mapping[str, int],
             parts: Sequence[Part]) -> List[Fault]:
    """Nothing floats, and nothing can sit on something not yet built.

    Only earlier parts may be named, which is also why there is no cycle check:
    a cycle cannot be written.
    """
    if not on:
        return [Fault(where, "every part says what it sits on",
                      f"a part id declared earlier, or '{GROUND}'")]
    if on == GROUND:
        return []
    if on.startswith("@"):
        try:
            pointer = Pointer.parse(on)
        except PointerError as exc:
            return [Fault(where, str(exc))]
        if pointer.op_id not in seen:
            return [Fault(where, f"sits on '{pointer.op_id}', which is not a part "
                                 f"declared before it",
                          ", ".join(seen) or "nothing is declared yet")]
        host = parts[seen[pointer.op_id]]
        faces = KINDS.get(host.kind, {}).get("faces", ())
        if pointer.kind != "face":
            return [Fault(where, "a part sits on a face, not an edge")]
        if pointer.role not in faces:
            return [Fault(where,
                          f"'{host.kind}' has no face called '{pointer.role}'",
                          f"{host.kind} faces: {', '.join(faces) or 'none'}")]
        return []
    if on not in seen:
        return [Fault(where, f"sits on '{on}', which is not a part declared "
                             f"before it",
                      ", ".join(seen) or "nothing is declared yet")]
    return []


def _refs(value: Any) -> List[str]:
    found: List[str] = []
    if isinstance(value, str):
        found.extend(_PARAM_REF.findall(value))
    elif isinstance(value, Mapping):
        for item in value.values():
            found.extend(_refs(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_refs(item))
    return found


def load_file(path: str) -> Tuple[Optional[FigureGenome], List[Fault]]:
    with open(path) as fh:
        return load(yaml.safe_load(fh) or {})


# ---------------------------------------------------------------- the prompt

def schema() -> Dict[str, Any]:
    """JSON Schema for constrained decoding.

    This is the lever on local hardware. Held to a grammar, a 7B model cannot
    emit a part with an unknown kind or a missing id — the sampler will not
    produce those tokens. What the loader still has to check is everything a
    schema cannot express: that `on` names an earlier part, that a face exists
    on the kind it is pointed at, that exactly one part is lit.
    """
    return {
        "type": "object",
        "required": ["figure", "question", "subject", "parts"],
        "additionalProperties": False,
        "properties": {
            "figure": {"type": "string", "pattern": _ID.pattern},
            "question": {"type": "string",
                         "description": "the one thing the figure has to teach"},
            "subject": {"type": "string",
                        "description": "what the lit part is, in words"},
            "archetype": {"type": "string"},
            "size": {"enum": ["figure", "hero", "epic"]},
            "camera": {"type": "object", "additionalProperties": {"type": "number"}},
            "params": {"type": "object", "additionalProperties": {"type": "number"}},
            "parts": {
                "type": "array", "minItems": 12,
                "items": {
                    "type": "object",
                    "required": ["id", "kind", "sits_on"],
                    "properties": {
                        "id": {"type": "string", "pattern": _ID.pattern},
                        "kind": {"enum": sorted(KINDS)},
                        "sits_on": {"type": "string",
                               "description": f"'{GROUND}', an earlier part id, "
                                              f"or @face:<part>/<role>"},
                        "tone": {"enum": list(TONES)},
                        "lit": {"type": "boolean"},
                        "note": {"type": "string"},
                    },
                },
            },
        },
    }


def vocabulary() -> str:
    """The kinds and their faces, rendered for a system prompt."""
    lines = []
    for name in sorted(KINDS):
        spec = KINDS[name]
        faces = ", ".join(spec["faces"]) or "no faces"
        lines.append(f"- {name}: {spec['note']}. needs "
                     f"{', '.join(spec['needs'])}. faces: {faces}")
    return "\n".join(lines)
