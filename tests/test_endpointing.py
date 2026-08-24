import pytest
from core.endpointing import Endpointer, EndpointerConfig, SpeechState, VoiceEvent

CFG = EndpointerConfig(threshold=0.5, min_speech_ms=100, min_silence_ms=300, window_ms=50)


def drive(ep, probs):
    """Feed a sequence, return the events emitted."""
    return [e for e in (ep.feed(p) for p in probs) if e]


def test_sustained_speech_starts_a_turn():
    ep = Endpointer(CFG)
    assert drive(ep, [0.9, 0.9]) == [VoiceEvent.SPEECH_START]   # 2 x 50ms = min_speech
    assert ep.state is SpeechState.SPEECH


def test_a_cough_never_starts_a_turn():
    ep = Endpointer(CFG)
    assert drive(ep, [0.9, 0.1, 0.9, 0.1, 0.9, 0.1]) == []      # never sustained
    assert ep.state is SpeechState.SILENCE


def test_full_turn_emits_start_then_end():
    ep = Endpointer(CFG)
    events = drive(ep, [0.9] * 4 + [0.1] * 6)                    # speak, then 300ms quiet
    assert events == [VoiceEvent.SPEECH_START, VoiceEvent.SPEECH_END]


def test_mid_sentence_pause_does_not_end_the_turn():
    """The whole point: pausing to think must not cut the user off."""
    ep = Endpointer(CFG)
    events = drive(ep, [0.9] * 4          # "set the workshop..."
                     + [0.1] * 5          # 250ms pause — under the 300ms threshold
                     + [0.9] * 4)         # "...to the blue one"
    assert events == [VoiceEvent.SPEECH_START]                   # no SPEECH_END
    assert ep.state is SpeechState.SPEECH


def test_pause_longer_than_threshold_does_end_the_turn():
    ep = Endpointer(CFG)
    events = drive(ep, [0.9] * 4 + [0.1] * 6 + [0.9] * 4)
    assert events == [VoiceEvent.SPEECH_START, VoiceEvent.SPEECH_END,
                      VoiceEvent.SPEECH_START]                   # second turn began


def test_post_speech_is_entered_on_first_quiet_window():
    ep = Endpointer(CFG)
    drive(ep, [0.9] * 4)
    ep.feed(0.1)
    assert ep.state is SpeechState.POST_SPEECH                   # not SILENCE — countdown


def test_two_turns_in_a_row():
    ep = Endpointer(CFG)
    events = drive(ep, [0.9] * 4 + [0.1] * 8 + [0.9] * 4 + [0.1] * 8)
    assert events == [VoiceEvent.SPEECH_START, VoiceEvent.SPEECH_END] * 2


def test_reset_clears_state():
    ep = Endpointer(CFG)
    drive(ep, [0.9] * 4)
    ep.reset()
    assert ep.state is SpeechState.SILENCE and not ep.is_speaking
