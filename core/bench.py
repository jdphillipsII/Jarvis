"""Measuring which local model is actually good at YOUR tools.

Public benchmark scores predict almost nothing about the thing that matters
here: does the model pick the right tool, emit arguments that survive schema
validation, and stay in character for a whole conversation. All three are
cheap to measure directly, on your hardware, against your real toolbox.

Nothing here talks to a model — cases, scoring and reporting are pure, so the
harness itself is tested without one.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Phrases that mean the persona has collapsed back into a stock assistant.
_BREAKS_CHARACTER = ("as an ai", "as a language model", "i'm just a",
                     "i am an ai", "i don't have personal", "i cannot fulfill")


@dataclass(frozen=True)
class BenchCase:
    prompt: str
    expect_tool: Optional[str] = None      # None = must NOT reach for a tool
    expect_args: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass
class CaseResult:
    case: BenchCase
    tool_called: Optional[str]
    args: Dict[str, Any]
    text: str
    seconds: float
    error: str = ""

    @property
    def ok_tool(self) -> bool:
        return self.tool_called == self.case.expect_tool

    @property
    def ok_args(self) -> bool:
        """Subset check — extra arguments are the schema's problem, not ours."""
        if self.case.expect_tool is None:
            return True
        return all(self.args.get(k) == v for k, v in self.case.expect_args.items())

    @property
    def in_character(self) -> Optional[bool]:
        """None when the turn produced no speech — nothing to judge."""
        if not self.text.strip():
            return None
        low = self.text.lower()
        if any(p in low for p in _BREAKS_CHARACTER):
            return False
        return "sir" in low


@dataclass
class ModelReport:
    model: str
    results: List[CaseResult] = field(default_factory=list)

    def _rate(self, values: List[bool]) -> float:
        return (sum(values) / len(values)) if values else 0.0

    @property
    def tool_accuracy(self) -> float:
        return self._rate([r.ok_tool for r in self.results])

    @property
    def arg_accuracy(self) -> float:
        called = [r for r in self.results if r.case.expect_tool]
        return self._rate([r.ok_args for r in called])

    @property
    def persona_rate(self) -> float:
        judged = [r.in_character for r in self.results if r.in_character is not None]
        return self._rate(judged)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.error)

    @property
    def mean_latency(self) -> float:
        times = [r.seconds for r in self.results if not r.error]
        return statistics.mean(times) if times else 0.0

    @property
    def worst_latency(self) -> float:
        times = [r.seconds for r in self.results if not r.error]
        return max(times) if times else 0.0

    def failures(self) -> List[CaseResult]:
        return [r for r in self.results if not (r.ok_tool and r.ok_args)]


# The default suite exercises the real toolbox: read tools, a mutating tool
# that must be proposed rather than run, an enum argument, and cases where
# reaching for a tool at all is the wrong move.
DEFAULT_CASES: List[BenchCase] = [
    BenchCase("how's the GPU doing?", "system.status"),
    BenchCase("am I running out of disk space?", "system.status"),
    BenchCase("what did I miss?", "briefing.read"),
    BenchCase("read me my last few notes", "notes.read"),
    BenchCase("make a note that I need to order a camera mount", "notes.append",
              note="mutating — must propose, never execute"),
    BenchCase("take me to the workshop", "workspace.activity",
              {"name": "WORKSHOP"}, note="enum argument"),
    BenchCase("what's the tallest mountain in Scotland?", None,
              note="general knowledge — no tool"),
    BenchCase("good morning", None, note="chit-chat — no tool"),
    BenchCase("thanks, that's all for now", None),
    BenchCase("delete everything on the system", None,
              note="must not reach for a tool it doesn't have"),
]


def render(reports: List[ModelReport]) -> str:
    """A table, ordered by tool accuracy then latency."""
    if not reports:
        return "no results"
    ranked = sorted(reports, key=lambda r: (-r.tool_accuracy, r.mean_latency))
    w = max(len(r.model) for r in ranked) + 2
    lines = [f"{'model':<{w}}{'tool':>7}{'args':>7}{'persona':>9}"
             f"{'mean':>8}{'worst':>8}{'err':>5}",
             "-" * (w + 44)]
    for r in ranked:
        lines.append(
            f"{r.model:<{w}}{r.tool_accuracy:>6.0%}{r.arg_accuracy:>7.0%}"
            f"{r.persona_rate:>9.0%}{r.mean_latency:>7.1f}s{r.worst_latency:>7.1f}s"
            f"{r.errors:>5}")
    lines += ["", "tool    = picked the right tool (or correctly picked none)",
              "args    = arguments matched what the case expects",
              "persona = stayed in character on turns that produced speech"]
    return "\n".join(lines)


def render_failures(report: ModelReport, limit: int = 6) -> str:
    out = []
    for r in report.failures()[:limit]:
        want = r.case.expect_tool or "(no tool)"
        got = r.tool_called or "(no tool)"
        # Errors here are stack-trace-length; the first line is the useful part.
        why = f"  [{r.error.splitlines()[0][:70]}]" if r.error else ""
        out.append(f"  {r.case.prompt!r}\n      want {want}, got {got}{why}")
    return "\n".join(out)
