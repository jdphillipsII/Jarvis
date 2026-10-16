"""Scoring a local model on the only two jobs it has.

`core/bench.py` scores models on tool choice against the real toolbox. This is
the same idea for figures, and it measures the two things that can actually go
wrong before any geometry exists:

**Shape.** Given a subject, does the model describe a mechanism that lands on
the right archetype? This is a classification over a closed vocabulary, which
is why a small model under a grammar can do it at all.

**Restraint.** Does it refuse when it should? Cases where the right answer is
"this does not work by parts moving" are weighted equally, because **a model
that always finds a mechanism is worse than one that sometimes does.** An
eager model produces a confident machine for the causes of a war, and that is
the failure this stack is built to refuse. A bench without refusal cases
rewards exactly the wrong instinct.

**Binding.** When a genome exists, does what the model says about the subject
survive loading and placing? A binding is a few dozen tokens against a grammar
cut to one genome, so this should be near-perfect — and if it is not, the
schema is too loose rather than the model too small.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import figure_archetypes as fa
from .figure_author import Draft, author

REFUSE = "<no mechanism>"
ABSENT = "<nothing fits>"


@dataclass(frozen=True)
class FigureCase:
    subject: str
    expect: str                    # an archetype id, REFUSE, or ABSENT
    note: str = ""

    @property
    def is_refusal(self) -> bool:
        return self.expect in (REFUSE, ABSENT)


# Deliberately drawn from fields that share nothing, because the claim being
# tested is that shape travels and subject does not.
DEFAULT_CASES: Sequence[FigureCase] = (
    FigureCase("a token bucket rate limiter holding 20 tokens, refilling 5 a "
               "second, rejecting when empty", "bucket.inflow_outflow"),
    FigureCase("a reservoir fed by a river, drawn on by a town, with a "
               "spillway at the top", "bucket.inflow_outflow",
               "same machine, no computing in it"),
    FigureCase("blood glucose rising after a meal and being cleared by insulin",
               "bucket.inflow_outflow"),
    FigureCase("a request passing authentication, then authorisation, then a "
               "quota check, stopping at the first failure",
               "gate.series_apertures"),
    FigureCase("JARVIS checking agency, then schema, then consent before a "
               "tool runs", "gate.series_apertures", "our own system"),
    FigureCase("a cache key: the work is skipped only when every field of the "
               "key matches", "lock.all_pins_match"),
    FigureCase("an enzyme that only catalyses when all of its cofactors are "
               "bound", "lock.all_pins_match"),
    FigureCase("the specific heat of CO2 against temperature at 80 bar, and "
               "the energy it takes to cross the peak", "vessel.area_is_quantity"),
    FigureCase("a progressive income tax schedule and the tax actually paid",
               "vessel.area_is_quantity"),
    FigureCase("one single-threaded event loop serving two hundred sockets",
               "plotter.one_head_many_sites"),
    FigureCase("a thermostat that switches on at 18 and off at 21",
               "snap.threshold_and_return"),
    FigureCase("precision against recall in a classifier",
               "balance.two_against_each_other"),
    FigureCase("the bytes per texel of seven different render targets",
               "drawers.depth_is_size"),
    # Restraint. Each of these has a tempting mechanical reading and no
    # mechanism, and a model that reaches for one has failed the case.
    FigureCase("the causes of the Thirty Years War", REFUSE,
               "a chain of events is not a machine"),
    FigureCase("why the volta in a sonnet changes how the poem reads", REFUSE),
    FigureCase("whether a sentencing guideline is just", REFUSE),
    FigureCase("the list of noble gases and when each was discovered", REFUSE,
               "a table is not a mechanism"),
)


@dataclass
class CaseResult:
    case: FigureCase
    draft: Optional[Draft] = None
    chose: str = ""
    seconds: float = 0.0
    error: str = ""

    @property
    def right_shape(self) -> bool:
        return self.chose == self.case.expect

    @property
    def bound(self) -> Optional[bool]:
        """None when there was nothing to bind."""
        if self.draft is None or self.case.is_refusal:
            return None
        if self.draft.archetype is None or not self.draft.archetype.built:
            return None
        return self.draft.ok


@dataclass
class Report:
    model: str
    results: List[CaseResult] = field(default_factory=list)

    @property
    def shape(self) -> float:
        rows = [r for r in self.results if not r.case.is_refusal]
        return sum(r.right_shape for r in rows) / len(rows) if rows else 0.0

    @property
    def restraint(self) -> float:
        rows = [r for r in self.results if r.case.is_refusal]
        return sum(r.right_shape for r in rows) / len(rows) if rows else 0.0

    @property
    def binding(self) -> float:
        rows = [r for r in self.results if r.bound is not None]
        return sum(1 for r in rows if r.bound) / len(rows) if rows else 0.0

    @property
    def unreachable(self) -> bool:
        """Every case failed to run at all.

        Without this the table reads `shape 0%`, which says the model is bad
        when what happened is that nothing answered.
        """
        return bool(self.results) and all(r.error for r in self.results)

    @property
    def mean_seconds(self) -> float:
        return (sum(r.seconds for r in self.results) / len(self.results)
                if self.results else 0.0)

    def failures(self) -> List[CaseResult]:
        return [r for r in self.results if not r.right_shape or r.bound is False]

    def line(self) -> str:
        if self.unreachable:
            reason = self.results[0].error
            return f"{self.model:<22} did not answer — {reason}"
        return (f"{self.model:<22} shape {self.shape:>5.0%}   "
                f"restraint {self.restraint:>5.0%}   "
                f"binding {self.binding:>5.0%}   "
                f"{self.mean_seconds:>5.2f}s")


def run(chat: Callable[..., Dict[str, Any]], library: fa.Library,
        cases: Sequence[FigureCase] = DEFAULT_CASES,
        model: str = "model",
        clock: Callable[[], float] = time.perf_counter) -> Report:
    report = Report(model=model)
    for case in cases:
        started = clock()
        result = CaseResult(case=case)
        try:
            draft = author(case.subject, library, chat)
        except Exception as exc:                      # a bad turn is a result
            result.error = f"{type(exc).__name__}: {exc}"
            result.chose = "<error>"
        else:
            result.draft = draft
            result.chose = _chose(draft)
        result.seconds = clock() - started
        report.results.append(result)
    return report


def _chose(draft: Draft) -> str:
    if draft.archetype is not None:
        return draft.archetype.id
    if not draft.traits:
        return REFUSE
    return ABSENT


def render(reports: Sequence[Report]) -> str:
    head = (f"{'model':<22} {'shape':>11} {'restraint':>15} "
            f"{'binding':>13} {'speed':>8}")
    return "\n".join([head, "-" * len(head)] + [r.line() for r in reports])


def render_failures(report: Report, limit: int = 8) -> str:
    out = []
    for result in report.failures()[:limit]:
        want = result.case.expect
        out.append(f"  {result.case.subject[:62]}")
        out.append(f"    wanted {want}, chose {result.chose}"
                   + (f" — {result.error}" if result.error else ""))
        if result.draft is not None and result.draft.traits:
            out.append(f"    said: {', '.join(result.draft.traits)}")
    return "\n".join(out)
