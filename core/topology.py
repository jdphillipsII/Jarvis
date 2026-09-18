"""Naming a face so it survives the edit.

The failure this exists to prevent: a program says "fillet face 3", somebody
makes the plate 3 mm thicker, the kernel renumbers, and face 3 is now a
different face. The part still builds. The fillet is on the wrong edge. Nothing
anywhere reports a problem, and the first sign of it is a machined part that
does not fit.

Index-based selection is the standard way to do this and it is silently wrong
under exactly the operation a parametric model exists to support. Taken from
cad-cae-copilot's `@face:*` pointers (docs/PRIOR_ART.md) and shaped to fit
PartGenome, where the op vocabulary is already closed.

A pointer names provenance, not position:

    @face:base_pad/top          the face the op called `base_pad` made as its top
    @face:inlet_hole/bore#2     the second bore instance, where there are many
    @edge:channels/floor_rim#*  every instance — "fillet all the channel floors"
    @edge:base_pad/top_rim      an edge, same grammar

Three properties follow, and they are the whole point:

  * **Thickening the plate changes nothing.** The pointer never referred to a
    number that the kernel owns.
  * **Inserting a step changes nothing.** It refers to an op by its declared
    id, not by where it sits in the program.
  * **Deleting the step it names is loud.** A dangling pointer is a load-time
    error, before any geometry is built — which is the half of this problem
    that can be solved without a kernel, and therefore the half we solve here.

This module is the pointer algebra and the checker. Resolving a pointer to an
actual face needs a kernel, so that is an interface (`Provenance`) rather than
an implementation: a kernel adapter reports which handles each op produced
under each role, and `resolve` does the rest. The checker runs with no kernel
at all, which is why the whole of it is tested.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------- vocabulary

FACE, EDGE = "face", "edge"

# What each op is understood to produce, kernel-independently. Grown the same
# way OPS is grown in atlas_cad/part.py: append, never repurpose — genomes in
# the wild point at these names.
ROLES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "datum_plane":    {FACE: ("plane",),                      EDGE: ()},
    "datum_axis":     {FACE: (),                              EDGE: ("axis",)},
    "sketch":         {FACE: ("profile",),                    EDGE: ("segment",)},
    "pad":            {FACE: ("top", "bottom", "side"),
                       EDGE: ("top_rim", "bottom_rim", "side_vertical")},
    "pocket":         {FACE: ("floor", "wall"),               EDGE: ("mouth", "floor_rim")},
    "hole":           {FACE: ("bore", "entry", "exit", "counterbore", "countersink"),
                       EDGE: ("entry_rim", "exit_rim")},
    "fillet":         {FACE: ("fillet",),                     EDGE: ("tangent",)},
    "chamfer":        {FACE: ("chamfer",),                    EDGE: ("tangent",)},
    "shell":          {FACE: ("inner", "outer", "opening"),   EDGE: ("opening_rim",)},
    "rib":            {FACE: ("side", "top"),                 EDGE: ("root",)},
    "boss":           {FACE: ("top", "side"),                 EDGE: ("top_rim", "root")},
    "thread":         {FACE: ("flank", "crest", "root"),      EDGE: ()},
}

# Ops that re-emit another op's faces rather than making their own. Their roles
# are the roles of the op named in `source`, and because they always produce
# more than one instance, a pointer into them must carry an ordinal.
INSTANCING = {"mirror", "pattern_linear", "pattern_circular",
              "hole_pattern", "pocket_pattern"}

_POINTER_RE = re.compile(
    r"^@(?P<kind>face|edge):"
    r"(?P<op>[A-Za-z_][A-Za-z0-9_]*)"
    r"/(?P<role>[a-z_][a-z0-9_]*)"
    r"(?:#(?P<ordinal>\d+|\*))?$")


class PointerError(ValueError):
    """A pointer that cannot be parsed, checked, or resolved."""


class DanglingPointer(PointerError):
    """Names an op that is not there."""


class AmbiguousPointer(PointerError):
    """Matches more than one face and did not say which.

    Deliberately an error. Taking the first match is how the fillet moves.
    """


@dataclass(frozen=True)
class Pointer:
    kind: str                       # "face" | "edge"
    op_id: str
    role: str
    ordinal: Optional[int] = None   # 1-based, None = "there should be exactly one"
    every: bool = False             # "#*" — all instances, however many

    def __str__(self) -> str:
        tail = "#*" if self.every else (
            f"#{self.ordinal}" if self.ordinal is not None else "")
        return f"@{self.kind}:{self.op_id}/{self.role}{tail}"

    @property
    def is_instanced(self) -> bool:
        """Says which of many, one way or the other."""
        return self.every or self.ordinal is not None

    @property
    def is_ordinal(self) -> bool:
        """Selects by position — the weaker kind. `#*` is not one of these."""
        return self.ordinal is not None and not self.every

    @property
    def caveat(self) -> str:
        """What this pointer does *not* guarantee, in the genome's own voice.

        A role pointer is stable because the role is ours. An ordinal is only
        as stable as whatever ordered the instances, which is the kernel's or
        the pattern's business. Saying so is cheaper than pretending otherwise,
        and matches how verify_part reports what it could not check.
        """
        if not self.is_ordinal:
            return ""
        return (f"{self} selects by position within a role; it survives a "
                f"dimension change but not a reordering of the instances")

    @classmethod
    def parse(cls, text: Any) -> "Pointer":
        if isinstance(text, Pointer):
            return text
        match = _POINTER_RE.match(str(text).strip())
        if not match:
            raise PointerError(
                f"{text!r} is not a topology pointer — "
                f"expected @face:<op_id>/<role> or @edge:<op_id>/<role>[#n]")
        ordinal = match.group("ordinal")
        if ordinal == "*":
            return cls(kind=match.group("kind"), op_id=match.group("op"),
                       role=match.group("role"), every=True)
        if ordinal is not None and int(ordinal) < 1:
            raise PointerError(f"{text!r}: ordinals are 1-based")
        return cls(kind=match.group("kind"), op_id=match.group("op"),
                   role=match.group("role"),
                   ordinal=int(ordinal) if ordinal is not None else None)


def is_pointer(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("@face:", "@edge:"))


def find_pointers(value: Any) -> List[str]:
    """Every pointer-shaped string anywhere in a nested structure."""
    found: List[str] = []
    if is_pointer(value):
        found.append(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            found.extend(find_pointers(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(find_pointers(item))
    return found


# ---------------------------------------------------------------- the checker

@dataclass(frozen=True)
class Problem:
    path: str                       # "program[4].edges"
    pointer: str
    reason: str
    suggestion: str = ""

    def __str__(self) -> str:
        tail = f" ({self.suggestion})" if self.suggestion else ""
        return f"{self.path}: {self.pointer} — {self.reason}{tail}"


def _steps(program: Iterable[Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Accept atlas FeatureOps or the plain dicts a YAML load gives."""
    out = []
    for item in program:
        if isinstance(item, Mapping):
            out.append((str(item.get("op", "")),
                        {k: v for k, v in item.items() if k != "op"}))
        else:
            out.append((str(getattr(item, "op", "")),
                        dict(getattr(item, "params", {}) or {})))
    return out


def check_program(program: Sequence[Any]) -> List[Problem]:
    """Every way a pointer can be wrong before a kernel is involved.

    Runs at load, next to the rest of PartGenome's validation, so a bad pointer
    is a refusal rather than a part.
    """
    steps = _steps(program)
    problems: List[Problem] = []

    # An op needs an id only if something points at it. You pay for what you
    # name, and a program with no pointers needs no ids at all.
    ids: Dict[str, int] = {}
    for index, (op_name, params) in enumerate(steps):
        op_id = params.get("id")
        if op_id is None:
            continue
        op_id = str(op_id)
        if op_id in ids:
            problems.append(Problem(f"program[{index}]", op_id,
                                    "duplicate op id",
                                    f"already used by program[{ids[op_id]}]"))
            continue
        ids[op_id] = index

    for index, (op_name, params) in enumerate(steps):
        path = f"program[{index}]"
        for raw in find_pointers(params):
            try:
                pointer = Pointer.parse(raw)
            except PointerError as exc:
                problems.append(Problem(path, raw, str(exc)))
                continue
            problems.extend(_check_one(pointer, raw, path, index, ids, steps))
    return problems


def _check_one(pointer: Pointer, raw: str, path: str, index: int,
               ids: Mapping[str, int],
               steps: Sequence[Tuple[str, Dict[str, Any]]]) -> List[Problem]:
    target = ids.get(pointer.op_id)
    if target is None:
        known = ", ".join(sorted(ids)) or "no op declares an id"
        return [Problem(path, raw, f"no op with id '{pointer.op_id}'", known)]

    # You cannot fillet a face that has not been made yet. A pointer at the op
    # it sits in is the same mistake with a shorter loop.
    if target >= index:
        when = "itself" if target == index else "a later step"
        return [Problem(path, raw, f"points at {when}",
                        "a pointer may only name an op earlier in the program")]

    op_name, params = steps[target]
    if op_name in INSTANCING:
        return _check_instanced(pointer, raw, path, op_name, params, ids, steps)

    roles = ROLES.get(op_name)
    if roles is None:
        return [Problem(path, raw, f"op '{op_name}' declares no topology roles",
                        "add it to ROLES before pointing at what it makes")]

    permitted = roles.get(pointer.kind, ())
    if pointer.role not in permitted:
        other = roles.get(EDGE if pointer.kind == FACE else FACE, ())
        if pointer.role in other:
            hint = f"'{pointer.role}' is {'an edge' if pointer.kind == FACE else 'a face'} role"
        else:
            hint = f"{op_name} {pointer.kind} roles: {', '.join(permitted) or 'none'}"
        return [Problem(path, raw,
                        f"'{op_name}' makes no {pointer.kind} called "
                        f"'{pointer.role}'", hint)]
    return []


def _check_instanced(pointer: Pointer, raw: str, path: str, op_name: str,
                     params: Mapping[str, Any], ids: Mapping[str, int],
                     steps: Sequence[Tuple[str, Dict[str, Any]]]) -> List[Problem]:
    """A pattern re-emits its source's faces, many times over.

    So the role has to be valid for the source op, and the ordinal is not
    optional: "the bore" of a six-hole pattern is not a thing.
    """
    source_id = params.get("source")
    if source_id is None:
        return [Problem(path, raw,
                        f"'{op_name}' does not name the op it instances",
                        "an instancing op needs `source: <op_id>` before "
                        "anything can point into it")]
    source_index = ids.get(str(source_id))
    if source_index is None:
        return [Problem(path, raw, f"instances '{source_id}', which has no op",
                        ", ".join(sorted(ids)))]

    problems: List[Problem] = []
    source_op, _ = steps[source_index]
    permitted = ROLES.get(source_op, {}).get(pointer.kind, ())
    if pointer.role not in permitted:
        problems.append(Problem(
            path, raw,
            f"'{source_op}' (instanced by '{pointer.op_id}') makes no "
            f"{pointer.kind} called '{pointer.role}'",
            f"{source_op} {pointer.kind} roles: {', '.join(permitted) or 'none'}"))
    if not pointer.is_instanced:
        problems.append(Problem(
            path, raw, "an instanced feature needs an ordinal",
            f"'{pointer.role}' is produced once per instance — "
            f"write {pointer}#1 for the first, or {pointer}#* for all"))
    return problems


# ---------------------------------------------------------------- resolution

class Provenance:
    """What a kernel adapter reports back: which handles each op made, by role.

    Handles are opaque — face ids, OCCT TopoDS shapes, whatever the kernel
    deals in. Nothing here looks inside one, which is why none of this needs a
    kernel to test.
    """

    def __init__(self, produced: Optional[Mapping[Tuple[str, str, str], Sequence[Any]]] = None):
        self._produced: Dict[Tuple[str, str, str], List[Any]] = {
            k: list(v) for k, v in (produced or {}).items()}

    def record(self, op_id: str, kind: str, role: str, handles: Sequence[Any]) -> None:
        self._produced[(op_id, kind, role)] = list(handles)

    def handles(self, pointer: Pointer) -> List[Any]:
        return list(self._produced.get((pointer.op_id, pointer.kind, pointer.role), []))

    def __len__(self) -> int:
        return len(self._produced)


def expand(pointer: Any, provenance: Provenance) -> List[Any]:
    """Every handle a pointer names — one, or all of them for `#*`."""
    pointer = Pointer.parse(pointer)
    handles = provenance.handles(pointer)
    if not handles:
        raise DanglingPointer(
            f"{pointer} resolves to nothing — '{pointer.op_id}' produced no "
            f"{pointer.kind} under '{pointer.role}'")
    if pointer.every:
        return handles
    if pointer.ordinal is not None:
        if pointer.ordinal > len(handles):
            raise DanglingPointer(
                f"{pointer} asks for instance {pointer.ordinal} of "
                f"{len(handles)}")
        return [handles[pointer.ordinal - 1]]
    if len(handles) > 1:
        raise AmbiguousPointer(
            f"{pointer} matches {len(handles)} {pointer.kind}s — "
            f"say which, e.g. {pointer}#1, or {pointer}#* for all")
    return handles


def resolve(pointer: Any, provenance: Provenance) -> Any:
    """One pointer, one handle. Anything else raises.

    The ambiguous case is the important one. A kernel asked for "the side face"
    of a four-sided pad will hand back the first of four and carry on; that is
    the behaviour this whole module exists to refuse.
    """
    pointer = Pointer.parse(pointer)
    if pointer.every:
        raise PointerError(
            f"{pointer} names every instance, not one — use expand()")
    return expand(pointer, provenance)[0]


def resolve_all(pointers: Iterable[Any], provenance: Provenance) -> List[Any]:
    """Flattened: a `#*` pointer in the list contributes all of its handles."""
    out: List[Any] = []
    for pointer in pointers:
        out.extend(expand(pointer, provenance))
    return out
