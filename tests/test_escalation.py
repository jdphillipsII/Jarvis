import pytest
from core.agent import Agent
from core.escalation import deep_thought_tool
from core.toolbox import Toolbox
from core.tools import Agency, ToolRegistry
from daemon.toolbox.builtin import build
from tests.test_agent import FakeModel, says, calls


def heavy(text="Because the pressure drop scales with the fourth power, sir."):
    """Stands in for the big model."""
    seen = []
    def chat(messages, tools=None):
        seen.append((messages, tools))
        return {"role": "assistant", "content": text}
    chat.seen = seen
    return chat


# ---- the tool itself ----

def test_returns_the_heavy_models_answer():
    t = deep_thought_tool(heavy())
    assert "fourth power" in t.handler(question="why?")


def test_the_heavy_model_gets_no_tools():
    """It thinks; it does not act. Side effects stay behind the consent gate."""
    h = heavy()
    deep_thought_tool(h).handler(question="why?")
    _, tools = h.seen[0]
    assert tools is None


def test_reasoning_traces_are_stripped_from_the_answer():
    t = deep_thought_tool(heavy("<think>long deliberation</think>Ben Nevis, sir."))
    assert t.handler(question="q") == "Ben Nevis, sir."


def test_an_empty_answer_still_says_something():
    """Silence would be spoken as nothing at all."""
    assert deep_thought_tool(heavy("")).handler(question="q") == "No answer, sir."


def test_it_is_advisory_and_non_mutating():
    """Escalation must never need confirmation — it has no side effects."""
    t = deep_thought_tool(heavy())
    assert t.min_agency is Agency.ADVISORY and t.mutates is False


def test_the_description_warns_against_overuse():
    d = deep_thought_tool(heavy()).description.lower()
    assert "do not use it for" in d and "slower" in d


# ---- registration ----

def test_absent_unless_a_heavy_model_is_configured(tmp_path):
    notes = str(tmp_path / "n.md")
    assert "reason.deeply" not in build(notes_path=notes)
    assert "reason.deeply" in build(notes_path=notes, heavy_chat=heavy())


# ---- end to end through the agent ----

def test_the_fast_model_can_escalate(tmp_path):
    h = heavy("Copper, sir — roughly twice the conductivity.")
    box = Toolbox(registry=build(notes_path=str(tmp_path / "n.md"), heavy_chat=h),
                  agency=Agency.ACTUATOR)
    model = FakeModel(calls("reason.deeply", question="copper or aluminium?"),
                      says("Copper, sir — roughly twice the conductivity."))
    turn = Agent(toolbox=box, chat=model).say("copper or aluminium for the plate?")
    assert turn.tools_used == ["reason.deeply"]
    assert "Copper" in turn.text
    assert h.seen, "the heavy model was never actually called"


def test_escalation_needs_no_confirmation(tmp_path):
    box = Toolbox(registry=build(notes_path=str(tmp_path / "n.md"), heavy_chat=heavy()),
                  agency=Agency.ACTUATOR)
    model = FakeModel(calls("reason.deeply", question="q"), says("Answer, sir."))
    turn = Agent(toolbox=box, chat=model).say("hard question")
    assert not turn.awaiting_confirmation


def test_a_broken_heavy_model_does_not_break_the_turn(tmp_path):
    def dead(messages, tools=None):
        raise ConnectionError("heavy model not loaded")
    box = Toolbox(registry=build(notes_path=str(tmp_path / "n.md"), heavy_chat=dead),
                  agency=Agency.ACTUATOR)
    model = FakeModel(calls("reason.deeply", question="q"),
                      says("I couldn't work that out, sir."))
    turn = Agent(toolbox=box, chat=model).say("hard question")
    assert turn.text == "I couldn't work that out, sir."     # recovered
