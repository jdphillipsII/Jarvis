import pytest
from core.bus import Bus
from core.intent import Intent
from core.observation import Observation
from core.policy import (Cooldown, DayType, DeliveryContext, SpeakPolicy,
                         TimeOfDay, Urgency)
from core.presence import PresenceEvent, PresenceEventType
from core.registry import Registry
from daemon.greeter import Greeter
from daemon.proactive import Briefing


def ctx(tod=TimeOfDay.MORNING, **kw):
    base = dict(time_of_day=tod, day_type=DayType.WORKDAY, local_hour=9,
                hour_of_week=2 * 24 + 9)
    base.update(kw)
    return DeliveryContext(**base)


def greeter(briefing=None, context=None):
    return Greeter(bus=Bus(registry=Registry.load()),
                   briefing=briefing or Briefing(),
                   policy=SpeakPolicy(cooldown=Cooldown(seconds=0)),
                   context_fn=lambda: context or ctx())


def arrived(should_greet=True, seconds=600.0):
    return PresenceEvent(PresenceEventType.ARRIVED, seconds, should_greet)


def test_greets_on_a_real_return():
    g = greeter()
    assert "Good morning, sir." == g.handle(arrived())


def test_stays_quiet_after_a_brief_absence():
    assert greeter().handle(arrived(should_greet=False)) is None


def test_leaving_is_never_greeted():
    g = greeter()
    assert g.handle(PresenceEvent(PresenceEventType.LEFT, 100.0)) is None


@pytest.mark.parametrize("tod,expected", [
    (TimeOfDay.EARLY_MORNING, "up early"), (TimeOfDay.MORNING, "Good morning"),
    (TimeOfDay.AFTERNOON, "Afternoon"), (TimeOfDay.EVENING, "Evening"),
    (TimeOfDay.NIGHT, "Still up")])
def test_salutation_matches_the_hour(tod, expected):
    g = greeter(context=ctx(tod))
    text = g.handle(arrived())
    assert text and expected in text


def test_held_items_are_delivered_on_return():
    b = Briefing()
    b.add(Observation("the build passed", Urgency.INFO, "ci", "1"))
    g = greeter(briefing=b)
    text = g.handle(arrived())
    assert "build passed" in text
    assert len(b) == 0                      # drained, not repeated next time


def test_nothing_held_means_a_bare_greeting():
    text = greeter().handle(arrived())
    assert "While you were away" not in text


def test_quiet_hours_suppress_even_the_greeting():
    g = greeter(context=ctx(is_quiet_hours=True))
    assert g.handle(arrived()) is None


def test_briefing_survives_a_suppressed_greeting():
    """Suppressed is not consumed: what was held must still be there later."""
    b = Briefing()
    b.add(Observation("something", Urgency.INFO, "c", "k"))
    g = greeter(briefing=b, context=ctx(is_quiet_hours=True))
    assert g.handle(arrived()) is None
    assert len(b) == 1


def test_greeting_is_an_offer_never_speech():
    g = greeter()
    seen = []
    g.bus.subscribe("jarvis.*", lambda i: seen.append(i.intent))
    g.handle(arrived())
    assert seen == ["jarvis.offer"]


def test_attaches_to_the_bus_and_fires_from_a_presence_intent():
    g = greeter().attach()
    seen = []
    g.bus.subscribe("jarvis.*", lambda i: seen.append(i.args["text"]))
    g.bus.publish(Intent("presence.arrived", "presence", 0.9,
                         {"away_seconds": 900.0, "should_greet": True}))
    assert seen and "morning" in seen[0]


def test_repeated_arrivals_are_rate_limited():
    t = [0.0]
    g = greeter()
    g.policy = SpeakPolicy(cooldown=Cooldown(seconds=600, clock=lambda: t[0]))
    assert g.handle(arrived()) is not None
    t[0] = 60.0
    assert g.handle(arrived()) is None       # cooldown holds
