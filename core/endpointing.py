"""End-of-speech detection: the hardest single problem in conversational voice.

Naive endpointing ("stop when RMS drops for N ms") cuts the user off the moment
they pause to think. The fix is a POST_SPEECH intermediate state: silence starts
a countdown rather than ending the turn, and speech resuming before the timer
expires is treated as a mid-sentence pause and emits nothing.

    SILENCE     -> SPEECH       prob > threshold, sustained for min_speech_ms
    SPEECH      -> POST_SPEECH  prob fell below threshold
    POST_SPEECH -> SILENCE      quiet for min_silence_ms   => SPEECH_END
    POST_SPEECH -> SPEECH       speech resumed             => (mid-sentence pause)

The probability source is deliberately not specified. Feed it Silero VAD in
production or plain RMS to start; this module is pure arithmetic and is tested
with synthetic probability sequences, no audio hardware required.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SpeechState(str, Enum):
    SILENCE = "silence"
    SPEECH = "speech"
    POST_SPEECH = "post_speech"     # maybe done, maybe just thinking


class VoiceEvent(str, Enum):
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"


@dataclass(frozen=True)
class EndpointerConfig:
    threshold: float = 0.5          # prob above this counts as voice
    min_speech_ms: int = 250        # ignore coughs, door clicks, chair creaks
    min_silence_ms: int = 700       # how long a pause may run before the turn ends
    window_ms: int = 32             # 512 samples @ 16 kHz — Silero's frame size


class Endpointer:
    """Feed one probability per audio window; get an event or None."""

    def __init__(self, config: Optional[EndpointerConfig] = None):
        self.cfg = config or EndpointerConfig()
        self.state = SpeechState.SILENCE
        self._speech_ms = 0         # sustained voice, for the min_speech gate
        self._silence_ms = 0        # sustained quiet while in POST_SPEECH

    def feed(self, probability: float) -> Optional[VoiceEvent]:
        voiced = probability > self.cfg.threshold
        w = self.cfg.window_ms

        if self.state is SpeechState.SILENCE:
            if voiced:
                self._speech_ms += w
                if self._speech_ms >= self.cfg.min_speech_ms:
                    self.state = SpeechState.SPEECH
                    self._silence_ms = 0
                    return VoiceEvent.SPEECH_START
            else:
                self._speech_ms = 0          # blip, not speech
            return None

        if self.state is SpeechState.SPEECH:
            if not voiced:
                self.state = SpeechState.POST_SPEECH
                self._silence_ms = w
            return None

        # POST_SPEECH — the countdown that makes pauses survivable
        if voiced:
            self.state = SpeechState.SPEECH   # they were just thinking
            self._silence_ms = 0
            return None
        self._silence_ms += w
        if self._silence_ms >= self.cfg.min_silence_ms:
            self.state = SpeechState.SILENCE
            self._speech_ms = 0
            return VoiceEvent.SPEECH_END
        return None

    @property
    def is_speaking(self) -> bool:
        return self.state is not SpeechState.SILENCE

    def reset(self) -> None:
        self.state = SpeechState.SILENCE
        self._speech_ms = self._silence_ms = 0
