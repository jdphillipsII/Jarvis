"""A library of mechanisms, indexed by relationship rather than by subject.

The objection to a library is obvious: "explain anything" cannot mean a
catalogue of objects, because there is no end to subjects. The resolution is in
anatomy's own concept-to-object table, where **not one object belongs to the
subject it explains**:

    a cache key that skips work when nothing changed   ->  a pin-tumbler lock
    seven render targets, different bytes per texel    ->  a chest of drawers
    one GPU context serving many canvases              ->  a gantry plotter
    a height profile                                   ->  a contour gauge

The lock does not know what a cache is. It is there because the relationship —
*several conditions must all match before one thing happens* — has that shape,
and the same lock explains an enzyme needing its cofactors, a multi-factor
login, and a tumbler of a combination safe. **A small library of shapes covers
an unbounded set of subjects**, which is the only way this works.

So the model is never asked to invent an object, and it is never even asked to
pick one. It describes the mechanism in a closed vocabulary of traits — does
this accumulate, does it drain, is there a ceiling, must conditions pass in
order — and the library matches. Characterising is a far smaller job than
inventing, and under a grammar a 7B model can do it.

Three answers, and the third is the one that makes the rest honest:

    a match          the shape is in the library
    nothing fits     the shape is real, and the library does not have it
    no mechanism     what you described does not work by parts moving

The last is not a failure. A poem, a judgement, a list of dates: forcing a
machine onto those produces decoration, and decoration dressed as explanation
is worse than nothing. The library says so.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import yaml

_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "figure_archetypes")

# The closed vocabulary a mechanism is described in. Grown by appending; a
# trait is a structural fact about how a thing works, never a subject.
TRAITS: Dict[str, str] = {
    # quantity and accumulation
    "accumulates": "something builds up over time or along an axis",
    "drains": "something leaves, continuously or in draws",
    "has_ceiling": "there is a maximum it cannot exceed",
    "overflows": "what arrives past the ceiling is lost, not queued",
    "varies_with_one": "a quantity changes with a single variable",
    "varies_along_path": "a quantity is sampled along a line or a surface",
    # conditions
    "conditions_all_required": "several checks must all pass",
    "conditions_ordered": "the checks happen in a fixed order and stop at the first failure",
    "conditions_any": "any one of several routes will do",
    "matches_a_key": "passing depends on a pattern matching, not on a magnitude",
    # change of state
    "threshold": "nothing happens until a level is crossed, then something does",
    "hysteresis": "the level to go up differs from the level to come back down",
    # sharing and contention
    "shared_resource": "one thing serves many",
    "many_clients": "there are several users of it",
    "queues": "waiting happens when it is busy",
    # sets
    "discrete_set": "a fixed number of distinct items",
    "differ_in_one_dimension": "the items differ chiefly in one measurable way",
    # comparison
    "trade_off": "more of one means less of another",
    "two_alternatives": "two ways of doing the same job",
    "cost_differs": "the alternatives differ in what they cost",
    # dynamics
    "feedback": "the output changes the input",
    "propagates": "an effect travels from one place to another",
    "delayed": "the effect arrives later than the cause",
    "sorts_by_property": "items are separated according to some property",
    "orientation_dependent": "the result depends on which way something faces",
}

STATUSES = ("proposed", "built")       # built = a genome exists and compiles


class ArchetypeError(ValueError):
    """The library itself is wrong. Loud, like a manifest error."""


@dataclass(frozen=True)
class FigureArchetype:
    id: str
    relationship: str                  # the shape, with no subject in it
    object: str                        # the machine
    moves: str                         # what moves, and what the motion means
    readout: str                       # the live number on the card
    needs: Tuple[str, ...] = ()        # traits that must all be present
    rules_out: Tuple[str, ...] = ()    # traits whose presence makes it wrong
    bindings: Tuple[str, ...] = ()     # what a caller must supply
    teaches: str = ""
    cannot_show: str = ""              # the limit, named
    genome: str = ""                   # path to a genome that compiles
    seen_as: Tuple[str, ...] = ()      # subjects it has explained, as examples
    status: str = "proposed"

    @property
    def built(self) -> bool:
        return self.status == "built"

    def fits(self, traits: Set[str]) -> bool:
        return set(self.needs) <= traits and not (set(self.rules_out) & traits)

    def missing(self, traits: Set[str]) -> List[str]:
        return sorted(set(self.needs) - traits)

    def blocked_by(self, traits: Set[str]) -> List[str]:
        return sorted(set(self.rules_out) & traits)


def load_archetype(document: Mapping[str, Any], source: str = "") -> FigureArchetype:
    where = source or document.get("id", "<archetype>")
    for key in ("id", "relationship", "object", "moves"):
        if not str(document.get(key) or "").strip():
            raise ArchetypeError(f"{where}: '{key}' is required")
    if not document.get("cannot_show"):
        raise ArchetypeError(
            f"{where}: 'cannot_show' is required — an archetype that claims no "
            f"limit will be reached for when it does not fit")
    status = str(document.get("status", "proposed"))
    if status not in STATUSES:
        raise ArchetypeError(f"{where}: status must be one of {list(STATUSES)}")

    needs = tuple(str(t) for t in document.get("needs") or ())
    rules_out = tuple(str(t) for t in document.get("rules_out") or ())
    for trait in needs + rules_out:
        if trait not in TRAITS:
            raise ArchetypeError(
                f"{where}: '{trait}' is not a trait",
                )
    if not needs:
        raise ArchetypeError(f"{where}: an archetype with no 'needs' matches "
                             f"everything, which is the same as matching nothing")
    overlap = set(needs) & set(rules_out)
    if overlap:
        raise ArchetypeError(f"{where}: {', '.join(sorted(overlap))} is both "
                             f"required and disqualifying")

    return FigureArchetype(
        id=str(document["id"]), relationship=str(document["relationship"]),
        object=str(document["object"]), moves=str(document["moves"]),
        readout=str(document.get("readout") or ""), needs=needs,
        rules_out=rules_out,
        bindings=tuple(str(b) for b in document.get("bindings") or ()),
        teaches=str(document.get("teaches") or ""),
        cannot_show=str(document["cannot_show"]),
        genome=str(document.get("genome") or ""),
        seen_as=tuple(str(s) for s in document.get("seen_as") or ()),
        status=status)


class Library:
    def __init__(self, items: Iterable[FigureArchetype] = ()):
        self._items: Dict[str, FigureArchetype] = {a.id: a for a in items}

    @classmethod
    def load(cls, directory: Optional[str] = None) -> "Library":
        source = directory or _DEFAULT_DIR
        if not os.path.isdir(source):
            return cls()
        found = []
        for entry in sorted(os.listdir(source)):
            if entry.endswith((".yaml", ".yml")):
                with open(os.path.join(source, entry)) as fh:
                    found.append(load_archetype(yaml.safe_load(fh) or {}, entry))
        library = cls(found)
        library.check()
        return library

    def check(self) -> None:
        for archetype in self._items.values():
            if archetype.built and not archetype.genome:
                raise ArchetypeError(
                    f"{archetype.id}: status 'built' means a genome exists — "
                    f"name it")
            if archetype.genome and not os.path.exists(archetype.genome):
                raise ArchetypeError(
                    f"{archetype.id}: genome '{archetype.genome}' is not there")

    def get(self, archetype_id: str) -> Optional[FigureArchetype]:
        return self._items.get(archetype_id)

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __iter__(self):
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)


# ---------------------------------------------------------------- selection

NO_MECHANISM = "no_mechanism"
NOTHING_FITS = "nothing_fits"
MATCHED = "matched"


@dataclass
class Choice:
    verdict: str
    traits: Set[str] = field(default_factory=set)
    matches: List[FigureArchetype] = field(default_factory=list)
    near: List[Tuple[FigureArchetype, List[str]]] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)

    @property
    def best(self) -> Optional[FigureArchetype]:
        return self.matches[0] if self.matches else None

    def report(self) -> str:
        if self.verdict == NO_MECHANISM:
            return ("this does not work by parts moving, so there is no figure "
                    "to build. Forcing a machine onto it would be decoration, "
                    "and decoration dressed as explanation is worse than prose.")
        if self.verdict == MATCHED:
            lines = [f"{a.id} — {a.object}" for a in self.matches]
            if self.unknown:
                lines.append(f"  ignored, not traits: {', '.join(self.unknown)}")
            return "\n".join(lines)
        lines = ["no archetype in the library has this shape."]
        if self.near:
            lines.append("closest, and what each would still need:")
            lines += [f"  {a.id}: needs {', '.join(m)}" for a, m in self.near[:3]]
        lines.append("building a new one by hand is the honest next step; it "
                     "then joins the library and is never hand-built again.")
        return "\n".join(lines)


def select(library: Library, traits: Sequence[str]) -> Choice:
    """Match a described mechanism against the library.

    Ranked by how much of the shape an archetype accounts for, so the entry
    that explains the most of what was described comes first. Deliberately not
    a score — a count of traits matched, which is a fact about the entry.
    """
    known = {t for t in traits if t in TRAITS}
    unknown = sorted({str(t) for t in traits} - known)
    choice = Choice(verdict=MATCHED, traits=known, unknown=unknown)
    if not known:
        choice.verdict = NO_MECHANISM
        return choice

    for archetype in library:
        if archetype.fits(known):
            choice.matches.append(archetype)
        else:
            missing = archetype.missing(known)
            if missing and not archetype.blocked_by(known):
                choice.near.append((archetype, missing))
    choice.matches.sort(key=lambda a: (-len(a.needs), not a.built, a.id))
    choice.near.sort(key=lambda pair: (len(pair[1]), pair[0].id))
    if not choice.matches:
        choice.verdict = NOTHING_FITS
    return choice


def vocabulary() -> str:
    """The traits, rendered for a system prompt."""
    return "\n".join(f"- {name}: {why}" for name, why in sorted(TRAITS.items()))


def schema() -> Dict[str, Any]:
    """A grammar for the sketch a model emits. The model describes; it does not
    choose."""
    return {
        "type": "object",
        "required": ["subject", "traits"],
        "additionalProperties": False,
        "properties": {
            "subject": {"type": "string",
                        "description": "what is being explained"},
            "lesson": {"type": "string",
                       "description": "the one thing a reader should leave with"},
            "traits": {"type": "array", "minItems": 0,
                       "items": {"enum": sorted(TRAITS)},
                       "description": "how the thing works. Empty is a valid "
                                      "answer and means it has no mechanism."},
        },
    }
