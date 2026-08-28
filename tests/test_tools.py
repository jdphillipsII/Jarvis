import pytest
from core.tools import Agency, Tool, ToolRegistry, ToolResult


def tool(**kw):
    base = dict(name="t.thing", description="do a thing", handler=lambda: "done")
    base.update(kw)
    return Tool(**base)


# ---- agency ----

def test_agency_is_ordered():
    assert Agency.ADVISORY < Agency.ACTUATOR < Agency.AGENTIC


@pytest.mark.parametrize("text,expected", [
    ("actuator", Agency.ACTUATOR), ("AGENTIC", Agency.AGENTIC),
    ("  advisory ", Agency.ADVISORY)])
def test_agency_parses_from_config(text, expected):
    assert Agency.parse(text) is expected


def test_unknown_agency_fails_closed():
    """A typo in jarvis.env must not silently grant shell access."""
    assert Agency.parse("supervisor") is Agency.ADVISORY
    assert Agency.parse("") is Agency.ADVISORY


def test_registry_only_exposes_permitted_tools():
    r = ToolRegistry()
    r.add(tool(name="read.a", min_agency=Agency.ADVISORY))
    r.add(tool(name="act.b", min_agency=Agency.ACTUATOR))
    r.add(tool(name="shell.c", min_agency=Agency.AGENTIC))
    assert [t.name for t in r.available(Agency.ADVISORY)] == ["read.a"]
    assert len(r.available(Agency.ACTUATOR)) == 2
    assert len(r.available(Agency.AGENTIC)) == 3


# ---- schema ----

def test_missing_required_argument_is_caught():
    t = tool(parameters={"name": {"type": "string"}}, required=("name",))
    assert "missing required" in t.validate({})


def test_unknown_argument_is_rejected():
    t = tool(parameters={"name": {"type": "string"}})
    assert "unknown argument" in t.validate({"name": "x", "sudo": True})


def test_wrong_type_is_rejected():
    t = tool(parameters={"n": {"type": "integer"}})
    assert "must be integer" in t.validate({"n": "twelve"})
    assert t.validate({"n": 12}) is None


def test_enum_is_enforced():
    t = tool(parameters={"which": {"type": "string", "enum": ["a", "b"]}})
    assert "one of" in t.validate({"which": "c"})
    assert t.validate({"which": "a"}) is None


def test_schema_render_is_openai_shaped():
    s = tool(parameters={"x": {"type": "string"}}, required=("x",)).schema()
    assert s["type"] == "function"
    assert s["function"]["name"] == "t.thing"
    assert s["function"]["parameters"]["required"] == ["x"]


def test_tool_result_truthiness():
    assert ToolResult(True, 1)
    assert not ToolResult(False, error="nope")


def test_registry_membership():
    r = ToolRegistry()
    r.add(tool(name="a.b"))
    assert "a.b" in r and "nope" not in r
