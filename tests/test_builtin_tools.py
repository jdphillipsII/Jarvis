import os
import pytest
from core.bus import Bus
from core.intent import Intent
from core.registry import Registry
from core.toolbox import Toolbox
from core.tools import Agency
from daemon.proactive import Briefing
from daemon.toolbox.builtin import build


@pytest.fixture
def notes(tmp_path):
    return str(tmp_path / "notes.md")


def box(notes, agency=Agency.ACTUATOR, bus=None, briefing=None):
    return Toolbox(registry=build(bus=bus, briefing=briefing, notes_path=notes),
                   agency=agency)


def test_shell_is_hidden_at_the_default_agency(notes):
    assert "shell.run" not in box(notes).catalogue()
    assert "shell.run" in box(notes, Agency.AGENTIC).catalogue()


def test_system_status_reads_without_confirmation(notes):
    r = box(notes).invoke("system.status")
    assert r.ok and "disk_free_gb" in r.value


def test_notes_require_confirmation_then_write(notes):
    b = box(notes)
    p = b.invoke("notes.append", {"text": "order the camera mount"})
    assert not os.path.exists(notes)              # nothing yet
    b.confirm(p.id)
    assert "camera mount" in open(notes).read()


def test_notes_read_back(notes):
    b = box(notes)
    for line in ("first", "second"):
        b.confirm(b.invoke("notes.append", {"text": line}).id)
    assert box(notes).invoke("notes.read", {"count": 1}).value == ["second"]


def test_activity_switch_publishes_an_intent_after_confirmation(notes):
    bus = Bus(registry=Registry.load())
    seen = []
    bus.subscribe("workspace.activity", lambda i: seen.append(i.args["name"]))
    b = box(notes, bus=bus)
    p = b.invoke("workspace.activity", {"name": "WORKSHOP"})
    assert seen == []
    b.confirm(p.id)
    assert seen == ["WORKSHOP"]


def test_unknown_activity_is_refused_by_the_enum(notes):
    r = box(notes, bus=Bus(registry=Registry.load())).invoke(
        "workspace.activity", {"name": "BATCAVE"})
    assert not r.ok and "one of" in r.error


def test_briefing_tool_reads_the_queue(notes):
    from core.observation import Observation
    from core.policy import Urgency
    br = Briefing()
    br.add(Observation("the build passed", Urgency.INFO, "ci", "1"))
    assert "build passed" in box(notes, briefing=br).invoke("briefing.read").value


def test_units_convert_tool(notes):
    b = box(notes)
    assert b.invoke("units.convert", {"value": "80 bar", "to": "Pa"}).value == "8e+06 Pa"
    assert b.invoke("units.convert", {"value": "20 degC", "to": "K"}).value == "293.15 K"


def test_units_convert_refuses_incompatible(notes):
    r = box(notes).invoke("units.convert", {"value": "5 kg", "to": "m"})
    assert not r.ok and "cannot convert" in r.error


def test_units_convert_is_advisory(notes):
    """Reading a conversion has no side effects — never ask permission."""
    from core.tools import Agency
    assert box(notes, Agency.ADVISORY).invoke(
        "units.convert", {"value": "1 inch", "to": "mm"}).ok


# ---- the archetype library, through the toolbox ----

class TestDesignTools:
    def box(self):
        from core.toolbox import Toolbox
        from core.tools import Agency
        from daemon.toolbox.builtin import build
        return Toolbox(registry=build(bridges=False), agency=Agency.ACTUATOR)

    def test_the_library_is_readable_at_advisory(self):
        from core.tools import Agency
        from core.toolbox import Toolbox
        from daemon.toolbox.builtin import build
        box = Toolbox(registry=build(bridges=False), agency=Agency.ADVISORY)
        result = box.invoke("design.archetypes")
        assert result.ok
        assert "cold_plate.straight_channel" in [a["id"] for a in result.value]

    def test_selecting_reports_rather_than_guesses(self):
        result = self.box().invoke("design.select", {"problem": {
            "coolant_phase": "two_phase", "flow_regime": "turbulent",
            "source_geometry": "flat"}})
        assert result.ok
        assert result.value["nothing_applies"]
        assert result.value["applies"] == []
        assert "honest next step" in result.value["report"]

    def test_selecting_a_covered_problem_returns_the_archetype(self):
        result = self.box().invoke("design.select", {"problem": {
            "coolant_phase": "single_phase_liquid", "flow_regime": "laminar",
            "source_geometry": "flat", "material_family": "copper",
            "footprint": "90 mm", "flow_distribution": "parallel"}})
        assert result.value["applies"] == ["cold_plate.straight_channel"]

    def test_describing_an_archetype_includes_how_it_fails(self):
        result = self.box().invoke(
            "design.archetype", {"archetype_id": "cold_plate.straight_channel"})
        names = [m["name"] for m in result.value["failure_modes"]]
        assert "flow_maldistribution" in names

    def test_instantiating_adapts_and_keeps_the_rest(self):
        result = self.box().invoke("design.instantiate", {
            "archetype_id": "cold_plate.straight_channel",
            "values": {"n_channels": 32}, "name": "dlc_plate"})
        assert result.ok
        values = {p["name"]: p["value"] for p in result.value["parameters"]}
        assert values["n_channels"] == 32 and values["plate_width"] == 100.0
        assert result.value["part"] == "dlc_plate"

    def test_an_out_of_range_adaptation_comes_back_as_a_tool_error(self):
        result = self.box().invoke("design.instantiate", {
            "archetype_id": "cold_plate.straight_channel",
            "values": {"n_channels": 500}})
        assert not result.ok and "outside the archetype's range" in result.error

    def test_the_design_tools_are_all_advisory(self):
        """Proposing a design changes nothing in the world. Reading the
        library should not cost a confirmation."""
        from core.tools import Agency
        from daemon.toolbox.builtin import build
        for tool in build(bridges=False).available(Agency.ADVISORY):
            if tool.name.startswith("design."):
                assert not tool.mutates
