"""Retrieve and adapt, rather than generate.

Every spec→CAD project in the survey (docs/PRIOR_ART.md) generates geometry
from the problem statement each time, and every one of them is unreliable in
the same way. That is not a model-capability problem. It is that a spec does
not contain a design: "450 W off a 40 mm die into water at 2 L/min" does not
say straight channels, and no amount of reasoning derives them, because the
answer is *a shape somebody already found* and then adapted.

So the library holds shapes. An archetype is a named, parameterised design that
has been evaluated at least once, carrying:

    what it is for          the problem shape it answers
    its parameters          named, dimensioned, bounded
    its program             PartGenome ops with $refs and topology pointers
    when it applies         machine-checkable conditions, each with a reason
    how it fails            named failure modes, and which archetype fixes each
    what backs it           provenance, and how far up the evidence ladder it is

Two rules carry the weight:

**Nothing applies is an answer.** A library that always returns its nearest
entry is worse than no library, because the nearest entry arrives with all the
authority of a proven design and none of the fit. An archetype with a failed
condition is *excluded*, never ranked low, and `select` will report that the
library does not cover the problem while naming what came closest and why it
was thrown out.

**What could not be checked is reported.** A problem statement that says
nothing about the coolant leaves every coolant condition unchecked, and the
assessment says so, in the same voice `verify_part`'s certificate names its
dark regions. An unchecked condition is not a passed one.

The ladder — proposed, simulated, built, measured — is the admission gate the
Atlas north-star doc asks for (§4.4, "admission only through a max-fidelity
adversarial gate"). Promotion needs evidence, not assertion, and the top rung
needs a predicted-vs-measured record, which is the arrow the engineering suite
lists as having no home. An archetype cannot claim to be measured without it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

from .topology import check_program
from .units import UnitError, parse_quantity

_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "archetypes")

# How far up the evidence ladder an archetype has climbed. Ordered.
STATUSES: Tuple[str, ...] = ("proposed", "simulated", "built", "measured")


class ArchetypeError(ValueError):
    """The library itself is wrong. Loud, like a manifest error."""


# ---------------------------------------------------------------- the schema

@dataclass(frozen=True)
class ParamSpec:
    name: str
    unit: str
    default: float
    bounds: Optional[Tuple[float, float]] = None      # None = fixed, not evolvable
    integer: bool = False
    description: str = ""

    @property
    def evolvable(self) -> bool:
        return self.bounds is not None

    def check(self, value: float) -> Optional[str]:
        if self.integer and float(value) != int(value):
            return f"{self.name} must be a whole number"
        if self.bounds and not (self.bounds[0] <= value <= self.bounds[1]):
            return (f"{self.name}={value} {self.unit} is outside the archetype's "
                    f"range {self.bounds[0]}–{self.bounds[1]} {self.unit}")
        return None


PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"


@dataclass(frozen=True)
class Condition:
    """One clause of "when does this shape apply".

    `why` is mandatory at load. A bound with no reason cannot be argued with,
    and an archetype library is a thing you argue with.
    """
    quantity: str
    why: str
    minimum: Optional[str] = None       # "10 W", with units
    maximum: Optional[str] = None
    one_of: Tuple[str, ...] = ()

    def describe(self) -> str:
        if self.one_of:
            return f"{self.quantity} in {{{', '.join(self.one_of)}}}"
        lo = f"≥ {self.minimum}" if self.minimum else ""
        hi = f"≤ {self.maximum}" if self.maximum else ""
        return f"{self.quantity} {' and '.join(b for b in (lo, hi) if b)}"

    def check(self, stated: Mapping[str, Any]) -> Tuple[str, str]:
        """(verdict, reason). UNKNOWN when the problem did not say."""
        if self.quantity not in stated:
            return UNKNOWN, f"the problem says nothing about {self.quantity}"
        value = stated[self.quantity]

        if self.one_of:
            ok = str(value).strip().lower() in {o.lower() for o in self.one_of}
            return (PASS, "") if ok else (
                FAIL, f"{self.quantity} is {value}, not one of "
                      f"{', '.join(self.one_of)}")
        try:
            got = parse_quantity(value)
        except UnitError as exc:
            return UNKNOWN, f"{self.quantity}: {exc}"
        for bound, worse in ((self.minimum, lambda a, b: a < b),
                             (self.maximum, lambda a, b: a > b)):
            if not bound:
                continue
            try:
                limit = parse_quantity(bound)
            except UnitError as exc:                      # caught at load too
                return UNKNOWN, f"{self.quantity}: {exc}"
            if got.dim != limit.dim:
                return FAIL, (f"{self.quantity} is {got} ({got.dim}), but this "
                              f"condition is about {limit.dim}")
            if worse(got.si, limit.si):
                return FAIL, f"{self.quantity} is {got}, outside {self.describe()}"
        return PASS, ""


@dataclass(frozen=True)
class FailureMode:
    name: str
    description: str
    detected_by: str = ""        # the analysis that would catch it
    mitigated_by: str = ""       # an archetype id, where one exists


@dataclass(frozen=True)
class Archetype:
    id: str
    summary: str
    intent: str
    parameters: Tuple[ParamSpec, ...]
    program: Tuple[Dict[str, Any], ...]
    applicability: Tuple[Condition, ...] = ()
    analyses: Tuple[str, ...] = ()
    failure_modes: Tuple[FailureMode, ...] = ()
    material: str = ""
    process: str = ""
    ports: Tuple[str, ...] = ()
    provenance: str = ""
    status: str = "proposed"
    evidence: str = ""

    @property
    def rung(self) -> int:
        return STATUSES.index(self.status)

    def param(self, name: str) -> Optional[ParamSpec]:
        return next((p for p in self.parameters if p.name == name), None)


# ---------------------------------------------------------------- loading

def load_archetype(document: Mapping[str, Any], source: str = "") -> Archetype:
    where = source or document.get("id", "<archetype>")

    def need(key: str) -> Any:
        if not document.get(key):
            raise ArchetypeError(f"{where}: '{key}' is required")
        return document[key]

    status = str(document.get("status", "proposed"))
    if status not in STATUSES:
        raise ArchetypeError(f"{where}: status must be one of {list(STATUSES)}")
    evidence = str(document.get("evidence", "")).strip()
    if status != "proposed" and not evidence:
        raise ArchetypeError(
            f"{where}: status '{status}' claims evidence — cite it in `evidence`, "
            f"or leave the status at 'proposed'")
    # The loop closure is the promotion rule, not a nice-to-have.
    if status == "measured" and "predicted" not in evidence.lower():
        raise ArchetypeError(
            f"{where}: 'measured' means a predicted-vs-measured comparison "
            f"exists — `evidence` must cite it")

    parameters = tuple(_param(where, raw) for raw in need("parameters"))
    names = [p.name for p in parameters]
    if len(set(names)) != len(names):
        raise ArchetypeError(f"{where}: duplicate parameter name")

    archetype = Archetype(
        id=str(need("id")), summary=str(need("summary")),
        intent=str(need("intent")),
        parameters=parameters,
        program=tuple(dict(step) for step in need("program")),
        applicability=tuple(_condition(where, raw)
                            for raw in document.get("applicability") or []),
        analyses=tuple(str(a) for a in document.get("analyses") or []),
        failure_modes=tuple(_failure(where, raw)
                            for raw in document.get("failure_modes") or []),
        material=str(document.get("material") or ""),
        process=str(document.get("process") or ""),
        ports=tuple(str(p) for p in document.get("ports") or []),
        provenance=str(document.get("provenance") or ""),
        status=status, evidence=evidence)

    problems = check_program(archetype.program)
    if problems:
        raise ArchetypeError(f"{where}: " + "; ".join(str(p) for p in problems))
    if (missing := sorted(_undeclared_refs(archetype))):
        raise ArchetypeError(f"{where}: program references undeclared "
                             + ", ".join(f"${name}" for name in missing))
    return archetype


def _param(where: str, raw: Mapping[str, Any]) -> ParamSpec:
    for key in ("name", "unit"):
        if key not in raw:
            raise ArchetypeError(f"{where}: every parameter needs '{key}'")
    if "default" not in raw:
        raise ArchetypeError(f"{where}: parameter '{raw['name']}' needs a default — "
                             f"an archetype is a working design, not a template")
    bounds = raw.get("bounds")
    if bounds is not None:
        if len(bounds) != 2 or bounds[0] > bounds[1]:
            raise ArchetypeError(f"{where}: {raw['name']} bounds must be [low, high]")
        bounds = (float(bounds[0]), float(bounds[1]))
    spec = ParamSpec(name=str(raw["name"]), unit=str(raw["unit"]),
                     default=float(raw["default"]), bounds=bounds,
                     integer=bool(raw.get("integer", False)),
                     description=str(raw.get("description") or ""))
    if (problem := spec.check(spec.default)):
        raise ArchetypeError(f"{where}: the default is out of its own range — {problem}")
    return spec


def _condition(where: str, raw: Mapping[str, Any]) -> Condition:
    if "quantity" not in raw:
        raise ArchetypeError(f"{where}: every applicability clause needs 'quantity'")
    if not raw.get("why"):
        raise ArchetypeError(
            f"{where}: condition on '{raw['quantity']}' has no 'why' — a bound "
            f"with no reason cannot be argued with")
    one_of = tuple(str(v) for v in raw.get("one_of") or ())
    minimum, maximum = raw.get("minimum"), raw.get("maximum")
    if not one_of and minimum is None and maximum is None:
        raise ArchetypeError(f"{where}: condition on '{raw['quantity']}' bounds nothing")
    for bound in (minimum, maximum):
        if bound is not None:
            try:
                parse_quantity(bound)
            except UnitError as exc:
                raise ArchetypeError(f"{where}: {raw['quantity']}: {exc}") from None
    return Condition(quantity=str(raw["quantity"]), why=str(raw["why"]),
                     minimum=minimum if minimum is None else str(minimum),
                     maximum=maximum if maximum is None else str(maximum),
                     one_of=one_of)


def _failure(where: str, raw: Mapping[str, Any]) -> FailureMode:
    if not raw.get("name") or not raw.get("description"):
        raise ArchetypeError(f"{where}: a failure mode needs a name and a description")
    return FailureMode(name=str(raw["name"]), description=str(raw["description"]),
                       detected_by=str(raw.get("detected_by") or ""),
                       mitigated_by=str(raw.get("mitigated_by") or ""))


def _undeclared_refs(archetype: Archetype) -> Iterable[str]:
    import re
    declared = {p.name for p in archetype.parameters}
    found = set()

    def walk(value: Any) -> None:
        if isinstance(value, str):
            found.update(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", value))
        elif isinstance(value, Mapping):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk([dict(step) for step in archetype.program])
    return found - declared


class Library:
    def __init__(self, archetypes: Iterable[Archetype] = ()):
        self._items: Dict[str, Archetype] = {a.id: a for a in archetypes}

    @classmethod
    def load(cls, directory: Optional[str] = None) -> "Library":
        source = directory or _DEFAULT_DIR
        if not os.path.isdir(source):
            return cls()
        items = []
        for entry in sorted(os.listdir(source)):
            if not entry.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(source, entry)
            with open(path) as fh:
                items.append(load_archetype(yaml.safe_load(fh) or {}, source=entry))
        library = cls(items)
        library.check_cross_references()
        return library

    def check_cross_references(self) -> None:
        for archetype in self._items.values():
            for mode in archetype.failure_modes:
                target = mode.mitigated_by
                if target and target not in self._items:
                    raise ArchetypeError(
                        f"{archetype.id}: failure mode '{mode.name}' points at "
                        f"'{target}', which is not in the library")
                if target == archetype.id:
                    raise ArchetypeError(
                        f"{archetype.id}: cannot be its own mitigation")

    def get(self, archetype_id: str) -> Optional[Archetype]:
        return self._items.get(archetype_id)

    def __contains__(self, archetype_id: object) -> bool:
        return archetype_id in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items.values())


# ---------------------------------------------------------------- selection

@dataclass
class Assessment:
    archetype: Archetype
    passed: List[str] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)      # (clause, reason)
    unchecked: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def applies(self) -> bool:
        """One failed condition is enough to exclude. Conditions are not a score.

        And nothing tested is not the same as nothing wrong: an archetype whose
        every condition went unchecked has not been selected, it has merely not
        been ruled out. That is `unproven`, and it is kept out of the answer.
        """
        return not self.failed and bool(self.passed)

    @property
    def verdict(self) -> str:
        if self.failed:
            return "excluded"
        return "applies" if self.passed else "unproven"

    def why_not(self) -> str:
        return "; ".join(reason for _, reason in self.failed)

    def summary(self) -> str:
        if self.failed:
            return f"{self.archetype.id}: excluded — {self.why_not()}"
        if not self.passed:
            return (f"{self.archetype.id}: unproven — the problem statement "
                    f"tests none of its {len(self.unchecked)} condition(s)")
        tail = (f" ({len(self.unchecked)} condition(s) unchecked)"
                if self.unchecked else "")
        return f"{self.archetype.id}: applies{tail}"


def assess(archetype: Archetype, problem: Mapping[str, Any]) -> Assessment:
    result = Assessment(archetype=archetype)
    for condition in archetype.applicability:
        verdict, reason = condition.check(problem)
        if verdict == PASS:
            result.passed.append(condition.describe())
        elif verdict == FAIL:
            result.failed.append((condition.describe(), reason))
        else:
            result.unchecked.append((condition.describe(), reason))
    return result


@dataclass
class Selection:
    applicable: List[Assessment] = field(default_factory=list)
    excluded: List[Assessment] = field(default_factory=list)
    unproven: List[Assessment] = field(default_factory=list)

    @property
    def best(self) -> Optional[Archetype]:
        return self.applicable[0].archetype if self.applicable else None

    @property
    def nothing_applies(self) -> bool:
        return not self.applicable

    def report(self) -> str:
        """What a library that refuses to guess has to say for itself."""
        if self.applicable:
            lines = [a.summary() for a in self.applicable]
            for assessment in self.applicable:
                for clause, reason in assessment.unchecked:
                    lines.append(f"  unchecked: {clause} — {reason}")
        else:
            lines = ["no archetype in the library covers this problem."]
            if self.excluded:
                lines.append("closest, and why each was excluded:")
                lines += [f"  {a.summary()}" for a in self.excluded[:3]]
            if self.unproven:
                lines.append("untested against this problem — say more, or "
                             "treat them as not covering it:")
                lines += [f"  {a.summary()}" for a in self.unproven[:3]]
            lines.append("designing from scratch is the honest next step, not "
                         "adapting one of the above.")
        return "\n".join(lines)


def select(library: Library, problem: Mapping[str, Any]) -> Selection:
    """Rank what applies; exclude what does not. Never both.

    Ordering among applicable archetypes is by evidence and then by how much of
    the problem was actually checked — deliberately not a score. A number here
    would invite comparing a design proven on a bench against one that has only
    ever been simulated, as though the gap were 0.3.
    """
    selection = Selection()
    buckets = {"applies": selection.applicable, "excluded": selection.excluded,
               "unproven": selection.unproven}
    for archetype in library:
        assessment = assess(archetype, problem)
        buckets[assessment.verdict].append(assessment)
    selection.applicable.sort(
        key=lambda a: (-a.archetype.rung, len(a.unchecked), a.archetype.id))
    selection.excluded.sort(key=lambda a: (len(a.failed), a.archetype.id))
    selection.unproven.sort(key=lambda a: a.archetype.id)
    return selection


# ---------------------------------------------------------------- adaptation

def instantiate(archetype: Archetype, values: Optional[Mapping[str, Any]] = None,
                name: str = "", material: str = "", process: str = "") -> Dict[str, Any]:
    """Retrieve, then adapt: the archetype plus the numbers this job needs.

    Returns a PartGenome document — the same shape `atlas_cad.part.load_part`
    reads — so the result goes straight into the checker battery rather than
    into a conversation about whether it looks right.

    Nothing extra is added to the document, not even which archetype it came
    from: `load_part` rejects unknown top-level fields, and it is right to.
    Provenance travels beside the document (`to_yaml` writes it as a header
    comment, the way the hand-written genomes carry theirs).
    """
    supplied = dict(values or {})
    unknown = sorted(set(supplied) - {p.name for p in archetype.parameters})
    if unknown:
        raise ArchetypeError(
            f"{archetype.id} has no parameter(s) {', '.join(unknown)} — "
            f"it takes {', '.join(p.name for p in archetype.parameters)}")

    parameters = []
    for spec in archetype.parameters:
        value = _numeric(spec, supplied[spec.name]) if spec.name in supplied \
            else spec.default
        if (problem := spec.check(value)):
            raise ArchetypeError(f"{archetype.id}: {problem}")
        entry: Dict[str, Any] = {"name": spec.name,
                                 "value": int(value) if spec.integer else value,
                                 "unit": spec.unit}
        if spec.bounds:
            entry["bounds"] = list(spec.bounds)
        if spec.integer:
            entry["integer"] = True
        parameters.append(entry)

    return {"part": name or archetype.id.replace(".", "_"),
            "role": archetype.intent,
            "parameters": parameters,
            "program": [dict(step) for step in archetype.program],
            "manufacturing": {"material": material or archetype.material,
                              "process": process or archetype.process},
            "ports": list(archetype.ports)}


def _numeric(spec: ParamSpec, value: Any) -> float:
    """Accept 8, 8.0, or "8 mm" — and refuse "8 kg" for a length.

    The units layer earns its keep here: an archetype parameter carries a unit,
    so a caller who says "3 mm" for something declared in metres gets the
    conversion, and a caller who says "3 volts" gets a refusal.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        quantity = parse_quantity(value)
    except UnitError as exc:
        raise ArchetypeError(f"{spec.name}: {exc}") from None
    try:
        return quantity.to(spec.unit).value
    except UnitError as exc:
        raise ArchetypeError(f"{spec.name}: {exc}") from None


def to_yaml(archetype: Archetype, document: Mapping[str, Any]) -> str:
    """The document as a genome file, with its provenance in the header.

    A part that came out of the library should say so on disk. The header is a
    comment because the field would not survive `load_part`, and a comment is
    where the hand-written genomes keep the same information.
    """
    known = [f"# generated from archetype {archetype.id} ({archetype.status})"]
    if archetype.provenance.strip():
        known.append("# " + " ".join(archetype.provenance.split()))
    for mode in archetype.failure_modes:
        detector = mode.detected_by or "NOTHING DETECTS THIS"
        known.append(f"# known failure mode: {mode.name} — {detector}")
    body = yaml.safe_dump(dict(document), sort_keys=False, default_flow_style=False)
    return "\n".join(known) + "\n" + body
