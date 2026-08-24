from core.debounce import Debouncer


def clockfn(t):
    return lambda: t[0]


def test_requires_consecutive_frames_before_firing():
    d = Debouncer(stable_frames=3, cooldown_s=0)
    assert d.feed("g") is None
    assert d.feed("g") is None
    assert d.feed("g") == "g"          # third confirms


def test_flicker_never_fires():
    d = Debouncer(stable_frames=3, cooldown_s=0)
    for name in ["a", "b", "a", "b", "a", "b"]:
        assert d.feed(name) is None


def test_a_dropped_frame_breaks_the_streak():
    d = Debouncer(stable_frames=3, cooldown_s=0)
    d.feed("g"); d.feed("g")
    assert d.feed(None) is None
    assert d.feed("g") is None         # streak restarted


def test_held_gesture_fires_once_not_thirty_times():
    t = [0.0]
    d = Debouncer(stable_frames=2, cooldown_s=1.0, clock=clockfn(t))
    fires = [d.feed("g") for _ in range(30)]     # one second of held gesture
    assert [f for f in fires if f] == ["g"]


def test_cooldown_expires():
    t = [0.0]
    d = Debouncer(stable_frames=1, cooldown_s=1.0, clock=clockfn(t))
    assert d.feed("g") == "g"
    t[0] = 0.5
    assert d.feed("g") is None
    t[0] = 1.6
    assert d.feed("g") == "g"
