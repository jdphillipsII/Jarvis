# What is in the library

The goal is a local model that can explain almost anything visually. The
objection is obvious: a library of objects cannot cover an unbounded set of
subjects. The resolution is in anatomy's own concept-to-object table, where
**not one object belongs to the subject it explains**:

| Concept | Object |
|---|---|
| a cache key that skips work when nothing changed | a pin-tumbler lock |
| seven render targets, different bytes per texel | a chest of drawers |
| one GPU context serving many canvases | a gantry plotter |
| a height profile | a contour gauge |

The lock does not know what a cache is. It is there because the relationship —
*several things must all match before one thing happens* — has that shape. The
same lock explains an enzyme needing its cofactors, multi-factor login, and a
combination safe.

**So the library is indexed by the shape of the relationship, not by subject.**
There are not many shapes. There is no end of subjects.

---

## The nine

| id | the relationship | the object |
|---|---|---|
| `vessel.area_is_quantity` | a quantity varying with one variable, accumulating | a graduated vessel whose width is the quantity |
| `bucket.inflow_outflow` | fills at one rate, empties at another, has a ceiling | a bucket under a tap, with a spigot and an overflow lip |
| `gate.series_apertures` | conditions that must all pass, in order, stopping at the first refusal | three apertures in series on one rail |
| `lock.all_pins_match` | passing depends on a pattern matching exactly, all at once | a pin-tumbler lock with its face cut away |
| `drawers.depth_is_size` | a fixed set differing chiefly in one measurable dimension | a chest of drawers, each as deep as its measure |
| `plotter.one_head_many_sites` | one resource serving many, so waiting is it being elsewhere | a gantry plotter over a tray of wells |
| `gauge.profile_along_path` | a quantity sampled along a path, where the shape is the point | a contour gauge pressed against an edge |
| `balance.two_against_each_other` | two good things in opposition | an equal-arm balance with a sliding poise |
| `snap.threshold_and_return` | nothing, then everything at once — and back is not where out was | an over-centre toggle on a cam |

Four come from anatomy's own validated table. Two we have built. Three fill
shapes that kept coming up.

### What that already covers

```
a token-bucket rate limiter       -> bucket.inflow_outflow
a capacitor smoothing a supply    -> bucket.inflow_outflow
a reservoir with a spillway       -> bucket.inflow_outflow
blood glucose after a meal        -> bucket.inflow_outflow
TLS, then authz, then quota       -> gate.series_apertures
an enzyme needing its cofactors   -> lock.all_pins_match
CO2 specific heat vs temperature  -> vessel.area_is_quantity
a progressive tax schedule        -> vessel.area_is_quantity
one event loop, many sockets      -> plotter.one_head_many_sites
a thermostat's differential       -> snap.threshold_and_return
precision against recall          -> balance.two_against_each_other
```

Electronics, physiology, security, thermodynamics, tax law, networking. Nine
entries.

---

## The model describes; it does not choose

The model never invents an object and never picks one. It characterises the
mechanism in a **closed vocabulary of traits** — does it accumulate, does it
drain, is there a ceiling, must conditions pass in order — and the library
matches. Characterising is a far smaller job than inventing, and under a
grammar a 7B model can do it. There is no field in the schema where a model
names an archetype.

An entry declares `needs` (traits that must all be present) and `rules_out`
(traits whose presence make it wrong). `conditions_all_required` plus
`conditions_ordered` is a gate; the same conditions with `matches_a_key` and
no ordering is a lock. That is the whole classifier.

---

## Three answers, and the third is what makes the rest honest

**matched** — the shape is in the library.

**nothing fits** — the shape is real and the library lacks it. Names the near
misses and what each would still need:

```
no archetype in the library has this shape.
closest, and what each would still need:
  snap.threshold_and_return: needs threshold
building a new one by hand is the honest next step; it then joins the library
and is never hand-built again.
```

**no mechanism** — what you described does not work by parts moving:

> this does not work by parts moving, so there is no figure to build. Forcing
> a machine onto it would be decoration, and decoration dressed as explanation
> is worse than prose.

The causes of the Thirty Years War, why a sonnet's volta works, whether a
policy is just. These are not failures of the library. A figure of them would
be a diagram with arrows, which is the first of the two failures anatomy names
("too abstract — stacked plates, floating slabs or labelled boxes don't read as
anything").

---

## How it reaches "practically any subject"

Not by someone guessing the right nine. **By ratchet.**

When nothing fits, a figure is built by hand — by Claude, or by you — and that
figure becomes an entry. Every shape built once is available forever after, to
every subject that shares it. The local model's reach is exactly the
accumulated library, and it grows by use rather than by foresight.

That is why `status` distinguishes `proposed` from `built`: an entry is `built`
only when a genome exists that compiles. Today exactly one does
(`gate.series_apertures` → `figures/tool-gate/genome.yaml`). The rest are
described and waiting for their first figure. A test asserts that every entry
names at least one subject it has actually explained, so nothing accumulates
on speculation.

Each entry also names **what it cannot show**, and that field is mandatory at
load. An archetype that claims no limit will be reached for when it does not
fit — the same discipline as a design archetype's failure modes and a
certificate's dark regions.

---

## The part nobody should skip: where the numbers come from

A figure from a model that searched the web is only as true as what it found.
The machinery already exists — `figures/<slug>/generate.py` computes, the
result is stamped with its source, and `figure.check` re-runs it and says when
the answer has moved. A web-sourced figure needs the same: which page, fetched
when, and a re-check that can fail.

Without that, "explain anything from the web" means confident figures of wrong
numbers, drawn beautifully, audited for geometry, and incorrect. That is the
one failure this whole stack is built to refuse.
