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


# ---- quantity arguments ----

def qtool(dimension=None):
    spec = {"type": "quantity"}
    if dimension:
        spec["dimension"] = dimension
    return tool(parameters={"p": spec}, required=("p",))


def test_quantity_argument_accepts_a_unit_string():
    assert qtool("pressure").validate({"p": "80 bar"}) is None


def test_wrong_dimension_is_refused():
    problem = qtool("pressure").validate({"p": "20 degC"})
    assert "must be a pressure" in problem


def test_a_bare_number_is_not_a_pressure():
    """The whole point: 80 with no unit must not silently become 80 Pa."""
    assert "must be a pressure" in qtool("pressure").validate({"p": 80})


def test_unknown_unit_is_named():
    assert "flurbles" in qtool("pressure").validate({"p": "80 flurbles"})


def test_dimension_free_quantity_accepts_anything_parseable():
    t = qtool()
    assert t.validate({"p": "3 mm"}) is None and t.validate({"p": "80 bar"}) is None
    assert t.validate({"p": "3 flurbles"}) is not None


def test_unknown_dimension_in_the_schema_is_caught():
    assert "unknown dimension" in qtool("spookiness").validate({"p": "1 m"})


def test_quantity_is_presented_to_the_model_as_a_string():
    """Models emit "80 bar" far more reliably than a typed object."""
    prop = qtool("pressure").schema()["function"]["parameters"]["properties"]["p"]
    assert prop["type"] == "string"
    assert "pressure" in prop["description"]
