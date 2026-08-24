"""The full proactive chain, end to end, with fake watchers and a fake clock."""
from datetime import datetime
import pytest

from core.bus import Bus
from core.observation import Observation
from core.policy import (Cooldown, DeliveryContext, SpeakPolicy, TimeOfDay,
                         DayType, Urgency)
from core.registry import Registry
from core.sources import SourceRunner, SourceSpec
from daemon.proactive import ProactiveDaemon, Briefing


def ctx(**kw):
    base = dict(time_of_day=TimeOfDay.AFTERNOON, day_type=DayType.WORKDAY,
                local_hour=14, hour_of_week=2 * 24 + 14)
    base.update(kw)
    return DeliveryContext(**base)


def daemon(bus=None, context=None, cooldown=None):
    return ProactiveDaemon(
        bus=bus or Bus(registry=Registry.load()),
        policy=SpeakPolicy(cooldown=cooldown or Cooldown(seconds=0)),
        runner=SourceRunner(),
        context_fn=lambda: context or ctx(),
    )


def watcher(*observations):
    return SourceSpec("fake", lambda: list(observations), 0)


def test_warning_becomes_an_offer_not_speech():
    bus = Bus(registry=Registry.load())
    seen = []
    bus.subscribe("jarvis.*", lambda i: seen.append(i.intent))
    d = daemon(bus)
    d.tick([watcher(Observation("GPU is warm, sir.", Urgency.WARN, "gpu", "temp"))])
    assert seen == ["jarvis.offer"]           # never jarvis.speak


def test_nothing_ever_reaches_jarvis_speak_proactively():
    bus = Bus(registry=Registry.load())
    spoken = []
    bus.subscribe("jarvis.speak", spoken.append)
    for urg in Urgency:
        for tod in TimeOfDay:
            d = daemon(bus, context=ctx(time_of_day=tod))
            d.tick([watcher(Observation("x", urg, "c", f"{urg}{tod}"))])
    assert spoken == []


def test_info_while_focused_is_held_for_the_briefing():
    d = daemon(context=ctx(is_focused=True))
    d.tick([watcher(Observation("Build finished, sir.", Urgency.INFO, "ci", "b1"))])
    assert len(d.briefing) == 1


def test_absent_user_gets_everything_batched():
    d = daemon(context=ctx(user_present=False))
    d.tick([watcher(
        Observation("a", Urgency.INFO, "c", "1"),
        Observation("b", Urgency.CRITICAL, "c", "2"))])
    assert len(d.briefing) == 2


def test_night_info_is_dropped_entirely_not_batched():
    d = daemon(context=ctx(time_of_day=TimeOfDay.NIGHT, local_hour=2))
    d.tick([watcher(Observation("minor", Urgency.INFO, "c", "k"))])
    assert len(d.briefing) == 0


def test_a_flapping_watcher_only_surfaces_once():
    t = [0.0]
    d = daemon(cooldown=Cooldown(seconds=600, clock=lambda: t[0]))
    seen = []
    d.bus.subscribe("jarvis.*", lambda i: seen.append(i.args["text"]))
    o = Observation("GPU warm, sir.", Urgency.WARN, "gpu", "temp-high")
    for t[0] in (0.0, 60.0, 120.0, 300.0):
        d.tick([watcher(o)])
    assert seen == ["GPU warm, sir."]


def test_a_broken_watcher_does_not_stop_the_others():
    d = daemon()
    seen = []
    d.bus.subscribe("jarvis.*", lambda i: seen.append(i.args["text"]))
    r = d.tick([
        SourceSpec("boom", lambda: (_ for _ in ()).throw(RuntimeError("nope")), 0),
        watcher(Observation("still here, sir.", Urgency.WARN, "c", "k")),
    ])
    assert seen == ["still here, sir."]
    assert r.failed and r.failed[0][0] == "boom"


def test_published_intents_carry_the_policy_reason():
    d = daemon(context=ctx(is_focused=True))
    got = []
    d.bus.subscribe("jarvis.*", got.append)
    d.tick([watcher(Observation("x", Urgency.WARN, "c", "k"))])
    assert "focused" in got[0].args["reason"]


# ---- briefing ----

def test_briefing_orders_by_urgency_and_drains():
    b = Briefing()
    b.add(Observation("minor thing", Urgency.INFO, "c", "1"))
    b.add(Observation("the disk is full", Urgency.CRITICAL, "c", "2"))
    assert b.summary().index("disk") < b.summary().index("minor")
    assert len(b.drain()) == 2 and len(b) == 0


def test_empty_briefing_says_so():
    assert "Nothing held" in Briefing().summary()


def test_long_briefing_is_truncated_with_a_count():
    b = Briefing()
    for i in range(8):
        b.add(Observation(f"item {i}", Urgency.INFO, "c", str(i)))
    assert "And 3 more" in b.summary()
