import json
import pytest
from core.reasoning import clean_reply, extract_tool_calls, strip_reasoning


# ---- stripping deliberation ----

def test_removes_think_block():
    assert strip_reasoning(
        "<think>The user wants the GPU temp. Call system.status.</think>"
        "Sixty-one degrees, sir.") == "Sixty-one degrees, sir."


@pytest.mark.parametrize("tag", ["think", "thinking", "reasoning", "scratchpad"])
def test_handles_every_tag_in_the_wild(tag):
    assert strip_reasoning(f"<{tag}>noise</{tag}>Answer.") == "Answer."


def test_multiple_blocks():
    assert strip_reasoning("<think>a</think>One. <think>b</think>Two.") == "One. Two."


def test_unclosed_block_drops_the_tail():
    """A truncated response must not speak half a monologue."""
    assert strip_reasoning("Right, sir. <think>now let me consider") == "Right, sir."


def test_plain_text_is_untouched():
    assert strip_reasoning("Ben Nevis, sir.") == "Ben Nevis, sir."


def test_pure_reasoning_yields_nothing_to_say():
    assert strip_reasoning("<think>all of it was thinking</think>") == ""


def test_empty_input():
    assert strip_reasoning("") == "" and strip_reasoning(None) == ""


# ---- text-form tool calls ----

def test_extracts_hermes_style_tool_call():
    text = ('<tool_call>\n{"name": "system.status", "arguments": {}}\n</tool_call>')
    calls = extract_tool_calls(text)
    assert calls == [{"function": {"name": "system.status", "arguments": {}}}]


def test_extracts_multiple_and_keeps_arguments():
    text = ('<tool_call>{"name":"a.b","arguments":{"x":1}}</tool_call>'
            '<tool_call>{"name":"c.d","arguments":{"y":2}}</tool_call>')
    calls = extract_tool_calls(text)
    assert [c["function"]["name"] for c in calls] == ["a.b", "c.d"]
    assert calls[0]["function"]["arguments"] == {"x": 1}


def test_string_encoded_arguments_are_parsed():
    text = '<tool_call>{"name":"a.b","arguments":"{\\"x\\":1}"}</tool_call>'
    assert extract_tool_calls(text)[0]["function"]["arguments"] == {"x": 1}


@pytest.mark.parametrize("junk", [
    "<tool_call>not json</tool_call>",
    "<tool_call>[1,2,3]</tool_call>",
    '<tool_call>{"arguments":{}}</tool_call>',      # no name
    "no tags here at all", ""])
def test_malformed_calls_are_dropped_not_guessed(junk):
    assert extract_tool_calls(junk) == []


# ---- the whole message ----

def test_reasoning_and_text_tool_call_together():
    msg = {"role": "assistant", "content":
           '<think>I should check.</think>'
           '<tool_call>{"name":"system.status","arguments":{}}</tool_call>'}
    out = clean_reply(msg)
    assert out["content"] == ""
    assert out["tool_calls"][0]["function"]["name"] == "system.status"


def test_structured_field_wins_over_text():
    """A model that does it properly must not be second-guessed."""
    msg = {"content": '<tool_call>{"name":"wrong.one","arguments":{}}</tool_call>',
           "tool_calls": [{"function": {"name": "right.one", "arguments": {}}}]}
    assert clean_reply(msg)["tool_calls"][0]["function"]["name"] == "right.one"


def test_a_normal_model_passes_through_unchanged():
    msg = {"role": "assistant", "content": "Sixty-one degrees, sir."}
    out = clean_reply(msg)
    assert out["content"] == "Sixty-one degrees, sir."
    assert "tool_calls" not in out


def test_reasoning_is_stripped_even_when_a_real_tool_call_exists():
    msg = {"content": "<think>hmm</think>Checking now.",
           "tool_calls": [{"function": {"name": "a.b", "arguments": {}}}]}
    assert clean_reply(msg)["content"] == "Checking now."
