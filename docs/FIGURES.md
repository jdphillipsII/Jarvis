# Figures

    jarvis figures              what exists, and whether its numbers still hold
    jarvis figures co2-widom    one in full

A figure explains an idea by building it as a real, working object. The drawing
is done by [`anatomy`](https://github.com/wheresryan22/anatomy) (MIT), which
also ray-casts its own geometry to prove no part passes through another — see
[PRIOR_ART.md](PRIOR_ART.md).

**JARVIS does not author figures.** That needs an agent with a code-writing
loop and the patience to read its own renders. What JARVIS owns is the half
anatomy cannot have.

---

## The idea: a figure is a cached view of a computation

It shows numbers that something else worked out, at some moment, under some
inputs. The failure that follows is neither subtle nor rare: a beautiful,
audited, demonstrably self-consistent figure quietly showing last spring's
answer. **Nothing in the drawing can detect that**, because the drawing is
still perfectly correct about data that is no longer true.

So every figure declares the generator that produced its numbers, and
`figure.check` re-runs it and compares:

| | |
|---|---|
| `fresh` | regenerated and matched |
| `stale` | regenerated and **moved** — with the field and the size of the move |
| `missing` | never generated |
| `uncheckable` | the generator will not run, so the figure is not verifiable |

`uncheckable` is deliberately not a kind of fresh. A figure whose provenance
cannot be re-executed is a picture, and it is better to say so. The same
distinction as an `unproven` archetype and a certificate's dark regions.

Reading is advisory. `figure.show` is an actuator that reports freshness as it
opens — because an out-of-date figure does not look out of date.

---

## Laying one out

```
figures/<slug>/
  figure.yaml     slug, title, question, generator, source, findings
  generate.py     table() -> a JSON-able dict. The numbers, from the real model.
  data.json       what table() returned, stamped with when and from what
  model.mjs       pure JS: reads the table, exposes what the drawing asks it
  build.mjs       the anatomy build
  <slug>.html     the built standalone page, both themes
```

**The join to our physics is a generated table, not a second implementation.**
Our numbers are Python — CoolProp, `atlas_cad`. Anatomy's models are JS.
Reimplementing an equation of state in JavaScript would create exactly the
divergent second source of truth every other rule in this repo exists to
prevent. `generate.py` computes; `model.mjs` reads and interpolates; the card
cites the version that produced the table.

One implementation detail worth keeping: `generate` **reads and compiles the
generator source on every call** rather than importing it. Python's import
machinery reuses a cached `.pyc` when a file's size and mtime both look
unchanged, and an edit that keeps the byte count inside the same second does
look unchanged — so a tool whose entire job is noticing that the numbers moved
would quietly run the old code. Found by a test that swapped one constant for
another of the same length.

---

## What is in it

### `co2-widom` — CO₂ at 80 bar

A graduated vessel on a bench whose **cross-sectional area at height T is the
specific heat of CO₂**. That is an identity, not a decorative mapping:

- height is temperature
- area at a height is cp
- **the volume up to a level is the enthalpy**

So pouring energy in is literally adding volume, and the level rises by
dT = dQ/cp(T). The geometry is therefore checkable against physics rather than
taste: integrate the profile the vessel is cut from and it must reproduce
CoolProp's enthalpy. It does, to **8.1 × 10⁻⁵** — asserted in the tests.

It illustrates finding 3 of
[the Tpc audit](findings/2026-08-27-co2-pseudocritical-audit.md) — that peak cp
is not a usable design number — and makes it sharper than the audit could:

- Tpc at 80 bar is **34.65 °C**, where cp peaks at **35,237 J/kg·K**, 41.7× the
  ideal-gas value. The peak itself is resolution-dependent, which is the
  strongest possible form of the audit's claim.
- Pour in **half** the window's total energy and the level sits at 34.68 °C —
  almost exactly on the peak.
- **Crossing the four degrees from 32.65 to 36.65 °C costs 41% of all the
  energy in a 30 K window. The four degrees below 50 °C cost 5.8%.** A ratio
  of 7.1.
- Across any realistic operating span you get a fraction of the peak: ±2 K
  gives 55%, ±5 K gives 34%, ±10 K gives 23%.

The last point is the lesson the object teaches by being operated: the bulge is
not somewhere you can sit, because absorbing heat is the thing that carries you
out of it.

**Where it stands against anatomy's bar:** it builds in both themes, the
console is clean, and the model round-trips. It is **not** finished to their
standard — `scripts/lines.mjs` reports 64 of 252 line ends floating against a
bar of 0, there is no `--audit` hook (no recorder, no pipes), and at 4× there
are bare faces. It is a working first pass that proves the pipeline, not a
reference figure.
