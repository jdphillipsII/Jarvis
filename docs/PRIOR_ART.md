# Prior art

Surveyed 2026-09-18, before building the MODEL and ANALYZE stages of
[ENGINEERING_SUITE.md](ENGINEERING_SUITE.md).

The question was whether we were reinventing wheels. Partly, yes: the
CAD-driver layer is commodity and should be borrowed. The layer above it —
consent, agency, physics, archetypes — is empty, and that is where the work is.

This file exists so the survey is a record rather than a memory. Star counts
are as of the survey date and will drift; the verdicts are what matter.

---

## The finding in one line

**Every CAD-over-MCP project found executes immediately.** Not one of them has
a proposal/confirm step, an agency ceiling, or a fluid-properties tier. They
are drivers. We are building the thing that decides whether to use a driver.

---

## What exists

### CAD over MCP — crowded and active

| Project | ★ | What it is |
|---|---|---|
| `wzyn20051216/solidworks-automation-skill` | 943 | Python SolidWorks COM automation, exposed over MCP |
| `daobataotie/CAD-MCP` | 557 | General CAD MCP server |
| `ghbalf/freecad-ai` | 506 | Natural language → 3D, MCP + Ollama |
| `jdilla1277/agentcad` | 128 | build123d + cadquery agent |
| `AuraFriday/Fusion-360-MCP-Server` | 126 | Fusion 360 |
| `U-C4N/Autocad-MCP` | 92 | 122 tools, dual COM + headless `ezdxf`, ISO GD&T and tolerance validation |
| `pzfreo/build123d-mcp` | 88 | "improve AI cognition when creating 3D CAD models" |
| `armpro24-blip/cad-cae-copilot` | 61 | spec → build123d → critique → CalculiX → `.aieng` package |
| `NeonGlay/inventor-mcp` | — | Autodesk Inventor |
| `Alfredoalv13/shapr3d-mcp` | — | Shapr3D |
| `almightyshui/Mechanical-AI-Skill` | — | DFM / DFA / FEA review |
| `chisomobanzi/Serpentine3D` | — | — |

### The architectural reference

`pascalorg/editor` — **24,076★**. An open-source 3D architectural editor:
local CLI, MCP tools, react-three-fiber, parametric design, local-first,
agent-skills. Wrong domain, right shape — it is the most-validated example of
the exact stack we are assembling, and worth reading for where it draws its
skill boundaries.

### Voice assistants

`leon-ai/leon` (17.5k★) is a different architecture entirely — modular NLP
skills, not a wake → endpoint → tool-call loop. `alxpez/alts` (81★) and
`dotradepro/SelenaCore` (23★) are thinner than what we run. Nothing found
improves on `core/endpointing.py`, `core/policy.py`, or the proposal gate.

### Teaching visualisation

Only one-off demos: `gpu-io` (1484★, a GPU compute library), `sciencelab3d`
(19★). **No general LLM → teaching-visualisation harness exists.** That gap is
real, not a wheel.

---

## cad-cae-copilot, in detail

Worth its own section because it independently arrived at nearly our
architecture, which is either reassuring or a warning depending on the day.

Its pipeline: engineering spec → MCP agent → build123d / OpenCASCADE →
named parts and topology pointers → critique / CAE setup / solver evidence →
a reproducible `.aieng` package.

Three ideas worth taking:

1. **Programs, not geometry.** build123d source is the artefact; the solid is a
   build product. Same instinct as `PartGenome`.
2. **`@face:*` stable topology pointers** that survive edits. This is the hard
   problem in parametric CAD agents — see [findings/2026-09-18-topology-pointers.md](findings/2026-09-18-topology-pointers.md).
3. **Deterministic critique.** Returns `design_rule_violation` backed by Python
   `require()` assertions rather than asking a model whether the design is
   good. The same "don't let the LLM judge" instinct behind our consent gate.
4. **`mesh_convergence`** doing GCI / Richardson extrapolation and returning
   `reliable` / `marginal` / `unreliable` — a solver result that grades its own
   trustworthiness, which is what `verify_part`'s certificate does for rules.

Its own stated maturity: **v0.1.0-alpha.4**, "Not production-certified CAD/CAE.
Outputs still require human engineering judgment." Excludes fatigue and
durability, excludes nonlinear contact, 3D SIMP experimental, freeform NURBS
listed as future work.

**Verdict: read it, port the ideas, do not depend on it.** An alpha package in
the path between a spec and a machine that moves metal is not a dependency we
want.

---

## Verdicts

### Adopt outright — do not rebuild

| What | Instead of |
|---|---|
| `wzyn20051216/solidworks-automation-skill` | writing our own COM bridge for the Windows side |
| `U-C4N/Autocad-MCP`'s headless `ezdxf` path | our own 2D/DXF tooling |
| `pzfreo/build123d-mcp`, `jdilla1277/agentcad` | our own build123d MCP layer |
| `ghbalf/freecad-ai` | our own FreeCAD driver |

All of them mount through [`core/bridges.py`](../core/bridges.py), which is the
condition of adoption: an external MCP server's tools are **not** trusted as
given. Each tool has to be named in `bridges/manifest.yaml` with an agency
level and a mutation flag before it is visible to the model at all. An
unclassified tool is not mounted — a new tool appearing upstream after an
update cannot silently gain the ability to act.

Also take from `Autocad-MCP`: its GD&T and tolerance validators, as a reference
for the tolerance stack-up gap named in the suite doc.

### Port the idea, write the code

- `@face:*` topology pointers → `core/topology.py`
- `mesh_convergence`'s reliable/marginal/unreliable grading → the shape any
  solver wrapper should return
- the `require()` critique pattern → already how `verify_part` works; extend it

### Keep hand-building — nothing out there has these

- **The consent gate.** Every CAD-MCP project surveyed executes on call.
- **The intent bus and the agency ceiling.** A tool above the level is not
  refused, it is invisible; probing for it is indistinguishable from a typo.
- **The physics tier.** Real CoolProp state points, two-phase refused rather
  than guessed, near-critical flagged. Everything surveyed either has no fluid
  properties or hardcodes water.
- **The archetype library.** `cad-cae-copilot` generates build123d from the
  spec every time. Nobody retrieves and adapts. That is how the work is
  actually done, and it is the reason spec → CAD keeps failing.
- **The teaching-visualisation harness.** Unclaimed.

---

## What this changes in the build order

The suite doc has the SolidWorks bridge at position 8, last, on the reasoning
that Onshape covers new work. That reasoning still holds for *building* it —
but adopting it costs a manifest entry rather than a service, so it moves to
wherever it is convenient. The work that remains ours is unchanged.
