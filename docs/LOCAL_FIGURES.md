# Teaching figures from a local model

**The goal:** point a model running on the 7900 XTX at a system — a paper, a
protocol, one of our own repos — and get back an interactive figure that
explains it, with true numbers.

**The question is not "can a 24 GB model write this code".** It is "what is the
smallest thing the model has to emit for the rest to be mechanical". Measured
against the eight shipped examples:

| | |
|---|---|
| Build size | 256 – 1,471 lines against a ~100-function API |
| Distinct kit calls per figure | 24 – 76 |
| **Share of all calls that are vector arithmetic** | **~⅓** (`G.add`, `G.mul`, `G.unit`, `G.sub`, `G.cross`, `G.dot` — 400 of 1,212) |
| Top-level named constants | 38 (dial-indicator) → 196 (raptor) — about 15% of lines |
| Acceptance bar | `audit passed` with zero on every line, `line ends: 0`, 4× close-ups of every junction in both themes, read by eye |

Three things follow, and they decide the design.

**1. The arithmetic is the bulk, and it is what the model is worst at.** A third
of every build is working out where a part goes. Asking a local model to do 3D
placement in its head is asking it to fail in the way that is hardest to spot:
a part 2 mm into another part looks fine until the audit ray-casts it.

**2. The skill already says what should replace it.** From `SKILL.md`:

> Each part sits on another part.

That is a *constraint*, not a coordinate. A figure where every part declares
what it sits on is a figure whose placement can be **solved** rather than
written. The model says "the dial sits on the post, centred"; the compiler does
the trigonometry. This is not a new abstraction imposed on the skill — it is the
skill's own description of what correct structure looks like.

**3. The verification bar is deterministic, and we have already run it.**
`lines.mjs` → 0 and `--audit` → passed are programs, not opinions. A loop that
can check itself can iterate without a human in it. The 4× taste pass cannot,
and pretending otherwise is how this fails.

---

## The split

Nothing here asks the local model to write kit code. Ever.

| Stage | Who does it | Why |
|---|---|---|
| 1. Comprehend the system | **local model** | Reading a repo or a paper and extracting a mechanism into a schema is the thing it is genuinely good at. Same shape as the LLM ontology extractor: constrained output, then grounding validation that drops what it cannot find in the source. |
| 2. Choose the object | **retrieve, model selects** | Inventing an apt physical metaphor is the hard creative act. Picking one from a library and adapting it is tractable — and "nothing in the library fits this" is a real answer, as it is for design archetypes. |
| 3. Lay out the parts | **local model emits a genome** | A closed, typed vocabulary, not code. Invalid states made inexpressible by the loader, exactly as `PartGenome` does it. |
| 4. Place the parts | **compiler** | Parts declare `on:` relationships; the compiler solves them into world coordinates and emits kit calls. The third of the work the model is worst at becomes the part no model touches. |
| 5. Supply the numbers | **our generators** | Already built. `figures/<slug>/generate.py` computes in Python, `model.mjs` reads the table, and `figure.check` says when the answer has moved. |
| 6. Verify | **deterministic** | `lines.mjs` → 0, `--audit` → passed. Failures are specific enough to act on: the line check does not say "that looks wrong", it says this tick ends 3.4 px from anything. |
| 7. Taste | **Claude, or a person** | The 4× pass over every junction. This does not go away and should not be claimed to. |

The pattern is the one this repo has arrived at three times now — for borrowed
tools, for part designs, and for topology references. Retrieve rather than
generate; emit a constrained declaration rather than code; make the checker the
strong half; and say plainly what could not be checked.

---

## Make the genome inexpressible when wrong

The lever that matters on local hardware is **constrained decoding**. llama.cpp
and Ollama can hold generation to a JSON Schema or grammar, which means the
model does not *try* to emit a valid genome — it cannot emit an invalid one.
That converts the hardest failure (plausible-looking structural nonsense) into
a class of output the sampler will not produce.

So `core/figure_genome.py` publishes its schema, and the schema is the prompt.

What the loader enforces on top, where a schema cannot reach:

- every part names what it **sits on**, resolving to an earlier part or `ground`
- the support graph is acyclic and fully rooted — nothing floats
- `kind` is in the closed vocabulary; an unknown kind is refused with the list
- every `$param` reference is declared
- exactly one part is the lit subject
- face references use the same `@face:<part>/<role>` grammar as `core/topology.py`,
  so a pointer at a face an op does not make is caught before geometry exists

---

## Model on the card

24 GB, ROCm, and the figure job is a long structured emission rather than a
chat. Two candidates, and the smaller one is likely better:

- `qwen2.5:32b` at Q4 fits (~19 GB) and is already configured as
  `JARVIS_HEAVY_MODEL`. It has the most world knowledge for stage 1.
- A 7–14 B model under a strict grammar often beats a 32 B model generating
  freely, because the grammar supplies the structure the larger model is being
  asked to remember. Worth benchmarking before assuming bigger is better —
  `core/bench.py` already scores models against our real toolbox and can be
  extended to score genome emission.

Stages 1 and 3 are different jobs and need not be the same model. Comprehension
wants knowledge; layout wants obedience.

---

## Our own projects are the first target

"Explain this system" pointed at our own repos needs no physics at all, and the
machinery is already here:

- **the tool gate** — agency, then schema, then consent, in that order. Three
  gates in series is already a physical object: a part that only passes when
  all three line up. The numbers come from `core/toolbox.py`.
- **the ingestion pipeline** or **the intent bus** — a sorting machine with a
  fixed allowlist, fed by several mouths.
- **the CO₂ vessel**, which exists, and whose numbers come from CoolProp with a
  freshness check behind them.

A figure of our own system is also the honest test of stage 1: we can tell
immediately whether the model understood the mechanism or paraphrased the
README.

---

## Build order

1. ~~**The genome schema and loader**~~ — **done.** `core/figure_genome.py`.
2. ~~**The compiler for a narrow vocabulary**~~ — **done.**
   `core/figure_compiler.py`. Ten kinds; `figures/tool-gate/genome.yaml` is a
   hand-written genome of our own tool gate that compiles to a built page with
   **no coordinate typed anywhere** — every position solved from what each
   part sits on. Two properties fell out of the support rule rather than being
   added: declaration order *is* painter's order, and nothing can float.
   What it does not yet do is craft: ticks that land on rules, apertures cut
   rather than drawn, and any motion at all. 48 of 50 line ends float.
3. ~~**The archetype library for figures**~~ — **done.**
   `core/figure_archetypes.py` + nine entries, indexed by the shape of the
   relationship rather than by subject, because not one of anatomy's own
   objects belongs to the subject it explains. The model characterises a
   mechanism in a closed trait vocabulary and the library matches; it never
   invents or picks an object. Three answers: matched, nothing fits, and no
   mechanism. See [FIGURE_ARCHETYPES.md](FIGURE_ARCHETYPES.md).
4. ~~**The local model front end**~~ — **done.** `core/figure_author.py` and
   `core/figure_bench.py`, driven by `jarvis author` and `jarvis figure-bench`.

   The model is trusted with two small jobs and nothing else. It **describes**
   a mechanism in the trait vocabulary — never what object to draw. Then, when
   an archetype's genome already exists, it **binds**: the question, the
   subject line, a few parameter values, a label per part. Not the layout. The
   binding grammar is generated from that one genome, so its parameter names
   are that genome's parameters and its labelled parts are that genome's parts.
   A model cannot name one that is not there.

   The bench scores three things, and **restraint carries the same weight as
   accuracy**: four of its seventeen cases have no mechanism at all. A model
   that always finds one is worse than a model that sometimes does, and a
   bench without refusal cases rewards exactly the wrong instinct.
5. **The loop** ← next. Emit, compile, `lines.mjs`, `--audit`, feed failures
   back. Deterministic failures mean the model gets told exactly what to fix,
   and `kit/audit.mjs` already exports every check individually
   (see the density-probe finding).
