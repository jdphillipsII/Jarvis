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
