import pytest
from core.rms_vad import RmsVad
from core.endpointing import Endpointer, EndpointerConfig, VoiceEvent


def test_calibration_sets_the_floor_from_ambient():
    v = RmsVad()
    v.calibrate([0.01, 0.012, 0.011, 0.009])
    assert 0.009 <= v.noise_floor <= 0.012


def test_median_ignores_a_cough_during_calibration():
    v = RmsVad()
    v.calibrate([0.01, 0.01, 0.01, 0.9])       # one loud outlier
    assert v.noise_floor < 0.02


def test_quiet_room_reads_as_no_voice():
    v = RmsVad(); v.calibrate([0.01] * 5)
    assert v.probability(0.011) == 0.0


def test_loud_speech_saturates():
    v = RmsVad(); v.calibrate([0.01] * 5)
    assert v.probability(0.20) == 1.0


def test_ramp_is_monotonic_between_onset_and_full():
    v = RmsVad(); v.calibrate([0.01] * 5)
    probs = [v.probability(r) for r in (0.02, 0.03, 0.04, 0.05, 0.06)]
    assert probs == sorted(probs)
    assert 0.0 < probs[2] < 1.0


def test_same_speech_in_a_louder_room_still_detected():
    """The point of calibrating: absolute levels differ per room and mic."""
    quiet, loud = RmsVad(), RmsVad()
    quiet.calibrate([0.005] * 5)
    loud.calibrate([0.05] * 5)
    assert quiet.probability(0.05) == 1.0      # 10x floor
    assert loud.probability(0.50) == 1.0       # also 10x its own floor


def test_bad_config_rejected():
    with pytest.raises(ValueError):
        RmsVad(onset=6.0, full=2.0)


def test_end_to_end_rms_into_endpointer():
    """A realistic capture: ambient, a sentence with a pause, then quiet."""
    v = RmsVad(); v.calibrate([0.01] * 10)
    ep = Endpointer(EndpointerConfig(min_speech_ms=96, min_silence_ms=320, window_ms=32))
    stream = [0.01]*5 + [0.08]*6 + [0.011]*8 + [0.08]*6 + [0.01]*12
    events = [e for e in (ep.feed(v.probability(r)) for r in stream) if e]
    assert events == [VoiceEvent.SPEECH_START, VoiceEvent.SPEECH_END]
