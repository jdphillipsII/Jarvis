import pytest
from core.presence import (PresenceConfig, PresenceEventType, PresenceState,
                           PresenceTracker)

CFG = PresenceConfig(arrive_frames=3, leave_grace_s=10.0, regreet_after_s=60.0)


def tracker(t):
    return PresenceTracker(CFG, clock=lambda: t[0])


def test_arrival_needs_consecutive_frames():
    t = [0.0]; tr = tracker(t)
    assert tr.feed(True) is None
    assert tr.feed(True) is None
    e = tr.feed(True)
    assert e and e.type is PresenceEventType.ARRIVED
    assert tr.is_present


def test_a_passer_by_does_not_count_as_arrival():
    t = [0.0]; tr = tracker(t)
    for d in (True, True, False, True, False, True):
        assert tr.feed(d) is None
    assert tr.state is PresenceState.AWAY


def test_leaning_out_of_frame_is_not_leaving():
    """The grace window: reaching for coffee must not end your session."""
    t = [0.0]; tr = tracker(t)
    for _ in range(3): tr.feed(True)
    for t[0] in (1.0, 3.0, 6.0, 9.0):
        assert tr.feed(False) is None          # under the 10s grace
    t[0] = 9.5
    assert tr.feed(True) is None
    assert tr.is_present


def test_sustained_absence_ends_the_session():
    t = [0.0]; tr = tracker(t)
    for _ in range(3): tr.feed(True)
    t[0] = 100.0; tr.feed(False)
    t[0] = 111.0
    e = tr.feed(False)
    assert e and e.type is PresenceEventType.LEFT
    assert not tr.is_present


def test_a_brief_absence_earns_no_greeting():
    """Returning after 30 seconds must not trigger 'welcome back, sir'."""
    t = [0.0]; tr = tracker(t)
    for _ in range(3): tr.feed(True)
    t[0] = 10.0; tr.feed(False)
    t[0] = 21.0; tr.feed(False)                # LEFT, away clock starts at 10.0
    t[0] = 35.0
    for _ in range(2): tr.feed(True)
    e = tr.feed(True)
    assert e.type is PresenceEventType.ARRIVED
    assert e.should_greet is False             # only 25s away


def test_a_real_absence_earns_a_greeting():
    t = [0.0]; tr = tracker(t)
    for _ in range(3): tr.feed(True)
    t[0] = 10.0; tr.feed(False)
    t[0] = 21.0; tr.feed(False)                # LEFT
    t[0] = 600.0
    for _ in range(2): tr.feed(True)
    e = tr.feed(True)
    assert e.should_greet is True


def test_away_time_is_backdated_to_the_actual_departure():
    """Away time counts from when they vanished, not from when we believed it."""
    t = [0.0]; tr = tracker(t)
    for _ in range(3): tr.feed(True)
    t[0] = 100.0; tr.feed(False)               # actually gone at 100
    t[0] = 111.0; tr.feed(False)               # we notice at 111
    t[0] = 160.0
    for _ in range(2): tr.feed(True)
    e = tr.feed(True)
    assert e.seconds == pytest.approx(60.0)    # 160-100, not 160-111


def test_present_duration_is_reported_on_leaving():
    t = [0.0]; tr = tracker(t)
    for _ in range(3): tr.feed(True)
    t[0] = 500.0; tr.feed(False)
    t[0] = 511.0
    e = tr.feed(False)
    assert e.seconds == pytest.approx(500.0)


def test_full_cycle_repeats_cleanly():
    t = [0.0]; tr = tracker(t)
    events = []
    for cycle in range(3):
        base = cycle * 1000.0
        t[0] = base
        for _ in range(3):
            if (e := tr.feed(True)): events.append(e.type)
        t[0] = base + 100.0; tr.feed(False)
        t[0] = base + 120.0
        if (e := tr.feed(False)): events.append(e.type)
    assert events == [PresenceEventType.ARRIVED, PresenceEventType.LEFT] * 3
