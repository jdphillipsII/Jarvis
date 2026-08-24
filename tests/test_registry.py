import pytest
from core.intent import Intent
from core.registry import Registry


@pytest.fixture(scope="module")
def reg():
    return Registry.load()


def test_loads_the_real_registry(reg):
    assert len(reg) >= 10
    assert "workspace.next" in reg
    assert "model.orbit" in reg


def test_unknown_intent_is_refused(reg):
    r = reg.check(Intent("rm.rf", confidence=1.0))
    assert r and "not in registry" in r


def test_confidence_floor_enforced(reg):
    # mic.mute has floor 0.95 — a shaky detection must not mute the mic
    assert reg.check(Intent("mic.mute", source="gesture", confidence=0.80))
    assert reg.check(Intent("mic.mute", source="gesture", confidence=0.97)) is None


def test_required_args_enforced(reg):
    assert reg.check(Intent("model.orbit", confidence=1.0, args={"dx": 1}))          # missing dy
    assert reg.check(Intent("model.orbit", confidence=1.0, args={"dx": 1, "dy": 2})) is None


def test_every_entry_is_namespaced_under_its_group(reg):
    for name in reg.names():
        assert "." in name and reg.spec(name).name == name
