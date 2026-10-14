"""Figures that know where their numbers came from, and when they stopped being true.

The drawing half of this is `anatomy` (docs/PRIOR_ART.md) — a Claude skill that
builds an explanatory figure as a real working machine and then ray-casts its
own geometry to prove no part passes through another. JARVIS cannot author one:
that needs an agent with a code-writing loop and the patience to read its own
renders. What JARVIS owns is the half anatomy does not:

**A figure is a cached view of a computation.** It shows numbers that something
else worked out, at some moment, under some inputs. The failure that follows is
not subtle and not rare — a beautiful, audited, demonstrably self-consistent
figure quietly showing last spring's answer. Nothing in the drawing can detect
that, because the drawing is still perfectly correct about data that is no
longer true.

So every figure here declares the generator that produced its numbers, and
`check` re-runs it and compares. Four states, and the fourth is the one that
matters:

    fresh         regenerated and matched
    stale         regenerated and moved — with the field and the size of the move
    missing       never generated
    uncheckable   the generator will not run, so the figure is not verifiable

`uncheckable` is deliberately not a kind of fresh. A figure whose provenance
cannot be re-executed is a picture, and it is better to say so.

Reading is advisory and never writes. Regenerating changes a file that a built
page depends on, so it is an actuator that proposes first — the usual rule.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "figures")

FRESH, STALE, MISSING, UNCHECKABLE = "fresh", "stale", "missing", "uncheckable"
SIZES = ("figure", "hero", "epic")          # anatomy's own sizing


class FigureError(ValueError):
    """The figure's declaration is wrong. Loud, like a manifest error."""


@dataclass(frozen=True)
class Figure:
    slug: str
    title: str
    question: str                  # what the figure is for, in one line
    directory: str
    generator: str = ""            # "module:callable", relative to the directory
    source: str = ""               # what computed the numbers, in prose
    findings: str = ""             # the write-up this figure illustrates
    page: str = ""                 # the built standalone HTML
    data: str = "data.json"
    size: str = "figure"
    tolerance: float = 1e-6        # relative; below this a move is not a move

    @property
    def data_path(self) -> str:
        return os.path.join(self.directory, self.data)

    @property
    def page_path(self) -> str:
        return os.path.join(self.directory, self.page) if self.page else ""

    @property
    def built(self) -> bool:
        return bool(self.page) and os.path.exists(self.page_path)


def load_figure(directory: str) -> Figure:
    manifest = os.path.join(directory, "figure.yaml")
    if not os.path.exists(manifest):
        raise FigureError(f"{directory}: no figure.yaml")
    with open(manifest) as fh:
        raw = yaml.safe_load(fh) or {}
    for key in ("slug", "title", "question"):
        if not raw.get(key):
            raise FigureError(f"{manifest}: '{key}' is required")
    size = str(raw.get("size", "figure"))
    if size not in SIZES:
        raise FigureError(f"{manifest}: size must be one of {list(SIZES)}")
    # A figure with no generator is allowed, but it will read as uncheckable
    # for the rest of its life and the loader does not pretend otherwise.
    generator = str(raw.get("generator") or "")
    if generator and ":" not in generator:
        raise FigureError(f"{manifest}: generator is 'module:callable'")
    return Figure(
        slug=str(raw["slug"]), title=str(raw["title"]),
        question=str(raw["question"]), directory=directory,
        generator=generator, source=str(raw.get("source") or ""),
        findings=str(raw.get("findings") or ""), page=str(raw.get("page") or ""),
        data=str(raw.get("data") or "data.json"), size=size,
        tolerance=float(raw.get("tolerance", 1e-6)))


def load_all(root: Optional[str] = None) -> Dict[str, Figure]:
    where = root or _DEFAULT_DIR
    if not os.path.isdir(where):
        return {}
    out: Dict[str, Figure] = {}
    for entry in sorted(os.listdir(where)):
        directory = os.path.join(where, entry)
        if entry.startswith("_") or not os.path.isdir(directory):
            continue
        if not os.path.exists(os.path.join(directory, "figure.yaml")):
            continue
        figure = load_figure(directory)
        out[figure.slug] = figure
    return out


# ---------------------------------------------------------------- generating

def generate(figure: Figure) -> Dict[str, Any]:
    """Run the figure's declared generator and return its table.

    The source is read and compiled on every call rather than imported. The
    import machinery will reuse a cached `.pyc` when a file's size and mtime
    both look unchanged, and an edit that keeps the byte count inside the same
    second does look unchanged — so a tool whose entire job is noticing that
    the numbers moved would quietly run the old code. Found by a test that
    swapped one constant for another of the same length.
    """
    if not figure.generator:
        raise FigureError(f"{figure.slug}: declares no generator")
    module_name, _, attribute = figure.generator.partition(":")
    path = os.path.join(figure.directory, f"{module_name}.py")
    if not os.path.exists(path):
        raise FigureError(f"{figure.slug}: no {module_name}.py in {figure.directory}")
    with open(path) as fh:
        source = fh.read()
    namespace: Dict[str, Any] = {"__file__": path, "__name__": f"figure_{module_name}"}
    exec(compile(source, path, "exec"), namespace)          # noqa: S102 — our own file
    call = namespace.get(attribute)
    if not callable(call):
        raise FigureError(f"{figure.slug}: {module_name}.py has no {attribute}()")
    table = call()
    if not isinstance(table, dict):
        raise FigureError(f"{figure.slug}: {figure.generator} must return a dict")
    return table


def read(figure: Figure) -> Optional[Dict[str, Any]]:
    if not os.path.exists(figure.data_path):
        return None
    with open(figure.data_path) as fh:
        return json.load(fh)


def write(figure: Figure, table: Mapping[str, Any]) -> str:
    """Write the table, stamped. The stamp is what `check` has to work with."""
    body = {**table, "_provenance": {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": figure.generator, "source": figure.source,
        "digest": digest(table)}}
    with open(figure.data_path, "w") as fh:
        json.dump(body, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return figure.data_path


def digest(table: Mapping[str, Any]) -> str:
    stripped = {k: v for k, v in table.items() if k != "_provenance"}
    return hashlib.sha256(
        json.dumps(stripped, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- freshness

@dataclass
class Freshness:
    slug: str
    state: str
    reason: str = ""
    moved: List[Tuple[str, Any, Any, float]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.state == FRESH

    def summary(self) -> str:
        if self.state == FRESH:
            return f"{self.slug}: fresh"
        if self.state == MISSING:
            return f"{self.slug}: never generated"
        if self.state == UNCHECKABLE:
            return f"{self.slug}: UNCHECKABLE — {self.reason}"
        worst = max(self.moved, key=lambda m: m[3]) if self.moved else None
        head = f"{self.slug}: STALE — {len(self.moved)} value(s) moved"
        if worst:
            head += (f"; worst {worst[0]} {worst[1]!r} → {worst[2]!r} "
                     f"({worst[3]:.2%})")
        return head


def check(figure: Figure) -> Freshness:
    """Re-run the generator and compare. Never writes, never raises."""
    stored = read(figure)
    if stored is None:
        return Freshness(figure.slug, MISSING)
    if not figure.generator:
        return Freshness(figure.slug, UNCHECKABLE, "the figure declares no generator")
    try:
        fresh_table = generate(figure)
    except Exception as exc:
        return Freshness(figure.slug, UNCHECKABLE, f"{type(exc).__name__}: {exc}")

    moved = _diff({k: v for k, v in stored.items() if k != "_provenance"},
                  fresh_table, figure.tolerance)
    if not moved:
        return Freshness(figure.slug, FRESH)
    return Freshness(figure.slug, STALE, moved=moved)


def _diff(old: Any, new: Any, tolerance: float, path: str = "") -> List[Tuple]:
    """Every leaf that moved by more than the figure's tolerance."""
    out: List[Tuple] = []
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        for key in sorted(set(old) | set(new)):
            where = f"{path}.{key}" if path else str(key)
            if key not in old:
                out.append((where, None, new[key], 1.0))
            elif key not in new:
                out.append((where, old[key], None, 1.0))
            else:
                out.extend(_diff(old[key], new[key], tolerance, where))
        return out
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return [(path or "<root>", f"{len(old)} items", f"{len(new)} items", 1.0)]
        for index, (a, b) in enumerate(zip(old, new)):
            out.extend(_diff(a, b, tolerance, f"{path}[{index}]"))
        return out
    if isinstance(old, (int, float)) and isinstance(new, (int, float)) \
            and not isinstance(old, bool) and not isinstance(new, bool):
        if old == new:
            return []
        scale = max(abs(float(old)), abs(float(new)))
        relative = 1.0 if scale == 0 else abs(float(new) - float(old)) / scale
        if relative <= tolerance or (math.isnan(old) and math.isnan(new)):
            return []
        return [(path or "<root>", old, new, relative)]
    return [] if old == new else [(path or "<root>", old, new, 1.0)]
