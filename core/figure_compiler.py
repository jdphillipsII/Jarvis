"""Turning a declaration into a drawing.

The genome says a part sits on another part. This works out where that is.

That division is the whole point. A third of every anatomy build is vector
arithmetic — where does this go, given what it rests on — and it is the part a
model on one card is worst at and fails invisibly at. Here it is a solve:
each part's host is already placed, so its own position is the host's plus an
offset in the host's frame. Nothing guesses.

Two properties fall out of the genome's support rule rather than being added:

**Declaration order is painter's order.** A part may only sit on a part
declared before it, so a part is always emitted after the thing it stands on —
which is back-to-front, bottom-to-top, the order the kit wants.

**Nothing floats.** Every part's z is derived from its host's top, so a part
cannot be left hanging at a coordinate somebody typed. The only way to be off
the ground is to say so.

The compiler emits a `build.mjs` rather than SVG. The kit is JavaScript and so
is the page assembly, so emitting JS means not reimplementing either — and the
output is a file a person can take over and extend, the same reason
`archetypes.instantiate` hands back a part document instead of geometry.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .figure_genome import GROUND, KINDS, FigureGenome, Part
from .topology import Pointer

_REF = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


class CompileError(ValueError):
    """The genome is structurally sound but cannot be drawn as written."""


@dataclass
class Placed:
    part: Part
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0                 # the part's own floor
    height: float = 0.0
    radius: float = 0.0
    plan: Tuple[float, float] = (0.0, 0.0)      # width, depth
    fields: Dict[str, Any] = field(default_factory=dict)

    @property
    def top(self) -> float:
        return self.z + self.height

    @property
    def centre(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def corners(self) -> List[Tuple[float, float]]:
        w, d = self.plan
        return [(self.x - w / 2, self.y - d / 2), (self.x + w / 2, self.y - d / 2),
                (self.x + w / 2, self.y + d / 2), (self.x - w / 2, self.y + d / 2)]


def resolve(value: Any, params: Mapping[str, float]) -> Any:
    """Substitute $refs. A bare "$name" keeps its type; inside a string it is
    spliced, so "$w * 0.25" stays an expression for the emitter to evaluate."""
    if isinstance(value, str):
        whole = _REF.fullmatch(value.strip())
        if whole:
            if whole.group(1) not in params:
                raise CompileError(f"undeclared ${whole.group(1)}")
            return params[whole.group(1)]
        def swap(match):
            name = match.group(1)
            if name not in params:
                raise CompileError(f"undeclared ${name}")
            return repr(params[name])
        return _REF.sub(swap, value)
    if isinstance(value, Mapping):
        return {k: resolve(v, params) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [resolve(v, params) for v in value]
    return value


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if isinstance(value, str):
            try:
                return float(eval(value, {"__builtins__": {}}, {}))  # noqa: S307
            except Exception:
                raise CompileError(f"{where}: '{value}' is not a number") from None
        raise CompileError(f"{where}: expected a number, got {value!r}")
    return float(value)


# ---------------------------------------------------------------- placement

def place(genome: FigureGenome) -> Dict[str, Placed]:
    """Solve every part's position from what it sits on.

    Lateral position is an offset in the host's frame (`at: {x, y}`), never an
    absolute coordinate — so a model that has never seen the figure cannot put
    a part somewhere there is nothing.
    """
    placed: Dict[str, Placed] = {}
    for part in genome.parts:
        fields = resolve(dict(part.fields), genome.params)
        spot = Placed(part=part, fields=fields)

        host: Optional[Placed] = None
        face = "top"
        if part.on != GROUND:
            name = part.host
            if name not in placed:
                raise CompileError(f"{part.id}: sits on '{name}', not yet placed")
            host = placed[name]
            if part.on.startswith("@"):
                face = Pointer.parse(part.on).role

        # `at` is an offset in the host's frame for a solid, and a placement
        # rule for marks that scatter over a host ("corners:bed"). A string
        # leaves the part at its host and is read by the emitter instead.
        offset = fields.get("at")
        if isinstance(offset, str):
            offset = {}
        elif offset is None:
            offset = {}
        elif not isinstance(offset, Mapping):
            raise CompileError(f"{part.id}: 'at' is an offset like {{x: 0, y: 0}} "
                               f"or a rule like 'corners:<part>'")
        dx = _number(offset.get("x", 0), f"{part.id}.at.x")
        dy = _number(offset.get("y", 0), f"{part.id}.at.y")
        dz = _number(offset.get("z", 0), f"{part.id}.at.z")

        if host is None:
            spot.x, spot.y, spot.z = dx, dy, dz
        else:
            spot.x, spot.y = host.x + dx, host.y + dy
            spot.z = _floor(host, face, dz, part.id)

        spot.height = _number(fields.get("height", 0), f"{part.id}.height")
        if "radius" in fields:
            spot.radius = _number(fields["radius"], f"{part.id}.radius")
        plan = fields.get("plan") or {}
        if plan:
            spot.plan = (_number(plan.get("w", 0), f"{part.id}.plan.w"),
                         _number(plan.get("d", 0), f"{part.id}.plan.d"))
        if part.kind == "turned":
            spot.height, spot.radius = _turned(spot, part)
        placed[part.id] = spot
    return placed


def _floor(host: Placed, face: str, dz: float, who: str) -> float:
    """Where a part's own floor sits, given the face it was put on."""
    if face == "top":
        return host.top + dz
    if face == "bottom":
        return host.z - dz
    if face in ("side", "wall", "face", "rim"):
        # Against a vertical face: the part keeps the host's floor unless the
        # genome lifts it. A side-mounted part that said nothing would
        # otherwise land at the host's top, which is not what "on the side"
        # means to anyone.
        return host.z + dz
    raise CompileError(f"{who}: nothing sits on a '{face}'")


def _turned(spot: Placed, part: Part) -> Tuple[float, float]:
    profile = spot.fields.get("profile")
    if not isinstance(profile, (list, tuple)) or len(profile) < 2:
        raise CompileError(f"{part.id}: a turned body needs a profile of "
                           f"[along, radius] pairs")
    rows = [(float(s), float(r)) for s, r in profile]
    return rows[-1][0] - rows[0][0], max(r for _, r in rows)


# ---------------------------------------------------------------- emission

def emit(genome: FigureGenome, placed: Optional[Mapping[str, Placed]] = None,
         width: int = 760, height: int = 520) -> str:
    """A build.mjs that draws the genome. Readable, and takeable-over."""
    placed = placed or place(genome)
    lines = [
        "// Generated from a figure genome by core/figure_compiler.py.",
        "// Positions are solved from each part's `on:`; edit the genome, not this.",
        'import { writeFileSync } from "node:fs";',
        'import { dirname, join } from "node:path";',
        'import { fileURLToPath } from "node:url";',
        "",
        "const HERE = dirname(fileURLToPath(import.meta.url));",
        'const ROOT = process.env.ANATOMY_ROOT',
        '  || join(HERE, "..", "..", ".claude", "skills", "anatomy");',
        'const k = await import(join(ROOT, "kit", "iso-kit.mjs"));',
        'const G = await import(join(ROOT, "kit", "lathe.mjs"));',
        'const { kitScript } = await import(join(ROOT, "scripts", "inline-kit.mjs"));',
        'const theme = process.argv.includes("--light") ? "light" : "dark";',
        "",
        f"const WIDTH = {width}, HEIGHT = {height};",
    ]

    extent = _extent(placed)
    camera = genome.camera or {}
    lines += [
        f"const P = k.fitProjection({json.dumps(extent)}, WIDTH, HEIGHT, "
        f"{{ pad: 28, azimuth: {camera.get('azimuth', 44)} }});",
        "const at = (p) => k.iso(p, P);",
        "const S = (paths, style) => k.solidSvg(paths, style);",
        "const L = (d, style) => k.lineSvg(d, style);",
        "const D = (points, style) => k.dotsSvg(points, style);",
        "const body = [];",
        "",
    ]
    for part in genome.parts:
        lines.append(f"// {part.id} — {part.kind}"
                     + (f", {part.note}" if part.note else ""))
        lines.extend(_draw(placed[part.id], placed))
        lines.append("")

    lit = genome.lit
    lines += [
        "const svg = k.figureSvg({ width: WIDTH, height: HEIGHT, "
        'body: body.join("") });',
        "const page = k.plateHtml({",
        '  fig: "Fig 1",',
        f"  title: {json.dumps(_title(genome))},",
        f"  hint: {json.dumps('Hover to drive the mechanism')},",
        f"  readout: {json.dumps(_one_line(genome.subject))},",
        "  keys: [",
        f"    {{ mark: \"lit\", label: {json.dumps(_one_line(genome.subject))} }},",
        "  ],",
        f"  caption: {json.dumps(_one_line(genome.question))},",
        '  body: `<div class="iso-stage" tabindex="0">${svg}</div>`,',
        "});",
        f"const name = theme === \"light\" ? \"{genome.figure}-light.html\" "
        f": \"{genome.figure}.html\";",
        "writeFileSync(join(HERE, name), k.pageHtml({ title: "
        f"{json.dumps(_title(genome))}, theme, body: page, "
        "script: kitScript() }));",
        'console.log("wrote", name);',
    ]
    if lit is None:                                   # the loader forbids this
        raise CompileError("no lit subject")
    return "\n".join(lines) + "\n"


def _title(genome: FigureGenome) -> str:
    return genome.figure.replace("_", " ").title()


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _extent(placed: Mapping[str, Placed]) -> List[List[float]]:
    """Every corner the camera has to hold, so nothing is framed out."""
    points: List[List[float]] = []
    for spot in placed.values():
        reach = max(spot.radius, max(spot.plan) / 2 if any(spot.plan) else 0.0)
        for sx in (-1, 1):
            for sy in (-1, 1):
                points.append([spot.x + sx * reach, spot.y + sy * reach, spot.z])
                points.append([spot.x + sx * reach, spot.y + sy * reach, spot.top])
    return points or [[0, 0, 0]]


def _plan(spot: Placed) -> str:
    w, d = spot.plan
    r = _number(spot.fields.get("r", min(w, d) * 0.06 if w and d else 0), "r")
    return (f"{{ x: {spot.x - w / 2:g}, y: {spot.y - d / 2:g}, "
            f"w: {w:g}, d: {d:g}, r: {r:g} }}")


def _draw(spot: Placed, placed: Mapping[str, Placed]) -> List[str]:
    kind, part = spot.part.kind, spot.part
    tone = f'{{ tone: "{part.tone}"{", lit: true" if part.lit else ""} }}'
    out: List[str] = []
    if kind == "slab":
        out.append(f"body.push(S(k.slabOf({_plan(spot)}, {spot.z:g}, "
                   f"{spot.height:g}, P, 6, 0.8), {tone}));")
    elif kind == "cylinder":
        out.append(f"body.push(S(k.cylinder({spot.x:g}, {spot.y:g}, "
                   f"{spot.radius:g}, {spot.z:g}, {spot.height:g}, P, 28), {tone}));")
    elif kind == "knurl":
        out.append(f"body.push(S(k.cylinder({spot.x:g}, {spot.y:g}, "
                   f"{spot.radius:g}, {spot.z:g}, {spot.height:g}, P, 28), {tone}));")
        out.append(f"body.push(L(k.knurl({spot.x:g}, {spot.y:g}, {spot.radius:g}, "
                   f"{spot.top:g}, {spot.height:g}, P, 18), {{ tone: \"lo\" }}));")
    elif kind == "turned":
        rows = [[float(s), float(r)] for s, r in spot.fields["profile"]]
        out.append(f"body.push(S(G.lathe({json.dumps(rows)}, "
                   f"G.frameAlong([{spot.x:g}, {spot.y:g}, {spot.z:g}], [0, 0, 1]), "
                   f"P, {{ steps: 48 }}), {tone}));")
    elif kind == "disc":
        out.append(f"body.push(S(k.cylinder({spot.x:g}, {spot.y:g}, "
                   f"{spot.radius:g}, {spot.z:g}, "
                   f"{max(spot.height, 0.8):g}, P, 36), {tone}));")
    elif kind == "ring":
        out.append(f"body.push(L(k.ring({spot.x:g}, {spot.y:g}, {spot.radius:g}, "
                   f"{spot.z:g}, P, 36), {{ tone: \"{part.tone}\" }}));")
    elif kind == "rule":
        a, b = _ends(spot)
        out.append(f"body.push(L(k.segment({json.dumps(a)}, {json.dumps(b)}, P), "
                   f"{{ tone: \"{part.tone}\" }}));")
    elif kind == "ticks":
        out.extend(_ticks(spot))
    elif kind == "dots":
        out.append(f"body.push(D({_points(spot, placed)}, {{ size: 0.5 }}));")
    elif kind == "pattern":
        out.extend(_pattern(spot, placed))
    else:                                              # the loader forbids this
        raise CompileError(f"{part.id}: no emitter for kind '{kind}'")
    return out


def _ends(spot: Placed) -> Tuple[List[float], List[float]]:
    a = spot.fields.get("from")
    b = spot.fields.get("to")
    if not (isinstance(a, (list, tuple)) and isinstance(b, (list, tuple))):
        raise CompileError(f"{spot.part.id}: from and to are [x, y, z] offsets "
                           f"from the part's own position")
    base = (spot.x, spot.y, spot.z)
    return ([base[i] + _number(a[i], "from") for i in range(3)],
            [base[i] + _number(b[i], "to") for i in range(3)])


def _ticks(spot: Placed) -> List[str]:
    a, b = _ends(spot)
    count = int(_number(spot.fields.get("count", 10), "count"))
    every = int(_number(spot.fields.get("every", 5), "every"))
    reach = _number(spot.fields.get("reach", 5), "reach")
    long = _number(spot.fields.get("long", reach * 2), "long")
    minor, major = [], []
    for index in range(count + 1):
        f = index / count if count else 0.0
        point = [a[i] + (b[i] - a[i]) * f for i in range(3)]
        far = point[:]
        far[0] += long if index % every == 0 else reach
        (major if index % every == 0 else minor).append(
            f"k.segment({json.dumps(point)}, {json.dumps(far)}, P)")
    return [f"body.push(L([{', '.join(minor)}].join(''), {{ tone: \"lo\" }}));",
            f"body.push(L([{', '.join(major)}].join(''), "
            f"{{ tone: \"{spot.part.tone}\" }}));"]


def _points(spot: Placed, placed: Mapping[str, Placed]) -> str:
    where = spot.fields.get("at")
    if isinstance(where, str) and where.startswith("corners:"):
        host = placed.get(where.split(":", 1)[1])
        if host is None:
            raise CompileError(f"{spot.part.id}: no part '{where.split(':')[1]}'")
        inset = _number(spot.fields.get("inset", 10), "inset")
        w, d = host.plan
        corners = [[host.x + sx * (w / 2 - inset), host.y + sy * (d / 2 - inset),
                    host.top] for sx in (-1, 1) for sy in (-1, 1)]
        return "[" + ", ".join(f"at({json.dumps(c)})" for c in corners) + "]"
    return f"[at([{spot.x:g}, {spot.y:g}, {spot.top:g}])]"


def _pattern(spot: Placed, placed: Mapping[str, Placed]) -> List[str]:
    source = placed.get(str(spot.fields.get("of") or ""))
    if source is None:
        raise CompileError(f"{spot.part.id}: repeats '{spot.fields.get('of')}', "
                           f"which is not a part")
    count = int(_number(spot.fields.get("count", 2), "count"))
    step = spot.fields.get("step") or {}
    dx = _number(step.get("x", 0), "step.x")
    dy = _number(step.get("y", 0), "step.y")
    out = []
    for index in range(1, count):
        clone = Placed(part=source.part, x=source.x + dx * index,
                       y=source.y + dy * index, z=source.z, height=source.height,
                       radius=source.radius, plan=source.plan, fields=source.fields)
        out.extend(_draw(clone, placed))
    return out
