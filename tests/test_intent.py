import json
import pytest
from core.intent import Intent, InvalidIntent


def test_roundtrip_through_wire_format():
    i = Intent("workspace.next", source="gesture", confidence=0.9, args={"n": 1})
    assert Intent.from_line(i.to_line()) == i


def test_namespacing_is_required():
    with pytest.raises(InvalidIntent):
        Intent("next")            # no group


@pytest.mark.parametrize("conf", [-0.1, 1.5])
def test_confidence_must_be_a_probability(conf):
    with pytest.raises(InvalidIntent):
        Intent("workspace.next", confidence=conf)


def test_unknown_source_rejected():
    with pytest.raises(InvalidIntent):
        Intent("workspace.next", source="telepathy")


def test_garbage_on_the_wire_is_rejected():
    for bad in ["not json", "[1,2,3]", json.dumps({"intent": "a.b", "evil": True})]:
        with pytest.raises(InvalidIntent):
            Intent.from_line(bad)


def test_intents_are_immutable():
    i = Intent("mic.mute")
    with pytest.raises(Exception):
        i.intent = "workspace.next"      # frozen dataclass
