"""Scoring a model on describing a shape, and on refusing to."""
import json

from core import figure_archetypes as fa
from core.figure_bench import (ABSENT, DEFAULT_CASES, REFUSE, FigureCase, run,
                               render, render_failures)

TRAITS = {
    "bucket.inflow_outflow": ["accumulates", "drains", "has_ceiling"],
    "gate.series_apertures": ["conditions_all_required", "conditions_ordered"],
    "lock.all_pins_match": ["matches_a_key", "conditions_all_required"],
    "vessel.area_is_quantity": ["varies_with_one", "accumulates"],
    "plotter.one_head_many_sites": ["shared_resource", "many_clients"],
    "snap.threshold_and_return": ["threshold", "hysteresis"],
    "balance.two_against_each_other": ["trade_off"],
    "drawers.depth_is_size": ["discrete_set", "differ_in_one_dimension"],
}


class Perfect:
    """Answers every case the way the case expects."""

    def __init__(self, cases, eager=False):
        self.by_subject = {c.subject: c.expect for c in cases}
        self.eager = eager
        self.current = None

    def __call__(self, messages, tools=None, schema=None):
        props = (schema or {}).get("properties", {})
        if "traits" in props:
            subject = messages[-1]["content"].split("\n")[0]
            want = self.by_subject.get(subject, REFUSE)
            if want in (REFUSE, ABSENT):
                # An eager model reaches for a mechanism that is not there.
                traits = ["accumulates", "drains", "has_ceiling"] if self.eager else []
            else:
                traits = TRAITS[want]
            return {"content": json.dumps({"traits": traits})}
        return {"content": json.dumps({
            "figure": "scored", "question": "q", "subject": "s"})}


def library():
    return fa.Library.load()


def test_a_model_that_describes_every_shape_correctly_scores_full_marks():
    cases = DEFAULT_CASES
    report = run(Perfect(cases), library(), cases, model="perfect")
    assert report.shape == 1.0
    assert report.restraint == 1.0


def test_a_model_that_always_finds_a_mechanism_loses_every_restraint_case():
    """Which is the whole reason the refusal cases carry equal weight: an
    eager model produces a confident machine for the causes of a war."""
    cases = DEFAULT_CASES
    report = run(Perfect(cases, eager=True), library(), cases, model="eager")
    assert report.restraint == 0.0
    assert report.shape == 1.0, "it still gets the real mechanisms right"
    assert report.restraint < report.shape


def test_the_bench_has_restraint_cases_at_all():
    refusals = [c for c in DEFAULT_CASES if c.is_refusal]
    assert len(refusals) >= 4
    assert len(refusals) / len(DEFAULT_CASES) > 0.15


def test_the_bench_spans_fields_that_share_nothing():
    bucket = [c for c in DEFAULT_CASES if c.expect == "bucket.inflow_outflow"]
    assert len(bucket) >= 3, "the claim is that shape travels across subjects"
    joined = " ".join(c.subject for c in bucket)
    assert "token" in joined and "reservoir" in joined and "glucose" in joined


def test_binding_is_only_scored_where_a_genome_exists():
    cases = [FigureCase("a reservoir with a spillway", "bucket.inflow_outflow")]
    report = run(Perfect(cases), library(), cases)
    assert report.results[0].bound is None, "nothing to bind without a genome"


def test_binding_is_scored_where_one_does():
    cases = [c for c in DEFAULT_CASES if c.expect == "gate.series_apertures"]
    report = run(Perfect(cases), library(), cases)
    assert all(r.bound for r in report.results)
    assert report.binding == 1.0


def test_a_model_that_never_answered_says_so_instead_of_scoring_zero():
    """`shape 0%` says the model is bad. It is usually Ollama not running."""
    def dead(messages, tools=None, schema=None):
        raise ConnectionError("Connection refused")

    report = run(dead, library(), DEFAULT_CASES, model="qwen2.5:7b")
    assert report.unreachable
    assert "did not answer" in report.line() and "Connection refused" in report.line()


def test_one_bad_turn_among_good_ones_is_not_unreachable():
    cases = DEFAULT_CASES
    report = run(Perfect(cases), library(), cases)
    assert not report.unreachable


def test_a_turn_that_throws_is_a_result_not_a_crash():
    def broken(messages, tools=None, schema=None):
        raise RuntimeError("the card fell over")

    cases = [FigureCase("anything", "gate.series_apertures")]
    report = run(broken, library(), cases)
    assert report.shape == 0.0
    assert "the card fell over" in report.results[0].error


def test_failures_say_what_the_model_said():
    cases = DEFAULT_CASES
    report = run(Perfect(cases, eager=True), library(), cases, model="eager")
    rendered = render_failures(report)
    assert "wanted <no mechanism>" in rendered
    assert "said: accumulates, drains, has_ceiling" in rendered


def test_the_table_reports_restraint_beside_accuracy():
    cases = DEFAULT_CASES
    rendered = render([run(Perfect(cases), library(), cases, model="m")])
    assert "restraint" in rendered and "shape" in rendered
