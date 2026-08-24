import pytest
from core.interrupt import is_pause_utterance


@pytest.mark.parametrize("said", [
    "stop", "Stop.", "pause", "shush", "hush", "quiet", "be quiet",
    "not now", "hold on", "never mind", "nevermind", "cancel",
    "shut up", "enough", "jarvis, stop", "Jarvis stop!"])
def test_stop_commands_match(said):
    assert is_pause_utterance(said)


@pytest.mark.parametrize("said", [
    "hold on let me check that",              # the false positive that matters
    "stop the build and redeploy",
    "can you pause the render",
    "not now but later remind me about the mount",
    "quiet hours should start at ten",
    "I need to stop doing that",
    "", "   "])
def test_ordinary_speech_never_silences_him(said):
    assert not is_pause_utterance(said)


def test_length_guard():
    assert not is_pause_utterance("stop " + "x" * 60)
