"""Borrowed tools, and the gate they have to come through."""
import pytest

from core.bridges import (BridgeSpec, ManifestError, MountReport, ToolPolicy,
                          load_manifest, mount, mount_all)
from core.mcp_client import McpClient, McpError
from core.proposals import Proposal
from core.toolbox import Toolbox
from core.tools import Agency, ToolRegistry

from tests.test_mcp_client import FakeServer


def spec(**kw):
    tools = kw.pop("tools", {"measure": ToolPolicy("measure", Agency.ADVISORY)})
    return BridgeSpec(name=kw.pop("name", "cad"), transport="http",
                      url="http://x/mcp", tools=tools, **kw)


def client(tools=None, **kw):
    return McpClient(FakeServer(tools=tools, **kw), name="cad")


def offered(name, **extra):
    return {"name": name, "description": f"{name} something",
            "inputSchema": {"type": "object", "properties": {}}, **extra}


# ---- fail closed: no manifest entry, no tool ----

def test_a_tool_the_manifest_does_not_name_is_not_mounted():
    """The upstream project ships a new version with a new tool. It stays
    invisible until a human has said what it may do."""
    reg = ToolRegistry()
    report = mount(reg, spec(), client([offered("measure"), offered("delete_everything")]))
    assert report.mounted == ["measure"]
    assert report.unclassified == ["delete_everything"]
    assert "cad.delete_everything" not in reg
    assert len(reg) == 1


def test_a_manifest_entry_the_server_does_not_offer_is_reported_absent():
    reg = ToolRegistry()
    policies = {"measure": ToolPolicy("measure", Agency.ADVISORY),
                "solidwords_typo": ToolPolicy("solidwords_typo", Agency.ADVISORY)}
    report = mount(reg, spec(tools=policies), client([offered("measure")]))
    assert report.absent == ["solidwords_typo"]


def test_a_tool_the_server_says_writes_is_refused_when_we_classified_it_as_a_reader():
    """We are wrong in the direction that matters, and which side is stale is
    not a question to answer at boot."""
    reg = ToolRegistry()
    report = mount(reg, spec(), client([offered("measure", annotations={"readOnlyHint": False})]))
    assert report.disputed == ["measure"]
    assert report.mounted == []
    assert len(reg) == 0


def test_we_may_be_stricter_than_the_server_claims():
    reg = ToolRegistry()
    policies = {"measure": ToolPolicy("measure", Agency.ACTUATOR, mutates=True)}
    report = mount(reg, spec(tools=policies),
                   client([offered("measure", annotations={"readOnlyHint": True})]))
    assert report.mounted == ["measure"]


# ---- the policy, not the server, decides ----

def test_the_mounted_tool_carries_our_agency_and_our_consent_requirement():
    reg = ToolRegistry()
    policies = {"save": ToolPolicy("save", Agency.ACTUATOR, mutates=True,
                                   confirm_label="Save", risk="overwrites")}
    mount(reg, spec(tools=policies), client([offered("save")]))
    tool = reg.get("cad.save")
    assert tool.min_agency is Agency.ACTUATOR and tool.mutates
    assert tool.confirm_label == "Save" and tool.risk == "overwrites"


def test_a_bridged_mutating_tool_returns_a_proposal_not_a_result():
    """The whole reason for the bridge: every CAD MCP server surveyed executes
    on call. Through here, it proposes."""
    reg = ToolRegistry()
    policies = {"save": ToolPolicy("save", Agency.ACTUATOR, mutates=True)}
    fake = FakeServer(tools=[offered("save")])
    mount(reg, spec(tools=policies), McpClient(fake, name="cad"))
    box = Toolbox(registry=reg, agency=Agency.ACTUATOR)

    outcome = box.invoke("cad.save", {})
    assert isinstance(outcome, Proposal)
    assert not [c for c in fake.calls if c["method"] == "tools/call"]

    box.confirm(outcome.id)
    assert [c["params"]["name"] for c in fake.calls if c["method"] == "tools/call"] == ["save"]


def test_a_bridged_tool_above_agency_is_invisible():
    reg = ToolRegistry()
    policies = {"execute": ToolPolicy("execute", Agency.AGENTIC, mutates=True)}
    mount(reg, spec(tools=policies), client([offered("execute")]))
    box = Toolbox(registry=reg, agency=Agency.ACTUATOR)
    assert box.schemas() == []
    assert not box.invoke("cad.execute", {}).ok


def test_the_bridge_name_prefixes_the_tool_so_two_servers_cannot_collide():
    reg = ToolRegistry()
    mount(reg, spec(name="sw"), client([offered("measure")]))
    mount(reg, spec(name="b123"), client([offered("measure")]))
    assert sorted(t.name for t in reg.available(Agency.AGENTIC)) == \
        ["b123.measure", "sw.measure"]


# ---- dimensional checking on a borrowed tool ----

def test_a_quantity_override_gives_a_borrowed_tool_our_dimension_check():
    reg = ToolRegistry()
    policies = {"mate": ToolPolicy("mate", Agency.ACTUATOR, mutates=True,
                                   quantities={"distance": "length"})}
    tools = [{"name": "mate", "description": "distance mate",
              "inputSchema": {"type": "object",
                              "properties": {"distance": {"type": "number"}},
                              "required": ["distance"]}}]
    mount(reg, spec(tools=policies), client(tools))
    box = Toolbox(registry=reg, agency=Agency.ACTUATOR)

    assert not box.invoke("cad.mate", {"distance": 12}).ok      # bare number
    assert isinstance(box.invoke("cad.mate", {"distance": "12 mm"}), Proposal)
    bad = box.invoke("cad.mate", {"distance": "12 kg"})
    assert not bad.ok and "length" in bad.error


# ---- failures are reports, not exceptions ----

def test_an_unreachable_bridge_is_a_warning_not_a_crash():
    """JARVIS has to boot with the workshop cold — SolidWorks lives on the
    other half of a dual boot and is absent more often than present."""
    reg = ToolRegistry()

    def refuse(_spec):
        raise McpError("connection refused")

    reports = mount_all(reg, {"sw": spec(name="sw", enabled=True)}, connect=refuse)
    assert len(reg) == 0
    assert "connection refused" in reports[0].error
    assert "unavailable" in reports[0].summary()


def test_a_server_that_cannot_list_its_tools_mounts_nothing():
    reg = ToolRegistry()
    broken = McpClient(FakeServer(error={"code": -1, "message": "boom"}), name="cad")
    assert mount(reg, spec(), broken).error.endswith("boom")
    assert len(reg) == 0


def test_a_disabled_bridge_is_not_connected_at_all():
    reg = ToolRegistry()
    calls = []
    mount_all(reg, {"sw": spec(name="sw", enabled=False)},
              connect=lambda s: calls.append(s) or client())
    assert calls == []


# ---- the manifest is our own config, so its errors are loud ----

def test_a_mutating_tool_cannot_be_advisory():
    with pytest.raises(ManifestError, match="no side effects"):
        load_manifest_from({"cad": {"transport": "http", "url": "http://x",
                                    "tools": {"save": {"agency": "advisory",
                                                       "mutates": True}}}})


def test_an_unknown_agency_is_an_error_not_a_silent_downgrade():
    with pytest.raises(ManifestError, match="agency must be"):
        load_manifest_from({"cad": {"transport": "http", "url": "http://x",
                                    "tools": {"save": {"agency": "actuater"}}}})


def test_a_transport_without_its_address_is_an_error():
    with pytest.raises(ManifestError, match="needs a command"):
        load_manifest_from({"cad": {"transport": "stdio", "tools": {}}})
    with pytest.raises(ManifestError, match="needs a url"):
        load_manifest_from({"cad": {"transport": "http", "tools": {}}})
    with pytest.raises(ManifestError, match="stdio"):
        load_manifest_from({"cad": {"transport": "carrier-pigeon", "tools": {}}})


def load_manifest_from(raw, tmp=None):
    import tempfile, os, yaml
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as fh:
        yaml.safe_dump(raw, fh)
    try:
        return load_manifest(path)
    finally:
        os.unlink(path)


# ---- the shipped manifest ----

def test_the_shipped_manifest_loads():
    manifest = load_manifest()
    assert {"solidworks", "build123d", "dxf"} <= set(manifest)


def test_nothing_ships_enabled():
    """Enabling a bridge is a deliberate act, like raising agency."""
    assert [n for n, s in load_manifest().items() if s.enabled] == []


def test_arbitrary_execution_is_never_quietly_an_actuator():
    """build123d's `execute` runs Python; autocad's run_command runs shell.
    One is classified agentic, the other is not classified at all."""
    manifest = load_manifest()
    assert manifest["build123d"].tools["execute"].agency is Agency.AGENTIC
    assert "system_run_command" not in manifest["dxf"].tools
    assert "system_run_lisp" not in manifest["dxf"].tools


def test_every_mutating_entry_confirms_with_a_verb():
    for bridge in load_manifest().values():
        for policy in bridge.tools.values():
            if policy.mutates:
                assert policy.confirm_label != "Confirm", \
                    f"{bridge.name}.{policy.name} should name what it is about to do"
