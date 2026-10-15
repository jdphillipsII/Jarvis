# Three ways to get a taste proxy wrong in half an hour

**Date:** 2026-10-15
**Question:** anatomy's acceptance bar is deterministic twice over and a
judgement once. Can the judgement be measured, so a model driving the pipeline
can close its own loop?

> **audit passed** — ray-cast geometry, zero on every line
> **line ends: 0** — every tick lands on a stroke
> *"At 4× every region still has something true to find; a bare face or an
> empty corner is unfinished work, not calm."* ← this one

**Answer: not this way.** The attempt took about half an hour and was wrong
three times, each time in a way that would have shipped looking reasonable.
That is the finding, and it is worth more than the probe.

---

## The idea

"Is this region empty" is a question about ink, and ink is countable. Grid a
rendered page, count marked pixels per cell, report cells that lie inside the
drawing and carry almost nothing.

## Wrong #1 — proximity is not enclosure

First version called a cell "inside the figure" if two of its neighbours had
ink. Measured that way, **every reference figure scored the same as ours**:

| figure | bare / inside |
|---|---|
| dial-indicator | 6 / 37 |
| desk-computer | 6 / 38 |
| co2-widom (ours) | 6 / 38 |

A measure that cannot separate a reference figure from a first draft is not
measuring the thing. The dark card around a machine is adjacent to it on two
sides, so "near the ink" selects the quiet space the drawing is supposed to
have. **Caught by calibrating against figures known to meet the bar** — never
by reading the code.

## Wrong #2 — the inversion

Replaced proximity with a flood fill: whatever the fill cannot reach from
outside is enclosed. At a 24×24 grid that gave a clean-looking result —
and **arcade-cabinet, their densest and most finished figure at about 240
solids, scored worst** while ours scored zero.

Marking the flagged cells on the render showed every one of them on the
cabinet's **interior wall and side panel**: correctly drawn flat faces that are
*supposed* to be empty, because they are the backdrop the mechanism stands
against. The measure was detecting flat faces, not unfinished ones. A model
pushed to minimise it would add clutter to a correct panel — the "too flat and
bland" failure inverted into a noise failure rather than fixed.

## Wrong #3 — the fill was leaking

The downsample before the flood fill used striding, `marked[::4, ::4]`, which
**drops a one-pixel outline unless it lands on a multiple of four**. In a
drawing made almost entirely of hairlines, the fill leaked out through the
gaps, and the "enclosed" regions of wrong #2 were an artefact of which strokes
happened to survive the stride. Caught by a synthetic test, not by the real
images — on a real render there is enough ink that the result looked plausible.

Fixed by max-pooling the downsample. Which produced the third wrong answer:
with hairlines preserved, the **card's own frame seals the fill**, so
"enclosed by the drawing" now means "inside the card", and the measure reduces
to *what share of the frame is empty*:

| figure | empty / cells (16×16) |
|---|---|
| arcade-cabinet | 85 / 256 |
| ripple-tank | 100 / 256 |
| desk-computer | 122 / 256 |
| co2-widom (ours) | 130 / 256 |
| dial-indicator | 136 / 256 |

That ordering is at least sensible — the dense figures leave less of the card
empty. It is also no longer a measure of anything anyone asked about.

---

## What survives

- **`core/figure_density.py`**, as a descriptive statistic with a warning on
  it, not a gate. Share-of-card-filled is a real property of a drawing.
- **The habit that caught all three**: run a new measure on work already known
  to meet the bar, and distrust it when it cannot tell that work apart from a
  draft. Wrong #1 and #2 were both found that way.
- The 4× read remains a human step.

## What it says about the harness question

The temptation, when a loop needs to judge its own output, is to build a proxy
for taste. This is what that costs. Each wrong version looked principled, each
produced numbers of exactly the right shape for a gate, and two of the three
were caught only by calibration against known-good work.

The checks that work measure facts about geometry rather than impressions of
it — and the ones we want **already exist and are not plugged in**.
`kit/audit.mjs` exports every one of its checks individually:

    overlapsOf  clearances  solidClearances  terminals  looseEnds  grounded
    supports    folds       selfOverlaps     crowding   coverage   wobble
    seats       depthOrder  boundsOf         footprintOf

They are used only as a pass/fail at the end, through `auditOrExit`. Exposing
them as a query surface a build loop can call *while* it works is wiring rather
than invention, and every answer is ground truth about the geometry.

So: a model does not need to understand 3D. It needs to never be in a position
where understanding 3D is required — that is the genome and the compiler — and
to be told precisely what is wrong when its declaration is. The second half
already exists.
