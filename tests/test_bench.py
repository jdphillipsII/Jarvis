import pytest
from core.bench import (BenchCase, CaseResult, ModelReport, DEFAULT_CASES,
                        render, render_failures)


def result(expect=None, called=None, args=None, text="Right, sir.",
           secs=1.0, expect_args=None, error=""):
    return CaseResult(BenchCase("p", expect, expect_args or {}), called,
                      args or {}, text, secs, error)


# ---- tool scoring ----

def test_right_tool_scores():
    assert result("a.b", "a.b").ok_tool


def test_wrong_tool_fails():
    assert not result("a.b", "c.d").ok_tool


def test_correctly_declining_to_use_a_tool_scores():
    """Not reaching for a tool is a right answer, not an absence of one."""
    assert result(None, None).ok_tool


def test_reaching_for_a_tool_when_none_was_needed_fails():
    assert not result(None, "a.b").ok_tool


# ---- argument scoring ----

def test_arguments_are_a_subset_check():
    r = result("w.a", "w.a", {"name": "WORKSHOP", "extra": 1},
               expect_args={"name": "WORKSHOP"})
    assert r.ok_args


def test_wrong_argument_value_fails():
    r = result("w.a", "w.a", {"name": "FORGE"}, expect_args={"name": "WORKSHOP"})
    assert not r.ok_args


def test_no_tool_expected_means_arguments_are_moot():
    assert result(None, None).ok_args


# ---- persona ----

def test_in_character_when_it_says_sir():
    assert result(text="Sixty-one degrees, sir.").in_character


def test_out_of_character_when_it_drops_the_persona():
    assert result(text="Sure! Happy to help, sir.").in_character
    assert result(text="As an AI language model, I cannot.").in_character is False


def test_a_silent_turn_is_not_judged():
    """A pure tool call produces no speech — there is nothing to score."""
    assert result(text="").in_character is None
    assert result(text="   ").in_character is None


def test_persona_rate_ignores_silent_turns():
    rep = ModelReport("m", [result(text=""), result(text="Right, sir.")])
    assert rep.persona_rate == 1.0


# ---- aggregation ----

def test_rates_and_latency():
    rep = ModelReport("m", [
        result("a.b", "a.b", secs=1.0),
        result("a.b", "c.d", secs=3.0),
        result(None, None, secs=2.0)])
    assert rep.tool_accuracy == pytest.approx(2 / 3)
    assert rep.mean_latency == pytest.approx(2.0)
    assert rep.worst_latency == 3.0


def test_errored_cases_do_not_skew_latency():
    rep = ModelReport("m", [result(secs=1.0), result(secs=99.0, error="timeout")])
    assert rep.mean_latency == 1.0
    assert rep.errors == 1


def test_empty_report_does_not_divide_by_zero():
    rep = ModelReport("m", [])
    assert rep.tool_accuracy == 0.0 and rep.mean_latency == 0.0


def test_failures_lists_only_the_bad_ones():
    rep = ModelReport("m", [result("a.b", "a.b"), result("a.b", "c.d")])
    assert len(rep.failures()) == 1


# ---- reporting ----

def test_render_ranks_by_accuracy_then_speed():
    good = ModelReport("good", [result("a.b", "a.b")])
    bad = ModelReport("bad", [result("a.b", "c.d")])
    out = render([bad, good])
    assert out.index("good") < out.index("bad")


def test_render_handles_no_results():
    assert render([]) == "no results"


def test_render_failures_shows_want_and_got():
    rep = ModelReport("m", [result("a.b", "c.d")])
    out = render_failures(rep)
    assert "want a.b" in out and "got c.d" in out


# ---- the shipped suite ----

def test_default_suite_covers_the_important_shapes():
    kinds = {c.expect_tool for c in DEFAULT_CASES}
    assert None in kinds                      # cases where no tool is right
    assert "notes.append" in kinds            # a mutating tool
    assert "workspace.activity" in kinds      # an enum argument
    assert sum(1 for c in DEFAULT_CASES if c.expect_tool is None) >= 3


def test_every_default_case_names_a_real_tool():
    """A typo in the suite would silently score every model as wrong.

    Built with a heavy model so the escalation tool is present — the suite has
    cases for it, and those are skipped at runtime when it is not configured.
    """
    from core.tools import Agency
    from daemon.toolbox.builtin import build
    registry = build(heavy_chat=lambda messages, tools=None: {"content": ""})
    names = {t.name for t in registry.available(Agency.AGENTIC)}
    for c in DEFAULT_CASES:
        assert c.expect_tool is None or c.expect_tool in names, c.expect_tool


# ---- escalation cases ----

def test_heavy_cases_are_skipped_without_a_heavy_model():
    from core.bench import applicable
    assert len(applicable(DEFAULT_CASES, has_heavy=False)) < len(DEFAULT_CASES)
    assert all(not c.requires_heavy
               for c in applicable(DEFAULT_CASES, has_heavy=False))


def test_escalation_is_scored_in_both_directions():
    """Reaching for the slow model matters; so does resisting it."""
    heavy_cases = [c for c in DEFAULT_CASES if c.requires_heavy]
    assert any(c.expect_tool == "reason.deeply" for c in heavy_cases)
    assert any(c.expect_tool is None for c in heavy_cases)
