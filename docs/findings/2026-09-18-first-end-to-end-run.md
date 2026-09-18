# First end-to-end run: problem → archetype → part → physics

**Date:** 2026-09-18
**Command:**

```
jarvis design coolant_phase=single_phase_liquid flow_regime=laminar \
  source_geometry=flat material_family=copper footprint="90 mm" \
  flow_distribution=parallel set:n_channels=32 at:flow="2 L/min" \
  --name dlc_plate_v3 \
  --manifold ~/atlas-research/atlas_cad/examples/manifold_block.part.yaml
```

Selects an archetype, adapts it, loads it through Atlas's own loader, runs the
checker battery and the physics the archetype declares, compares the analyses
against each other, and ends by naming what none of them covered.

It works. It also found four real problems, three of them in code written the
same week, which is the point of running a chain rather than testing its links.

---

## What it produced

| | |
|---|---|
| Archetype | `cold_plate.straight_channel` (applies; six conditions, none unchecked) |
| Adapted | `n_channels` 24 → 32, everything else at the archetype's default |
| Loader | clean, 0 findings |
| Checker battery | **17 rules passed, 0 failed**, 6 dark regions |
| R_th | **0.0389 K/W** (24 channels: 0.0500) |
| Δp | 280 Pa (24 channels: 374) |
| Re | 556, inside the archetype's own laminar claim |
| Cross-check (2-D FD) | **agree**, 2.2% deviation |
| Flow network | worst channel **65%** of mean; 0.040 vs 0.107 L/min across 32 channels |

---

## Finding 1 — the thermal worst case is not a bound

`evaluate_cold_plate` computes `r_th_worst` by assuming the starved channel
carries **70%** of mean flow. Solved against the pilot manifold, the flow
network says the starved channel actually carries **65%**.

So the conservative number is not conservative. Not by much here, and the
direction is what matters: `r_th_worst` is presented as the bad case and is in
fact optimistic, so a design sized against it has less margin than it appears
to. The margin is not bounded by anything unless the flow network is solved for
the manifold that will actually be built.

Neither analysis is wrong. Each is honest on its own and neither knows the
other ran. **The finding lives between them**, which is why `atlas.consistency`
now exists and why the chain prints a `between the analyses` section. It
adjusts no number — it says which one to distrust and why.

## Finding 2 — the manifold is turbulent where the plate is laminar

Gallery Reynolds is **7924**. The channels are at 556. The archetype's
applicability condition says laminar, and the plate satisfies it; the manifold
feeding it does not, so its pressure figure comes from a correlation outside
the one the plate was sized on.

This is the kind of thing an applicability condition checked against a
*problem statement* cannot catch, because it is a property of the assembly, not
of the stated problem. Recorded rather than solved.

## Finding 3 — the archetype's own program failed five DFM rules

First run: **16 passed, 5 failed**. The hand-written
`atlas_cad/examples/cold_plate.part.yaml` scores 17 and 0.

Cause: writing the archetype, the channel array was expressed as a `pocket`
followed by a `pocket_pattern` carrying `source: channel`, so the pattern op
could inherit topology roles for `@edge:channels/floor_rim#*`. **Atlas's DFM
rules read width, depth and diameter off the pattern op itself.** Hiding that
geometry behind an indirection broke `dfm.pocket.min_width`,
`dfm.pocket.depth_to_width`, `dfm.pocket.min_wall_between`,
`dfm.drill.min_diameter` and `dfm.drill.depth_to_diameter` — and added three
dark regions on top.

Fixed in the pointer grammar rather than in the archetype: an op whose name
already says what it makes — `pocket_pattern` makes pockets, `hole_pattern`
makes holes — now resolves its roles from that, and needs no `source`. Only the
generic three (`mirror`, `pattern_linear`, `pattern_circular`) must name one.
The archetype went back to the hand-written genome's shape and scores 17 and 0.

**The general lesson:** a convention invented for one consumer broke a second
consumer that was already there. Nothing short of running both would have
shown it.

## Finding 4 — `instantiate` emitted a field the loader rejects

`load_part` rejects unknown top-level fields, and is right to. `instantiate`
was adding `from_archetype`, so **no archetype-generated document could load at
all**. Provenance now travels beside the document; `to_yaml` writes it as a
header comment, which is where the hand-written genomes keep the same
information.

---

## What the run could not check

The certificate names six dark regions, and they are worth reading as the
honest edge of the result:

- `pad` — no rule covers it
- the part envelope — no contract was supplied
- `fillet`, two `hole`s and the `hole_pattern` — outside the v0 geometric
  subset the checker implements

So: 17 rules passed on the channel geometry and the manufacturing pair, and the
holes and fillets that make it a real part were not checked by anything.

And above that, the archetype's declared failure modes, of which the chain only
detected one:

| Mode | Detected here? |
|---|---|
| `flow_maldistribution` | **yes** — 65% worst fraction, with the manifold supplied |
| `degenerate_wall` | covered; wall stayed positive at n=32 |
| `fin_efficiency_collapse` | covered by the thermal model |

Finally, `cold_plate.straight_channel` is `simulated`. **Every number above is
predicted and none of it is measured.** The chain says so as its last line,
because a number that does not say what it left out is the thing this is all
trying not to build.

---

## Reproducing

Needs an Atlas checkout at `JARVIS_ATLAS_ROOT` (default `~/atlas-research`) and
`scipy`. The physics runs out of process via `scripts/atlas_worker.py` — both
projects own a package called `core`, and no import order satisfies both.
