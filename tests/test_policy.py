from datetime import datetime
import pytest
from core.policy import (Cooldown, Decision, Delivery, DeliveryContext, DayType,
                         SpeakPolicy, TimeOfDay, Urgency)


def ctx(**kw):
    base = dict(time_of_day=TimeOfDay.AFTERNOON, day_type=DayType.WORKDAY,
                local_hour=14, hour_of_week=2 * 24 + 14)
    base.update(kw)
    return DeliveryContext(**base)


@pytest.fixture
def pol():
    return SpeakPolicy()


# ---- the governing rule ----

def test_nothing_proactive_ever_auto_speaks(pol):
    """CHIME is the ceiling. No urgency, hour, or state unlocks speech."""
    for urg in Urgency:
        for tod in TimeOfDay:
            for focused in (True, False):
                for quiet in (True, False):
                    d = pol.decide(urg, ctx(time_of_day=tod, is_focused=focused,
                                            is_quiet_hours=quiet))
                    assert d.delivery in (Delivery.CHIME, Delivery.BADGE,
                                          Delivery.BATCH, Delivery.SUPPRESS)


def test_every_decision_explains_itself(pol):
    for urg in Urgency:
        assert pol.decide(urg, ctx()).reason


# ---- presence ----

def test_never_talks_to_an_empty_room(pol):
    d = pol.decide(Urgency.CRITICAL, ctx(user_present=False))
    assert d.delivery is Delivery.BATCH and "away" in d.reason


# ---- quiet hours ----

def test_quiet_hours_badge_critical_batch_the_rest(pol):
    assert pol.decide(Urgency.CRITICAL, ctx(is_quiet_hours=True)).delivery is Delivery.BADGE
    assert pol.decide(Urgency.WARN, ctx(is_quiet_hours=True)).delivery is Delivery.BATCH
    assert pol.decide(Urgency.INFO, ctx(is_quiet_hours=True)).delivery is Delivery.BATCH


# ---- focus: the check Axon's version lacked ----

def test_focus_protects_deep_work(pol):
    f = ctx(is_focused=True)
    assert pol.decide(Urgency.INFO, f).delivery is Delivery.BATCH
    assert pol.decide(Urgency.WARN, f).delivery is Delivery.BADGE
    assert pol.decide(Urgency.CRITICAL, f).delivery is Delivery.CHIME


def test_focus_is_quieter_than_the_same_moment_unfocused(pol):
    rank = {Delivery.CHIME: 3, Delivery.BADGE: 2, Delivery.BATCH: 1, Delivery.SUPPRESS: 0}
    for urg in (Urgency.INFO, Urgency.WARN):
        assert rank[pol.decide(urg, ctx(is_focused=True)).delivery] \
            <= rank[pol.decide(urg, ctx(is_focused=False)).delivery]


# ---- time of day ----

def test_night_drops_info_entirely(pol):
    n = ctx(time_of_day=TimeOfDay.NIGHT, local_hour=2)
    assert pol.decide(Urgency.INFO, n).delivery is Delivery.SUPPRESS
    assert pol.decide(Urgency.WARN, n).delivery is Delivery.BADGE
    assert pol.decide(Urgency.CRITICAL, n).delivery is Delivery.CHIME


def test_friday_afternoon_and_weekend_defer_info(pol):
    assert pol.decide(Urgency.INFO, ctx(day_type=DayType.FRIDAY)).delivery is Delivery.BATCH
    assert pol.decide(Urgency.INFO, ctx(day_type=DayType.WEEKEND)).delivery is Delivery.BATCH


def test_normal_working_moment_chimes_on_warn(pol):
    assert pol.decide(Urgency.WARN, ctx()).delivery is Delivery.CHIME
    assert pol.decide(Urgency.INFO, ctx()).delivery is Delivery.BADGE


# ---- cooldown ----

def test_flapping_condition_only_surfaces_once():
    t = [0.0]
    pol = SpeakPolicy(cooldown=Cooldown(seconds=1800, clock=lambda: t[0]))
    first = pol.decide(Urgency.WARN, ctx(), category="gpu", key="temp-high")
    pol.record("gpu", "temp-high")
    assert first.delivery is Delivery.CHIME
    for t[0] in (60.0, 600.0, 1799.0):
        assert pol.decide(Urgency.WARN, ctx(), category="gpu",
                          key="temp-high").delivery is Delivery.SUPPRESS
    t[0] = 1801.0
    assert pol.decide(Urgency.WARN, ctx(), category="gpu",
                      key="temp-high").delivery is Delivery.CHIME


def test_cooldown_is_keyed_on_identity_not_wording():
    t = [0.0]
    pol = SpeakPolicy(cooldown=Cooldown(seconds=100, clock=lambda: t[0]))
    pol.record("gpu", "temp-high")
    assert pol.decide(Urgency.WARN, ctx(), category="gpu", key="temp-high").delivery is Delivery.SUPPRESS
    assert pol.decide(Urgency.WARN, ctx(), category="gpu", key="fan-stall").delivery is Delivery.CHIME


# ---- mute ----

def test_muted_category_is_dropped_but_critical_still_lands():
    pol = SpeakPolicy(muted_categories=frozenset({"builds"}))
    assert pol.decide(Urgency.WARN, ctx(), category="builds").delivery is Delivery.SUPPRESS
    assert pol.decide(Urgency.CRITICAL, ctx(), category="builds").delivery is Delivery.CHIME


# ---- context construction ----

@pytest.mark.parametrize("hour,expected", [
    (2, TimeOfDay.NIGHT), (6, TimeOfDay.EARLY_MORNING), (10, TimeOfDay.MORNING),
    (14, TimeOfDay.AFTERNOON), (19, TimeOfDay.EVENING), (23, TimeOfDay.NIGHT)])
def test_time_of_day_buckets(hour, expected):
    c = DeliveryContext.from_clock(datetime(2026, 8, 26, hour, 0))   # a Wednesday
    assert c.time_of_day is expected


def test_day_type_and_hour_of_week():
    fri = DeliveryContext.from_clock(datetime(2026, 8, 28, 15, 0))
    sat = DeliveryContext.from_clock(datetime(2026, 8, 29, 15, 0))
    assert fri.day_type is DayType.FRIDAY and sat.day_type is DayType.WEEKEND
    assert fri.hour_of_week == 4 * 24 + 15


def test_decision_is_falsy_only_when_suppressed():
    assert not Decision(Delivery.SUPPRESS, "x")
    assert Decision(Delivery.BATCH, "x")
