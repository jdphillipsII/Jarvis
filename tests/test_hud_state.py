import pytest
from core.hud_state import Card, HudState, OpState
from core.policy import Urgency


def card(urg=Urgency.INFO, cid="a", kind="offer"):
    return Card(id=cid, text="something", urgency=urg, kind=kind)


def test_nothing_pending_is_calm():
    assert HudState().op_state() is OpState.CALM


def test_a_pending_offer_raises_to_elevated():
    s = HudState(); s.add(card(Urgency.WARN))
    assert s.op_state() is OpState.ELEVATED


def test_critical_outranks_everything():
    """The one thing allowed to break flow."""
    s = HudState(focused=True)
    s.add(card(Urgency.CRITICAL))
    assert s.op_state() is OpState.CRITICAL


def test_focus_outranks_a_mere_warning():
    """A warning you've already deferred must not keep the room amber."""
    s = HudState(focused=True)
    s.add(card(Urgency.WARN))
    assert s.op_state() is OpState.FOCUSED


def test_badges_do_not_raise_the_state():
    """Only answerable offers change the room; a badge is just a mark."""
    s = HudState()
    s.add(card(Urgency.CRITICAL, kind="badge"))
    assert s.op_state() is OpState.CALM


def test_resolving_the_last_offer_returns_to_calm():
    s = HudState(); s.add(card(Urgency.WARN, "x"))
    assert s.resolve("x") is not None
    assert s.op_state() is OpState.CALM


def test_resolving_an_unknown_offer_is_harmless():
    assert HudState().resolve("nope") is None


def test_an_offer_replaces_its_earlier_self():
    """Re-raising the same id must not stack duplicates on screen."""
    s = HudState()
    s.add(card(Urgency.WARN, "gpu"))
    s.add(card(Urgency.CRITICAL, "gpu"))
    assert len(s.offers) == 1 and s.op_state() is OpState.CRITICAL


def test_feed_is_bounded():
    s = HudState()
    for i in range(200):
        s.add(card(cid=str(i), kind="badge"))
    assert len(s.feed) <= 40


def test_feed_is_newest_first():
    s = HudState()
    s.add(Card("1", "older", kind="badge"))
    s.add(Card("2", "newer", kind="badge"))
    assert s.feed[0].text == "newer"


def test_snapshot_is_json_safe():
    import json
    s = HudState(telemetry={"gpu_temp_c": 61})
    s.add(card(Urgency.WARN))
    json.dumps(s.snapshot())          # must not raise
    assert s.snapshot()["state"] == "elevated"
