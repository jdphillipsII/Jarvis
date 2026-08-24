"""End-to-end with a FAKE gesture source and FAKE actuator.

This is the proof the architecture holds with zero hardware: swap the source
and the actuator never knows.
"""
from core.bus import Bus
from core.debounce import Debouncer
from core.intent import Intent
from core.registry import Registry


class FakeCompositor:
    """Stands in for the KWin script."""
    def __init__(self):
        self.calls = []

    def __call__(self, intent: Intent):
        self.calls.append((intent.intent, intent.args))


def fake_vision_stream():
    """30 frames: nothing, a held swipe, nothing, a pinch."""
    return ([None] * 5 + ["workspace.next"] * 10 + [None] * 5
            + ["window.dismiss"] * 10)


def test_noisy_vision_stream_produces_exactly_two_actions():
    bus = Bus(registry=Registry.load())
    kwin = FakeCompositor()
    bus.subscribe("workspace.next", kwin)
    bus.subscribe("window.dismiss", kwin)

    deb = Debouncer(stable_frames=3, cooldown_s=999)   # cooldown: no repeats
    for frame in fake_vision_stream():
        name = deb.feed(frame)
        if name:
            bus.publish(Intent(name, source="gesture", confidence=0.93))

    assert [c[0] for c in kwin.calls] == ["workspace.next", "window.dismiss"]


def test_a_jittery_low_confidence_source_is_ignored_entirely():
    bus = Bus(registry=Registry.load())
    kwin = FakeCompositor()
    bus.subscribe("*", kwin)
    deb = Debouncer(stable_frames=3, cooldown_s=0)

    for frame in ["mic.mute"] * 10:
        name = deb.feed(frame)
        if name:
            bus.publish(Intent(name, source="gesture", confidence=0.60))

    assert kwin.calls == []            # mic.mute floor is 0.95
    assert bus.rejected
