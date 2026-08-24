"""Landmarks through classifier, debouncer, registry and bus — no camera."""
from core.bus import Bus
from core.debounce import Debouncer
from core.gestures import DragTracker, Gesture, GESTURE_INTENTS, classify
from core.intent import Intent
from core.registry import Registry
from tests.test_gestures import hand


def pipeline(frames, stable=3, confidence=0.9):
    """Drive raw landmark frames all the way to published intents."""
    bus = Bus(registry=Registry.load())
    fired = []
    bus.subscribe("*", lambda i: fired.append((i.intent, i.args)))
    deb = Debouncer(stable_frames=stable, cooldown_s=999)
    drag, dragging = DragTracker(), False

    for lm in frames:
        r = classify(lm)
        if r.gesture is Gesture.PINCH:
            if not dragging:
                drag.start(r); dragging = True; deb.reset()
            else:
                dx, dy = drag.delta(r)
                if abs(dx) > 0.004 or abs(dy) > 0.004:
                    bus.publish(Intent("model.orbit", "gesture", confidence,
                                       {"dx": dx, "dy": dy}))
        else:
            if dragging:
                drag.stop(); dragging = False
            got = deb.feed(r.gesture.value if r.gesture else None)
            if got:
                bus.publish(Intent(GESTURE_INTENTS[Gesture(got)], "gesture",
                                   confidence, {}))
    return bus, fired


def test_a_held_palm_dismisses_exactly_once():
    _, fired = pipeline([hand()] * 30)
    assert [f[0] for f in fired] == ["window.dismiss"]


def test_a_flickering_hand_fires_nothing():
    frames = [hand(), None, hand(), None, hand(), None] * 4
    _, fired = pipeline(frames)
    assert fired == []


def test_a_pinch_drag_streams_orbit_deltas():
    frames = [hand(True, False, False, False, thumb_at=(.06, -.58), dx=i * 0.02)
              for i in range(6)]
    _, fired = pipeline(frames)
    assert [f[0] for f in fired] == ["model.orbit"] * 5     # first frame anchors
    assert all(f[1]["dx"] > 0 for f in fired)


def test_a_motionless_pinch_publishes_nothing():
    """Holding still must not spray zero-deltas at the compositor."""
    frames = [hand(True, False, False, False, thumb_at=(.06, -.58))] * 10
    _, fired = pipeline(frames)
    assert fired == []


def test_low_confidence_gestures_are_refused_by_the_registry():
    """A shaky detection must not mute the mic — the floor is 0.95."""
    frames = [hand(False, False, False, False, thumb=False)] * 10
    bus, fired = pipeline(frames, confidence=0.7)
    assert fired == []
    assert bus.rejected and "floor" in bus.rejected[0][1]


def test_a_confident_fist_does_mute():
    frames = [hand(False, False, False, False, thumb=False)] * 10
    _, fired = pipeline(frames, confidence=0.97)
    assert [f[0] for f in fired] == ["mic.mute"]


def test_switching_gestures_fires_each_once():
    frames = [hand()] * 8 + [None] * 3 + \
             [hand(True, False, False, False, thumb=False)] * 8
    _, fired = pipeline(frames)
    assert [f[0] for f in fired] == ["window.dismiss", "window.focus"]
