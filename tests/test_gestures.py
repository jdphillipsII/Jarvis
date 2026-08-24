"""Hand-written landmark sets. No camera, no MediaPipe."""
import pytest
from core.gestures import (DragTracker, Gesture, GESTURE_INTENTS, classify,
                           extended, hand_span, pinch_gap)

# A canonical right hand, palm to camera, fingers up the -y axis.
# Wrist at origin; knuckles at y=-0.25; pips ~-0.40; tips ~-0.60.
def hand(index=True, middle=True, ring=True, pinky=True, thumb=True,
         thumb_at=None, scale=1.0, dx=0.0, dy=0.0):
    def P(x, y):
        return (x * scale + dx, y * scale + dy)
    curled, out = -0.30, -0.60
    lm = [P(0, 0)]                                        # 0 wrist
    lm += [P(.10, -.10), P(.16, -.18), P(.20, -.24),      # 1-3 thumb chain
           P(*(thumb_at if thumb_at else (.26, -.30) if thumb else (.06, -.20)))]
    for i, (name, on, x) in enumerate([("index", index, .06), ("middle", middle, .00),
                                       ("ring", ring, -.06), ("pinky", pinky, -.12)]):
        lm += [P(x, -.25), P(x, -.40), P(x, -.50),        # mcp, pip, dip
               P(x, out if on else curled)]               # tip
    return lm


def test_the_fixture_hand_is_well_formed():
    assert len(hand()) == 21


# ---- individual fingers ----

def test_extension_detects_each_finger():
    lm = hand(index=True, middle=False, ring=False, pinky=False)
    assert extended(lm, "index")
    assert not extended(lm, "middle")


# ---- gestures ----

def test_open_palm():
    assert classify(hand()).gesture is Gesture.OPEN_PALM


def test_fist():
    lm = hand(False, False, False, False, thumb=False)
    assert classify(lm).gesture is Gesture.FIST


def test_point():
    assert classify(hand(True, False, False, False, thumb=False)).gesture is Gesture.POINT


def test_peace():
    assert classify(hand(True, True, False, False, thumb=False)).gesture is Gesture.PEACE


def test_pinch_beats_the_finger_count():
    """Thumb and index touching is unambiguous and must win, or a drag in
    progress reads as a two-finger pose."""
    lm = hand(True, False, False, False, thumb_at=(.06, -.58))   # thumb on index tip
    assert classify(lm).gesture is Gesture.PINCH


def test_an_open_pinch_is_not_a_pinch():
    lm = hand(True, False, False, False, thumb_at=(.40, -.20))
    assert classify(lm).gesture is not Gesture.PINCH


# ---- robustness ----

def test_scale_invariance():
    """A hand at arm's length and a hand near the lens classify identically."""
    for s in (0.4, 1.0, 2.5):
        assert classify(hand(scale=s)).gesture is Gesture.OPEN_PALM
        assert classify(hand(True, False, False, False, thumb=False,
                             scale=s)).gesture is Gesture.POINT


def test_translation_invariance():
    for dx, dy in ((0.5, 0.0), (-0.3, 0.4)):
        assert classify(hand(dx=dx, dy=dy)).gesture is Gesture.OPEN_PALM


def test_pinch_gap_is_normalised_by_span():
    near = hand(True, False, False, False, thumb_at=(.06, -.58), scale=1.0)
    far = hand(True, False, False, False, thumb_at=(.06, -.58), scale=0.3)
    assert pinch_gap(near) == pytest.approx(pinch_gap(far), abs=1e-6)


@pytest.mark.parametrize("bad", [None, [], [(0, 0)] * 5])
def test_garbage_input_yields_no_gesture(bad):
    assert classify(bad).gesture is None


def test_an_unrecognised_pose_is_none_not_a_guess():
    """None breaks the debouncer's streak; guessing would fire an action."""
    assert classify(hand(False, False, True, True, thumb=False)).gesture is None


def test_confidence_is_reported():
    assert 0.0 < classify(hand()).confidence <= 1.0


# ---- drag ----

def test_drag_deltas_are_span_normalised():
    """The same physical movement must mean the same rotation at any distance."""
    t = DragTracker()
    near_a, near_b = classify(hand(scale=1.0)), classify(hand(scale=1.0, dx=0.1))
    t.start(near_a); dn = t.delta(near_b)

    t2 = DragTracker()
    far_a, far_b = classify(hand(scale=0.5)), classify(hand(scale=0.5, dx=0.05))
    t2.start(far_a); df = t2.delta(far_b)
    assert dn[0] == pytest.approx(df[0], abs=1e-3)


def test_first_delta_is_zero():
    t = DragTracker()
    assert t.delta(classify(hand())) == (0.0, 0.0)


def test_delta_is_relative_to_the_previous_frame_not_the_origin():
    """Two equal steps must report equal deltas. If the tracker measured from
    the origin instead, the second would be twice the first and a slow drag
    would accelerate."""
    t = DragTracker()
    t.start(classify(hand()))
    first = t.delta(classify(hand(dx=0.1)))
    second = t.delta(classify(hand(dx=0.2)))
    assert second[0] == pytest.approx(first[0], abs=1e-3)
    assert first[0] > 0


def test_stopping_clears_the_origin():
    t = DragTracker()
    t.start(classify(hand())); t.stop()
    assert t.origin is None


# ---- intent mapping ----

def test_every_mapped_intent_exists_in_the_registry():
    """A gesture that maps to an unregistered intent would be silently dropped."""
    from core.registry import Registry
    reg = Registry.load()
    for gesture, name in GESTURE_INTENTS.items():
        assert name in reg, f"{gesture} -> {name} missing from registry.yaml"


def test_pinch_is_not_a_discrete_intent():
    """It is a continuous drag, published as model.orbit, not a one-shot."""
    assert Gesture.PINCH not in GESTURE_INTENTS
