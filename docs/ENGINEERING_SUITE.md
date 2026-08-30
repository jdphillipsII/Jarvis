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

## 1. MODEL — make and change the thing

**Parametric / program-driven** (the model writes a *program*, not geometry — which is what makes "3 mm thicker" a one-token edit)

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| Atlas `PartGenome` | in-process | actuator | Unit-typed YAML, `$param` refs, closed op vocabulary. Compiler implements 5 of 17 declared ops — the gap. |
| Atlas `AssemblyGenome` | in-process | actuator | Children, bindings, placements; interference + clearance checks |
| `build123d` | stdio MCP | actuator | OCCT B-rep, exact, STEP export |
| CadQuery | stdio MCP | actuator | Alternative fluent API over the same kernel |
| OpenSCAD | stdio MCP | actuator | Fast jigs, fixtures, throwaway parts |

**Interactive CAD**

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| **Onshape** | HTTP MCP | actuator | **Best agent target.** Full REST API: documents, part studios, feature add/modify, assemblies, mass properties, export. FeatureScript for custom features. |
| **SolidWorks** | Windows bridge | actuator | COM via pywin32; requires SW running. For models that already live there. |
| FreeCAD | stdio MCP | actuator | `freecadcmd` headless — conversion, batch ops, Path workbench |
| Blender | stdio MCP | actuator | `bpy` — organic geometry, mesh repair, renders for review |

**Electronics**

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| KiCad | stdio MCP | actuator | `kicad-cli` — schematic, PCB, netlist, gerbers, 3D export |

**2D / flat**

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| Inkscape | stdio MCP | actuator | Panel layouts, laser paths, DXF/SVG |
| `ezdxf` | stdio MCP | actuator | Programmatic DXF read/write |

**Mesh utilities**

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| `trimesh` | stdio MCP | advisory | Inspect, measure, boolean, convex hull |
| `admesh` / MeshLab | stdio MCP | actuator | Repair STLs before printing |

**The generative layer**

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| `atlas_cad.topology.propose_with` | in-process | actuator | LLM proposes moves, the grammar disposes. Invalid states are made *inexpressible* by round-tripping through the validating loader — a stronger guarantee than schema validation. |

---

## 2. ANALYZE — find out if it works

**Thermal / fluids**

| Tool | Interface | Agency | Speed |
|---|---|---|---|
| `atlas_cad.thermal` | in-process | advisory | **0.083 ms** — R_th, Δp, Reynolds, worst case under maldistribution |
| `atlas_cad.tier2_fd` | in-process | advisory | ~50 ms — *independent* 2-D FD method, returns agree / refine / disagree |
| `atlas_cad.flow_network` | in-process | advisory | ms — loop network solve |
| **CoolProp** | stdio MCP | advisory | µs — real fluid properties. **Add this early**: near-critical CO₂ at 75–80 bar is exactly where ideal-gas assumptions fall apart, and it is the working fluid for the whole cooling programme. |
| OpenFOAM | stdio MCP | advisory | minutes–hours, offer/notify |
| Elmer | stdio MCP | advisory | minutes, multiphysics |

**Structural**

| Tool | Interface | Agency | Speed |
|---|---|---|---|
| `atlas_cad.structural` | in-process | advisory | sub-ms — cantilever bending, safety factor |
| CalculiX | stdio MCP | advisory | minutes — real FEA |

**Electrical**

| Tool | Interface | Agency |
|---|---|---|
| ngspice | stdio MCP | advisory |
| KiCad ERC / DRC | stdio MCP | advisory |
| `scikit-rf` | stdio MCP | advisory |

**Verification and uncertainty**

| Tool | Interface | Agency | Speed |
|---|---|---|---|
| `atlas_cad.verify_part` | in-process | advisory | **0.31 ms** — 13 provenanced rules; certificate names what it could *not* check |
| `atlas_cad.verify_assembly` | in-process | advisory | interference, clearance, mass/CG rollup |
| `atlas_cad.robustness` | in-process | advisory | ~20 ms — 64-sample sweep |
| `atlas_spec.validator` | in-process | advisory | dimensional analysis over constraint expressions |
| Tolerance stack-up (Monte Carlo) | — | advisory | **not yet built** — Atlas lists it as deferred |

**Search and optimisation**

| Tool | Interface | Agency | Speed |
|---|---|---|---|
| `atlas_cad.evolve` | stdio MCP | advisory | seconds–minutes — NSGA-II, returns a Pareto portfolio with STEP files |
| `atlas_cad.qd` | stdio MCP | advisory | MAP-Elites over behaviour space |
| `scipy.optimize` / `cma` | in-process | advisory | general-purpose |

---

## 3. SOURCE — find what to make it from and buy it with

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| Atlas `materials.py` | in-process | advisory | 7 curated materials with real properties |
| Atlas `processes.py` | in-process | advisory | 13 processes with ISO 2768 tolerance classes |
| Materials Project API | HTTP MCP | advisory | `MP_API_KEY` already in Atlas `.env.example` |
| Digi-Key / Mouser API | HTTP MCP | advisory | stock, pricing, lead time |
| Octopart / Nexar | HTTP MCP | advisory | cross-distributor part search |
| McMaster-Carr | stdio MCP | advisory | no public API — part-number lookup only |
| Datasheet fetch + extract | stdio MCP | advisory | PDF → parameters |
| BOM generation | stdio MCP | actuator | from KiCad netlist or CAD assembly |
| Cost rollup | in-process | advisory | per-material, per-process, per-quantity |

**Deliberately out of scope: purchasing.** Reading a price is advisory. Spending
money is not something an autonomous agent should do, at any agency level.

---

## 4. FABRICATE — turn it into an object

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| PrusaSlicer / OrcaSlicer | stdio MCP | actuator | `--export-gcode`; produces a file, reversible |
| FreeCAD Path | stdio MCP | actuator | CAM toolpaths |
| G-code lint / verify | stdio MCP | advisory | travel limits, feed sanity, collision pre-check |
| Klipper (Moonraker API) | HTTP MCP | **agentic** | start / pause / abort a print |
| OctoPrint API | HTTP MCP | **agentic** | same |
| grbl / LinuxCNC sender | stdio MCP | **agentic** | CNC job start |
| Laser controller | stdio MCP | **agentic** | job start |
| Filament / stock tracking | in-process | actuator | what is loaded, what is left |

Slicing writes a file. Starting a machine moves metal. The line is drawn there,
and machine-start confirms **every time** with no remembered approvals.

---

## 5. MEASURE — find out what actually happened

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| Bench rig (ADS1220, thermistors, turbidity) | stdio MCP | advisory to read, **agentic** to drive | already built in `rig/` |
| SCPI instruments via `pyvisa` | stdio MCP | advisory to read, **agentic** to source | DMM, PSU, scope, function gen |
| Serial / USB DAQ | stdio MCP | advisory | generic logging |
| `local/batch_*.py` kit | stdio MCP | advisory | self-contained, resume-capable, self-certifying against pre-registered gates |
| Logging → CSV / Parquet | in-process | actuator | |
| `scipy.stats` | in-process | advisory | fits, intervals, hypothesis tests |
| Atlas `surrogate.conformal` | in-process | advisory | calibrated uncertainty |
| **Predicted vs measured** | in-process | advisory | **the loop closure** — feeds the delta back into MODEL |

Reading a sensor is safe. Energising a heater is not. The split is by *effect*,
never by device.

---

## 6. RECORD — make sure it counts

| Tool | Interface | Agency | Notes |
|---|---|---|---|
| git | stdio MCP | actuator | code, geometry, results, notebook |
| Atlas claims ledger | in-process | actuator | machine-readable belief layer, lineage-linked |
| Atlas certificates | in-process | advisory | provenance + computed dark regions |
| `knowledge/audit.jsonl` | in-process | actuator | append-only; every command and gate decision |
| Run manifests (seed, commit, model version) | in-process | actuator | reproducibility |
| Lab notebook entries | stdio MCP | actuator | markdown, timestamped |
| Report / brief generation | stdio MCP | actuator | Atlas already has an under-NDA brief generator |

Nothing is worth automating if the record of it is manual. Every stage above
must be able to write its own entry.

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

## Gaps worth naming

Things the enumeration above shows are missing rather than merely unbuilt:

- **CoolProp is not wired anywhere**, and the entire cooling programme runs on
  near-critical CO₂ at 75–80 bar — precisely the regime where ideal-gas
  approximations stop being approximations. This belongs in tier 1, not later.
- **Tolerance stack-up** is listed as deferred in Atlas's own design doc. Every
  process in the catalogue carries an ISO 2768 class, so the inputs exist; the
  Monte Carlo over them does not.
- **The `PartGenome` compiler implements 5 of its 17 declared ops.** `hole`,
  `fillet`, `chamfer`, `shell`, `rib`, `thread` and the pattern ops are accepted
  by the schema and then honestly recorded as dark regions. The checker is the
  hard half and it is done; the generator is the gap.
- **Predicted-vs-measured has no home.** Every other arrow in the loop exists in
  some form. This one — the comparison that makes the loop a loop rather than a
  line — is not implemented anywhere.
