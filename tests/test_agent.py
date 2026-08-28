"""The conversation engine, driven by a scripted model. No Ollama required."""
import json
import pytest

from core.agent import Agent
from core.proposals import ProposalStatus
from core.toolbox import Toolbox
from core.tools import Agency, Tool, ToolRegistry


class FakeModel:
    """Replays a script of assistant messages and records what it was shown."""
    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen_tools = []
        self.seen_messages = []

    def __call__(self, messages, tools):
        self.seen_messages.append(list(messages))
        self.seen_tools.append([t["function"]["name"] for t in tools])
        return self.replies.pop(0) if self.replies else {"content": "(silence)"}


def says(text):
    return {"role": "assistant", "content": text}


def calls(name, **args):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": args}}]}


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.add(Tool("system.status", "report status", lambda: {"gpu_temp_c": 61}))
    r.add(Tool("notes.append", "append a note", lambda text: f"noted: {text}",
               parameters={"text": {"type": "string"}}, required=("text",),
               min_agency=Agency.ACTUATOR, mutates=True))
    return r


def agent(registry, model, agency=Agency.ACTUATOR):
    return Agent(toolbox=Toolbox(registry=registry, agency=agency), chat=model)


# ---- plain conversation ----

def test_a_question_with_no_tool_just_answers(registry):
    a = agent(registry, FakeModel(says("Ben Nevis, sir.")))
    turn = a.say("tallest mountain in Scotland?")
    assert turn.text == "Ben Nevis, sir." and turn.tools_used == []


def test_empty_input_is_ignored(registry):
    assert agent(registry, FakeModel()).say("   ").text == ""


# ---- read tools ----

def test_a_read_tool_runs_and_its_result_reaches_the_model(registry):
    model = FakeModel(calls("system.status"), says("Sixty-one degrees, sir."))
    turn = agent(registry, model).say("how's the GPU?")
    assert turn.tools_used == ["system.status"]
    assert turn.text == "Sixty-one degrees, sir."
    tool_msg = [m for m in model.seen_messages[-1] if m.get("role") == "tool"]
    assert "61" in tool_msg[0]["content"]


def test_the_model_only_sees_permitted_tools(registry):
    model = FakeModel(says("ok"))
    agent(registry, model, Agency.ADVISORY).say("hello")
    assert model.seen_tools[0] == ["system.status"]      # notes.append hidden


# ---- consent ----

def test_a_mutating_tool_asks_first_and_does_not_run(registry):
    model = FakeModel(calls("notes.append", text="order the mount"))
    a = agent(registry, model)
    turn = a.say("note that I should order the mount")
    assert turn.awaiting_confirmation
    assert "Shall I, sir?" in turn.text
    assert a.pending.status is ProposalStatus.PROPOSED


def test_yes_executes_it(registry):
    a = agent(registry, FakeModel(calls("notes.append", text="buy a mount")))
    a.say("note that")
    turn = a.say("yes")
    assert "noted: buy a mount" in turn.text
    assert a.pending is None


def test_no_declines_it(registry):
    ran = []
    registry.add(Tool("t.act", "act", lambda: ran.append(1),
                      min_agency=Agency.ACTUATOR, mutates=True))
    a = agent(registry, FakeModel(calls("t.act")))
    a.say("do the thing")
    assert a.say("no").text == "As you wish, sir."
    assert ran == []


def test_a_qualified_yes_is_not_consent(registry):
    """'yes but change the name' must not fire the pending action."""
    ran = []
    registry.add(Tool("t.act", "act", lambda: ran.append(1),
                      min_agency=Agency.ACTUATOR, mutates=True))
    a = agent(registry, FakeModel(calls("t.act"), says("Right, sir.")))
    a.say("do the thing")
    turn = a.say("yes but call it something else")
    assert ran == []
    assert turn.text == "Right, sir."          # treated as a fresh request


def test_moving_on_cancels_the_pending_offer(registry):
    """A stale proposal must not be fired by a later, unrelated 'yes'."""
    ran = []
    registry.add(Tool("t.act", "act", lambda: ran.append(1),
                      min_agency=Agency.ACTUATOR, mutates=True))
    a = agent(registry, FakeModel(calls("t.act"), says("Ben Nevis, sir."),
                                  says("Nothing pending, sir.")))
    a.say("do the thing")
    a.say("what's the tallest mountain in Scotland")
    assert a.pending is None
    a.say("yes")
    assert ran == []


def test_an_expired_offer_is_reported_not_crashed(registry):
    from core.proposals import ProposalStore
    t = [0.0]
    box = Toolbox(registry=registry, agency=Agency.ACTUATOR,
                  proposals=ProposalStore(ttl_s=60, clock=lambda: t[0]))
    a = Agent(toolbox=box, chat=FakeModel(calls("notes.append", text="x")))
    a.say("note it")
    t[0] = 61.0
    assert "expired" in a.say("yes").text


# ---- error recovery ----

def test_a_bad_argument_goes_back_to_the_model_to_fix(registry):
    """The model gets the error and corrects itself; the user sees the answer."""
    model = FakeModel(
        calls("notes.append", wrong="x"),        # invalid
        calls("system.status"),                  # recovers
        says("All nominal, sir."))
    turn = agent(registry, model).say("check on things")
    assert turn.text == "All nominal, sir."
    errors = [m for m in model.seen_messages[-1]
              if m.get("role") == "tool" and "ERROR" in m["content"]]
    # Validation reports missing-required before unknown-argument, so the
    # model is told what it left out rather than what it made up.
    assert errors and "missing required" in errors[0]["content"]


def test_hallucinated_tools_are_refused_not_executed(registry):
    model = FakeModel(calls("rm.everything", path="/"), says("Can't do that, sir."))
    turn = agent(registry, model).say("delete everything")
    assert turn.text == "Can't do that, sir."


def test_a_tool_loop_is_capped(registry):
    model = FakeModel(*[calls("system.status") for _ in range(20)])
    turn = agent(registry, model).say("go")
    assert "stuck" in turn.text
    assert len(turn.tools_used) <= 4


def test_string_encoded_arguments_are_parsed(registry):
    """Some Ollama builds return arguments as a JSON string."""
    model = FakeModel({"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "notes.append",
                      "arguments": json.dumps({"text": "hello"})}}]})
    a = agent(registry, model)
    turn = a.say("note hello")
    assert turn.awaiting_confirmation and a.pending.args == {"text": "hello"}


# ---- history ----

def test_history_is_trimmed(registry):
    a = agent(registry, FakeModel(*[says(f"{i}") for i in range(30)]))
    a.max_history = 6
    for i in range(20):
        a.say(f"question {i}")
    assert len(a.history) <= 6


# ---- reasoning models (Hermes 4, Qwen 3.x) ----

def test_reasoning_is_never_spoken(registry):
    """The whole point: JARVIS must not read its own deliberation aloud."""
    model = FakeModel({"role": "assistant", "content":
                       "<think>The user asked about a mountain. Ben Nevis.</think>"
                       "Ben Nevis, sir."})
    turn = agent(registry, model).say("tallest in Scotland?")
    assert turn.text == "Ben Nevis, sir."
    assert "think" not in turn.text


def test_a_text_form_tool_call_still_executes(registry):
    """Hermes emits <tool_call> as text; it must reach the toolbox anyway."""
    model = FakeModel(
        {"role": "assistant", "content":
         '<think>check the gpu</think>'
         '<tool_call>{"name":"system.status","arguments":{}}</tool_call>'},
        says("Sixty-one degrees, sir."))
    turn = agent(registry, model).say("how's the GPU?")
    assert turn.tools_used == ["system.status"]
    assert turn.text == "Sixty-one degrees, sir."


def test_text_form_mutating_call_still_asks_permission(registry):
    """Consent must not be bypassed by the call arriving as text."""
    model = FakeModel({"role": "assistant", "content":
                       '<tool_call>{"name":"notes.append",'
                       '"arguments":{"text":"buy a mount"}}</tool_call>'})
    a = agent(registry, model)
    turn = a.say("note that")
    assert turn.awaiting_confirmation
    assert a.pending.args == {"text": "buy a mount"}


# ---- persona ----

def test_persona_and_tool_catalogue_both_reach_the_model(registry):
    model = FakeModel(says("Right, sir."))
    agent(registry, model).say("hello")
    system = model.seen_messages[0][0]
    assert system["role"] == "system"
    assert "sir" in system["content"]
    assert "system.status" in system["content"]      # the catalogue


def test_persona_states_the_rule_and_shows_it(registry):
    """Adjectives don't move a 7B; worked examples do. Keep both."""
    from core.agent import PERSONA
    assert "sir" in PERSONA.lower()
    assert PERSONA.count('"') >= 8                   # example dialogue present
    assert "As an AI" in PERSONA                     # the negative example


def test_persona_is_overridable(registry):
    from core.agent import Agent
    from core.toolbox import Toolbox
    a = Agent(toolbox=Toolbox(registry=registry, agency=Agency.ACTUATOR),
              chat=(m := FakeModel(says("ok"))), persona="You are a pirate.")
    a.say("hi")
    assert "pirate" in m.seen_messages[0][0]["content"]
