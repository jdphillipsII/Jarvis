# The engineering suite

The goal is the workshop loop, closed: describe intent, see geometry, run the
numbers, make the thing, measure it, and have the whole chain recorded. Six
stages, each a family of tools behind the same intent bus and the same consent
gate.

    MODEL ──► ANALYZE ──► SOURCE ──► FABRICATE ──► MEASURE ──► RECORD
      ▲                                                          │
      └──────────────────────────────────────────────────────────┘

Every tool is one of three agency levels. **Advisory** reads and reports and can
run unattended. **Actuator** changes a file or a document and returns a proposal
first. **Agentic** touches hardware or runs arbitrary code, and confirms *every
time* — no remembered approvals, no batching.

---

## Architecture: bridges, not imports

Tools live in different places — some are Python libraries, some are CLIs, some
are cloud APIs, and SolidWorks only exists on the Windows side of the dual boot.
Rather than teach JARVIS about each, every family gets an **MCP server that runs
where the tool lives** and speaks the same protocol back.

    JARVIS / Hermes
        │
        ├── (in-process)     Atlas physics, units, verify
        ├── stdio MCP        build123d, FreeCAD, KiCad, slicer, git
        ├── HTTP MCP         Onshape  (cloud REST API)
        └── HTTP MCP         solidworks-bridge  ← runs on WINDOWS, over Tailscale

The Windows bridge is the interesting one: a small service using the SolidWorks
COM API, reachable from Linux over the tailnet. It means the Linux side never
needs to know SolidWorks exists — it is just another MCP server.

---

## 1. MODEL

| Tool | How | Agency | Notes |
|---|---|---|---|
| **Atlas `PartGenome`** | in-process | actuator | Unit-typed YAML with `$param` refs and a closed op vocabulary — the shape an LLM emits well. Compiler currently implements 5 of 17 declared ops; extending it is the single highest-value CAD task. |
| **build123d / CadQuery** | stdio MCP | actuator | Python, parametric, exact B-rep via OCCT. The model writes a *program*, not geometry — which is what makes edits like "3mm thicker" trivial. |
| **Onshape** | HTTP MCP | actuator | **Best agent target.** Complete REST API: documents, part studios, feature add/modify, assemblies, mass properties, STEP/STL export. Cloud-hosted, so no local install and no OS problem. |
| **SolidWorks** | Windows bridge | actuator | COM API via pywin32. Requires SW running on the Windows side. Use for things already modelled there; prefer Onshape for new agent-driven work. |
| **FreeCAD** | stdio MCP | actuator | `freecadcmd` headless. Good for format conversion and batch ops. |
| **OpenSCAD** | stdio MCP | actuator | Fast throwaway parametric parts, fixtures, jigs. |
| **KiCad** | stdio MCP | actuator | `kicad-cli` — ERC/DRC, netlists, gerbers, 3D export. |

## 2. ANALYZE

| Tool | How | Agency | Speed |
|---|---|---|---|
| **`atlas_cad.verify_part`** | in-process | advisory | **0.31 ms** — rule battery with provenance, returns a certificate naming what it could NOT check |
| **`atlas_cad.thermal`** | in-process | advisory | **0.083 ms** — R_th, pressure drop, Reynolds, worst-case under maldistribution |
| **`atlas_cad.structural`** | in-process | advisory | sub-ms |
| **`atlas_cad.tier2_fd`** | in-process | advisory | ~50 ms — an *independent* second method returning agree/refine/disagree |
| **`atlas_cad.robustness`** | in-process | advisory | ~20 ms — 64-sample sweep |
| **ngspice** | stdio MCP | advisory | circuit sim |
| **CalculiX / Elmer** | stdio MCP | advisory | minutes — offer/notify |
| **OpenFOAM** | stdio MCP | advisory | minutes to hours — offer/notify, never a voice turn |
| **Atlas campaigns** | stdio MCP | advisory | seconds to tens of seconds — returns a Pareto portfolio with STEP files |

The tier-2 cross-check deserves special mention: it is a genuinely independent
calculation, so "how much should I trust that number" becomes something JARVIS
can *say out loud* rather than something you have to judge.

## 3. SOURCE

| Tool | How | Agency |
|---|---|---|
| **Materials Project API** | HTTP MCP | advisory |
| **Atlas material/process catalogs** | in-process | advisory |
| **Supplier search** (McMaster, Digi-Key, Mouser) | HTTP MCP | advisory |
| **Datasheet retrieval + extraction** | stdio MCP | advisory |

Purchasing stays **out of scope on purpose.** Reading a price is advisory;
spending money is not a thing an autonomous agent should do.

## 4. FABRICATE

| Tool | How | Agency |
|---|---|---|
| **PrusaSlicer / OrcaSlicer** | stdio MCP | actuator |
| **CAM post-processing** | stdio MCP | actuator |
| **Klipper / OctoPrint** | HTTP MCP | **agentic** |
| **Laser / CNC job start** | — | **agentic** |

Slicing produces a file and is reversible. Starting a machine is not — those
confirm every time, with no memory.

## 5. MEASURE

| Tool | How | Agency |
|---|---|---|
| **The bench rig** (ADS1220, thermistors, turbidity) | stdio MCP | advisory to read, **agentic** to drive |
| **`local/batch_*.py` kit** | stdio MCP | advisory |
| **SCPI instruments** (DMM, PSU, scope) | stdio MCP | advisory to read, **agentic** to source power |

The batch kit is already shaped for this: self-contained, resume-capable, and
self-certifying against pre-registered gates. Wrapping it is mostly plumbing.

Reading a sensor is safe. Energizing a heater is not. The split is by *effect*,
not by device.

## 6. RECORD

| Tool | How | Agency |
|---|---|---|
| **git** (lab notebook, results, geometry) | stdio MCP | actuator |
| **Atlas claims ledger** | in-process | actuator |
| **Certificates + provenance** | in-process | advisory |

Nothing is worth automating if the record of it is manual. Every stage above
should be able to write its own entry.

---

## Cross-cutting: units are an argument type

`atlas_spec/units.py` is a real 7-dimension SI system — `Dim` as frozen
`Fraction` exponents over `(kg, m, s, A, K, mol, cd)`, with `parse_unit`
handling `"W/cm^2"`, `"GHz"`, `"m/s^2"`. Zero dependencies.

Wiring it into the schema validator as a `quantity` argument type turns
dimensional mistakes into a **fail-closed check at the call boundary**, instead
of a plausible wrong number three steps downstream. Do this before any physics
tool goes live; it makes everything after it safer.

---

## Build order

Sequenced by value per hour, not by ambition.

1. **`units.convert` + the `quantity` argument type** — small, and everything
   after it inherits the safety
2. **Atlas physics tools** (thermal, structural, verify, cross-check) — real
   answers at voice speed, from code that already exists and is tested
3. **git lab notebook** — cheap, and it means the agent's work leaves a trace
4. **Onshape MCP** — the first real "describe it, see geometry" surface
5. **Extend the `PartGenome` compiler** past its 5 implemented ops — `hole`,
   `fillet`, `chamfer`, `shell`, patterns. The checker is done; the generator
   is the gap.
6. **Slicer + print** — closes the loop to a physical object
7. **The rig** — closes the loop back to measurement
8. **SolidWorks bridge** — last, because Onshape covers new work and this is
   only needed for models that already live there
