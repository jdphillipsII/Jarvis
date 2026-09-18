# The archetype library

**Why it exists:** every spec→CAD project in [PRIOR_ART.md](PRIOR_ART.md)
generates geometry from the problem statement each time, and every one of them
is unreliable in the same way. That is not a model-capability problem. A spec
does not contain a design. *"450 W off a 40 mm die into water at 2 L/min"* does
not say straight channels, and no amount of reasoning derives them, because the
answer is a shape somebody already found and then adapted.

The Atlas north-star doc asks for exactly this and calls it the component
library: *"proven mechanism/component archetypes … admission only through a
max-fidelity adversarial gate."* This is that, at the part level.

    jarvis archetypes                              what is in the library
    jarvis archetypes cold_plate.straight_channel  one in full

---

## The two rules that carry the weight

### Nothing applies is an answer

A library that always returns its nearest entry is **worse than no library**,
because the nearest entry arrives with all the authority of a proven design and
none of the fit. So:

- an archetype with one failed condition is **excluded**, never ranked low —
  conditions are not a score, and a design that is wrong in the one way that
  matters is not a 4-out-of-5 design
- when nothing applies, `select` says so, names what came closest, says why
  each was thrown out, and states that designing from scratch is the next step

```
$ design.select {"coolant_phase": "two_phase", "flow_regime": "turbulent"}
no archetype in the library covers this problem.
closest, and why each was excluded:
  cold_plate.straight_channel: excluded — coolant_phase is two_phase, not one
    of single_phase_liquid; flow_regime is turbulent, not one of laminar
designing from scratch is the honest next step, not adapting one of the above.
```

This is the same refusal as `resolve()` raising on an ambiguous face pointer,
and as the LLM extractor dropping an ungrounded entity. One house style: the
system would rather return nothing than return something plausible.

### What could not be checked is reported

A problem statement that says nothing about the coolant leaves every coolant
condition **unchecked**, and the assessment says so — in the same voice
`verify_part`'s certificate names its dark regions. An unchecked condition is
not a passed one.

That produces a third verdict alongside applies and excluded: **unproven** —
nothing contradicts this archetype, but nothing has tested it either. A cooling
problem must not surface a bracket merely because nothing in it rules one out,
so an archetype needs at least one *passed* condition before it is offered.

---

## What an archetype carries

| Field | Why it is mandatory |
|---|---|
| `parameters` | named, dimensioned, bounded, each with a **default** — an archetype is a working design, not a form to fill in |
| `program` | PartGenome ops with `$refs` and topology pointers; checked by `core/topology.py` at load |
| `applicability` | machine-checkable conditions, each with a **`why`** — a bound with no reason cannot be argued with, and a library is a thing you argue with |
| `failure_modes` | how it is known to break, what detects each, and **which archetype fixes it** |
| `provenance` | where the shape came from |
| `status` + `evidence` | how far up the ladder, and what backs the claim |

### The evidence ladder

    proposed  →  simulated  →  built  →  measured

Promotion needs evidence, not assertion: any status above `proposed` must cite
it, and **`measured` must cite a predicted-vs-measured comparison**. That is
the arrow [ENGINEERING_SUITE.md](ENGINEERING_SUITE.md) lists as having no home,
wired into the promotion rule rather than left as an aspiration. Nothing in the
library is `measured` yet, and that is the honest state of things — when the
rig closes the loop, `test_nothing_in_the_library_claims_to_be_measured_yet` is
the test that should change.

---

## What is in it

### `cold_plate.straight_channel` — *simulated*

The archetype that was already here implicitly. `atlas_cad.thermal`'s
`evaluate_cold_plate` requires exactly `plate_width, base_thickness,
channel_width, channel_depth, n_channels` — which means the shape was decided
long before anyone wrote it down.

Every applicability clause is a line the **evaluator itself** draws, not
engineering taste: single-phase because the lumped model has no latent term,
laminar because Nu = 3.66 and f = 64/Re are the laminar correlations, the five
material families because those are the keys in `_K_SOLID`.

Its programme also demonstrates what the topology work bought. The original
genome said `edges: internal_channel_edges` — a name with no definition
anywhere in the repo. The archetype says `@edge:channels/floor_rim#*`.

### `cold_plate.serpentine_channel` — *proposed*

**This archetype exists because of the other one's failure mode**, and that is
the whole argument for a library rather than a generator: the second design is
not a better guess at the same problem, it is the answer to a constraint the
first design taught us about. One continuous path means no parallel branches,
so there is nothing for a manifold to distribute unevenly.

Its `analyses` list is deliberately **empty**. `atlas_cad.thermal` assumes n
parallel channels sharing the flow; pointed at this shape it would compute a
confident wrong answer rather than refuse, because n = 1 is inside its
parameter domain and outside its physical one. An archetype with no evaluator
is worth recording. It is not worth pretending about.

The pair is also the clearest demonstration of selection. State
`flow_distribution: parallel` and you get the straight-channel plate. State
`single_path` and the straight-channel plate is *excluded* and the serpentine
one is offered — not because it scored higher, but because the constraint that
motivated it was finally stated.

### `bracket.l_cantilever` — *simulated*

Here to prove the schema is not cold-plate-shaped, which is the same thing
`bracket.part.yaml` proved about the Atlas spine. Its most valuable field is a
failure mode that **nothing detects**: σ is computed from bending alone, the
mounting holes sit at the root where stress is highest, and their K_t is not in
the model. `structural.py` names this as a stated gap. Writing it here means it
is read every time the archetype is proposed, rather than rediscovered.

---

## Adding one

Drop a YAML file in `archetypes/`. It is data, not code, so a new archetype is
a config change — and the loader is strict on purpose:

- a parameter default outside its own bounds is refused
- a `$ref` to an undeclared parameter is refused
- a broken topology pointer is refused *at load*, long before instantiation
- a condition with no `why`, or one that bounds nothing, is refused
- a failure mode pointing at an archetype that is not in the library is refused
- a status above `proposed` with no `evidence` is refused

The tests enforce two house rules over the whole library: every archetype names
at least one way it fails, and every archetype says where it came from.

---

## Where it goes next

The library is the retrieval half. The adaptation half — `instantiate` — hands
back a PartGenome document ready for the checker battery, which means the
natural next step is to run one end to end: select, adapt, verify, and evaluate
through `atlas_cad.thermal`, so the numbers come back into the same
conversation that chose the shape.

The rung above that is the rig, and the rung above *that* is the first
archetype promoted to `measured`.
