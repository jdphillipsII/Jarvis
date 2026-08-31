# CO₂ pseudocritical point — audit of the cooling-loop figures

**Date:** 2026-08-27
**Method:** CoolProp 8.0.0 (Span–Wagner reference EOS for CO₂), driven through
`core/fluids.py`. Reproduction script at the end.
**Scope:** the Tpc and specific-heat figures in `atlas-docs/state/atlas_cooling.md`,
`plan-2H-adaptive-nitinol-sprint.md` and `crusoe-outreach-package.md`.

---

## Summary

| # | Finding | Severity |
|---|---|---|
| 1 | Two internal docs disagree on Tpc at 80 bar; one is wrong by ~2.7 K | **medium** — it is the doc that sets the NiTi Af target |
| 2 | The stated "Tpc window ~32–45 °C at 75–80 bar" does not correspond to any computed quantity | **medium** — appears to conflate Tpc with the DLC supply temperature |
| 3 | Peak cp is not a usable design number, and the outreach material quotes it | **high** — the number a licensee's thermal engineer will check first |

Finding 3 is the substantive one. Findings 1 and 2 are bookkeeping.

---

## Finding 1 — Tpc at 80 bar is 34.7 °C

| Source | Claim |
|---|---|
| `plan-2H-adaptive-nitinol-sprint.md` | "sCO2 at 80 bar has a pseudo-critical point near **32 °C**" |
| `crusoe-outreach-package.md` | "Cp peak at **~35 °C** at 80 bar" |
| **Computed** | **34.7 °C** |

The outreach figure is correct. Plan 2H is low by 2.7 K.

This matters because plan 2H is the document that specifies *"Af tuned to Tpc
neighborhood"* against a stated tolerance of ±5 °C. An insert designed to a
32 °C target sits 2.7 K low before any manufacturing variation is counted —
over half the budget spent on a bookkeeping error.

**Full pseudocritical line:**

| P (bar) | Tpc (°C) | peak cp (kJ/kg·K) |
|---|---|---|
| 74 | 31.1 | 1,463.7 |
| 75 | 31.7 | 228.2 |
| 76 | 32.3 | 115.0 |
| 78 | 33.5 | 54.7 |
| 80 | 34.7 | 35.3 |
| 85 | 37.4 | 18.7 |
| 90 | 40.0 | 12.8 |
| 100 | 45.0 | 8.1 |
| 110 | 49.7 | 6.1 |
| 120 | 54.0 | 5.0 |

---

## Finding 2 — the "32–45 °C window" is not a real quantity

`state/atlas_cooling.md` states: *"near-critical CO2 throughout the loop
(~75–80 bar, Tpc window ~32–45 °C)"*.

At 75–80 bar the pseudocritical temperature is **31.7–34.7 °C**. Reaching
45 °C requires roughly **100 bar**.

The alternative reading — that "window" meant the *width* of the elevated-cp
band at a single pressure rather than the locus of peaks across pressures —
was tested and does not fit either:

- half-peak width at 80 bar: **33.7 to 35.7 °C** (about ±1 K)
- region where cp > 2 kJ/kg·K at 80 bar: **−25.5 to 58.3 °C**

Neither is 32–45.

**Probable origin:** 32 is plan 2H's Tpc figure; 45 is the DLC coolant supply
temperature stated three paragraphs later in the same file ("direct-to-chip
liquid at 45 °C, Rubin-compatible"). Two different quantities appear to have
been merged into one range.

---

## Finding 3 — peak cp is not what a cold plate experiences

Two properties of the cp peak make it unusable as a design figure.

**It is violently pressure-sensitive.** Peak cp falls from 1,464 kJ/kg·K at
74 bar to 35 at 80 bar to 8 at 100 bar — two orders of magnitude across 26 bar.
Any figure quoted without its pressure is meaningless.

**It is about 1 K wide.** A plate with a real temperature rise never sits at
the peak; it integrates across a band. The number that governs heat capture is
Δh/ΔT across that band, not cp at a point.

**Effective cp = Δh/ΔT, centred on Tpc** (kJ/kg·K, and as a multiple of water):

| | ΔT = 2 K | ΔT = 5 K | ΔT = 10 K | ΔT = 20 K |
|---|---|---|---|---|
| **75 bar** | 39.6 (9.5x) | 21.3 (5.1x) | 13.4 (3.2x) | 8.6 (2.0x) |
| **80 bar** | 26.4 (6.3x) | 17.4 (4.2x) | 11.9 (2.8x) | 8.0 (1.9x) |
| **90 bar** | 12.5 (3.0x) | 11.2 (2.7x) | 9.2 (2.2x) | 6.9 (1.6x) |

### Against this, the two internal figures

**The outreach claim is optimistic.** `crusoe-outreach-package.md` states
*"40–60 kJ/kg·K, ~10× water"* at 80 bar. That combination occurs only at
75 bar with ΔT ≈ 2 K. At 80 bar across a realistic 5–10 K rise the effective
value is **12–17 kJ/kg·K, or 3–4× water**. Still a real advantage over water —
but not ten times, and the gap is a factor of about five.

**The simulator figure is sound.** Plan 2H notes its constant-property
simulator assumed `Cp = 8895 J/kg·K`. That corresponds to roughly ΔT = 15–20 K
at 75–80 bar — a defensible, conservative effective value.

So the engineering is honest and the marketing is not. That asymmetry is worth
correcting before the Chart follow-up, because it is exactly the calculation a
licensee's thermal engineer runs first, and finding it themselves costs more
credibility than correcting it voluntarily.

---

## What this supports

The steepness that makes peak cp a bad *quoted* number is a strong argument
**for** the bellows-first architecture. Between 74 and 80 bar the peak drops
roughly fortyfold; the entire value proposition depends on holding the fluid
near its operating point, and passive geometric compliance exists precisely to
do that without sensors.

That rationale is currently implicit. Stating it explicitly — *"the cp
advantage is pressure-sensitive by design, and the regulation network is what
makes it dependable"* — turns an apparent fragility into the reason the
architecture is shaped the way it is.

---

## Recommended edits

1. `plan-2H`: change "pseudo-critical point near 32 °C" to **34.7 °C at 80 bar**,
   and re-check the NiTi Af target against it.
2. `state/atlas_cooling.md`: replace "Tpc window ~32–45 °C" with
   **"Tpc 31.7–34.7 °C at 75–80 bar"**, and state the 45 °C DLC supply
   temperature separately so the two are not read as one range.
3. `crusoe-outreach-package.md` and any derived material: quote **effective**
   cp with its pressure and ΔT, not peak cp. Suggested form:
   *"12–17 kJ/kg·K across a 5–10 K rise at 80 bar — three to four times
   water's."*
4. Add the pressure-sensitivity argument to the regulation rationale.
5. Consider carrying Tpc(P) as a computed value rather than a literal, so it
   cannot drift between documents again.

---

## Reproduction

```python
import CoolProp.CoolProp as CP

def tpc(p_bar):                      # cp maximum along an isobar
    p = p_bar * 1e5
    best_t, best = 0, -1
    for i in range(4000):
        t = 299.0 + i * 0.02
        c = CP.PropsSI('C', 'P', p, 'T', t, 'CO2')
        if c > best:
            best_t, best = t, c
    return best_t - 273.15, best

def effective_cp(p_bar, dT):         # what a plate with a real rise sees
    p, t = p_bar * 1e5, tpc(p_bar)[0] + 273.15
    hi = CP.PropsSI('H', 'P', p, 'T', t + dT / 2, 'CO2')
    lo = CP.PropsSI('H', 'P', p, 'T', t - dT / 2, 'CO2')
    return (hi - lo) / dT

print(tpc(80))                       # (34.67, 35293.)
print(effective_cp(80, 5))           # 17420.
```

Or through the assistant's own tooling:

```bash
./cli.py chat
> what is the pseudocritical temperature of CO2 at 80 bar?
> density and cp of CO2 at 80 bar and 35 degC?
```

## Caveats

- CoolProp uses Span–Wagner for CO₂, the reference equation of state. The
  property values are not in question.
- The ΔT bands above are illustrative. **The actual plate ΔT decides which row
  applies**, and that number should come from the design, not from this note.
- Effective cp is computed at constant pressure. A real loop has pressure drop
  along the channel, which shifts Tpc downstream — a second-order effect here,
  but not zero, and worth checking once the plate ΔP is fixed.
