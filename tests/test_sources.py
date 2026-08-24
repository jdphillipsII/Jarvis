import time
import pytest
from core.observation import Observation
from core.policy import Urgency
from core.sources import SourceRunner, SourceSpec, source, get_sources, clear_sources


def obs(text="something", urg=Urgency.INFO, key="k"):
    return Observation(text, urg, "test", key)


@pytest.fixture(autouse=True)
def clean():
    clear_sources(); yield; clear_sources()


def test_decorator_registers_once_so_double_import_is_safe():
    @source("dupe")
    def a(): return []
    @source("dupe")
    def b(): return []
    assert len(get_sources()) == 1


def test_a_hanging_watcher_costs_only_its_own_slot():
    """The reason for a per-source timeout: one wedged sensor must not stop
    all proactive intelligence."""
    def hangs(): time.sleep(10)
    def works(): return [obs("fine")]
    r = SourceRunner().collect([
        SourceSpec("hangs", hangs, 0, timeout_s=0.15),
        SourceSpec("works", works, 0),
    ])
    assert [o.text for o in r.observations] == ["fine"]
    assert ("hangs", "timeout") in r.failed


def test_a_raising_watcher_is_isolated():
    def boom(): raise RuntimeError("i2c bus wedged")
    r = SourceRunner().collect([
        SourceSpec("boom", boom, 0),
        SourceSpec("ok", lambda: [obs("fine")], 0),
    ])
    assert len(r.observations) == 1
    assert r.failed[0][0] == "boom" and "i2c" in r.failed[0][1]


def test_garbage_return_is_rejected_not_propagated():
    r = SourceRunner().collect([SourceSpec("bad", lambda: ["a string"], 0)])
    assert r.observations == []
    assert "non-Observation" in r.failed[0][1]


def test_intervals_are_respected():
    t = [0.0]
    runner = SourceRunner(clock=lambda: t[0])
    spec = SourceSpec("slow", lambda: [obs()], interval_s=60.0)
    assert runner.collect([spec]).ran == ["slow"]
    t[0] = 30.0
    assert runner.collect([spec]).ran == []          # not due
    t[0] = 61.0
    assert runner.collect([spec]).ran == ["slow"]


def test_empty_returns_are_normal():
    r = SourceRunner().collect([SourceSpec("quiet", lambda: [], 0)])
    assert r.observations == [] and r.failed == [] and r.ran == ["quiet"]
