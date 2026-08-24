import pytest
from core.affirmation import is_affirmative, is_negative


@pytest.mark.parametrize("said", [
    "yes", "Yes.", "yeah", "yep", "sure", "ok", "okay", "do it", "go ahead",
    "please do", "confirm", "confirmed", "proceed", "make it so", "affirmative"])
def test_agreement(said):
    assert is_affirmative(said) and not is_negative(said)


@pytest.mark.parametrize("said", [
    "no", "nope", "nah", "don't", "do not", "cancel", "forget it",
    "leave it", "never mind", "not now", "stop", "abort", "negative"])
def test_refusal(said):
    assert is_negative(said) and not is_affirmative(said)


@pytest.mark.parametrize("said", [
    "yes but change the name first",       # qualified — NOT consent
    "do it later",
    "ok so what about the other thing",
    "sure, after you check the disk",
    "no idea what that means",
    "yes or no",
    "", "   "])
def test_anything_qualified_is_neither(said):
    """A qualified yes is not a yes. It becomes a new request instead."""
    assert not is_affirmative(said)


def test_long_utterances_are_never_consent():
    assert not is_affirmative("yes " + "x" * 60)
