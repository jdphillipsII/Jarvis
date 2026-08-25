#!/usr/bin/env python3
"""JARVIS voice loop — wake -> listen -> think -> speak.

    "hey jarvis"  -> openWakeWord fires
                  -> record until you stop talking (silence endpointing)
                  -> faster-whisper transcribes (CPU; the 12900K eats it)
                  -> Ollama replies in the JARVIS persona
                  -> Piper speaks it as Alan

Run:  source .venvs/voice/bin/activate && python voice/loop.py
"""
import os, sys, time, shutil, subprocess, tempfile
from collections import deque
import numpy as np, sounddevice as sd, requests
from openwakeword.model import Model as WakeModel
from faster_whisper import WhisperModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.endpointing import Endpointer, EndpointerConfig, VoiceEvent   # noqa: E402
from core.rms_vad import RmsVad
from core.config import cfg                                          # noqa: E402
from core.agent import Agent, PERSONA                                    # noqa: E402
from core.interrupt import is_pause_utterance                            # noqa: E402
from core.ollama import OllamaChat                                       # noqa: E402
from core.registry import Registry                                       # noqa: E402
from core.bus import Bus                                                 # noqa: E402
from core.toolbox import Toolbox                                         # noqa: E402
from core.tools import Agency                                            # noqa: E402
from daemon.toolbox.builtin import build as build_tools                  # noqa: E402

CHAT_MODEL = cfg("JARVIS_CHAT_MODEL", "qwen2.5:7b")
VOICE      = cfg("JARVIS_VOICE", "en_GB-alan-medium")
PIPER_ONNX = os.path.join(ROOT, "models/piper", VOICE + ".onnx")
OLLAMA     = "http://127.0.0.1:11434/api/chat"
SR         = 16000          # openWakeWord and whisper both want 16 kHz mono
WAKE_BLOCK = 1280           # 80 ms @ 16 kHz — oWW's expected frame size


# ---- audio out --------------------------------------------------------------
# Fedora is PipeWire; aplay may be absent. Pick whatever exists, once.
DIM, OFF = "\033[2m", "\033[0m"
PLAYER = next((p for p in ("pw-play", "paplay", "aplay") if shutil.which(p)), None)

def say(text):
    text = " ".join(text.split())
    if not text:
        return
    print(f"  JARVIS: {text}")
    if PLAYER is None:
        print("  [no audio player found: install pipewire-utils or alsa-utils]")
        return
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav = tmp.name
    try:
        r = subprocess.run(["piper", "-m", PIPER_ONNX, "-f", wav],
                           input=text.encode(), capture_output=True)
        if r.returncode != 0 or not os.path.getsize(wav):
            print("  [piper failed]", r.stderr.decode()[:300]); return
        subprocess.run([PLAYER, wav], stderr=subprocess.DEVNULL)
    finally:
        os.path.exists(wav) and os.unlink(wav)

# ---- audio in ---------------------------------------------------------------
VAD_WINDOW = 512                 # 32 ms @ 16 kHz — matches EndpointerConfig.window_ms
PREROLL_WINDOWS = 8              # ~256 ms kept before speech starts, so the
                                 # first word isn't clipped off the front

def _rms(block) -> float:
    return float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))


def calibrate(vad: RmsVad, seconds: float = 0.6) -> float:
    """Measure the room once at startup so thresholds are relative, not absolute."""
    n = int(seconds * SR / VAD_WINDOW)
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        blocksize=VAD_WINDOW) as s:
        floor = vad.calibrate(_rms(s.read(VAD_WINDOW)[0]) for _ in range(n))
    return floor


def record_turn(vad: RmsVad, max_s: float = 15.0):
    """Capture one utterance, ending on the endpointer's SPEECH_END.

    Unlike a plain silence timer, a pause mid-sentence does not end the turn -
    see core/endpointing.py.
    """
    ep = Endpointer(EndpointerConfig(threshold=0.5, min_speech_ms=192,
                                     min_silence_ms=800, window_ms=32))
    preroll, frames, started = deque(maxlen=PREROLL_WINDOWS), [], False
    t0 = time.time()

    with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        blocksize=VAD_WINDOW) as stream:
        print("  listening...")
        while time.time() - t0 < max_s:
            block, _ = stream.read(VAD_WINDOW)
            event = ep.feed(vad.probability(_rms(block)))

            if started:
                frames.append(block)
            else:
                preroll.append(block)

            if event is VoiceEvent.SPEECH_START:
                started = True
                frames.extend(preroll)      # recover the clipped onset
                preroll.clear()
            elif event is VoiceEvent.SPEECH_END and started:
                break

    if not frames:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(frames).flatten()


# ---- main -------------------------------------------------------------------
def load_wake():
    """Fetch the melspec/embedding models on first run, then build the detector."""
    import openwakeword.utils as u
    if hasattr(u, "download_models"):
        try:
            u.download_models(["hey_jarvis"])
        except TypeError:
            u.download_models()
        except Exception as e:
            print("  [wake model download note]", e)
    return WakeModel(wakeword_models=["hey_jarvis"])

def build_agent() -> Agent:
    agency = Agency.parse(cfg("JARVIS_AGENCY", "advisory"))
    bus = Bus(registry=Registry.load())
    box = Toolbox(registry=build_tools(bus=bus), agency=agency)
    print(f"agency={agency.name.lower()}  "
          f"tools={[t.name for t in box.registry.available(agency)]}")
    return Agent(toolbox=box, chat=OllamaChat(CHAT_MODEL), persona=PERSONA)


def main():
    if not os.path.exists(PIPER_ONNX):
        sys.exit(f"Voice missing: {PIPER_ONNX}\n"
                 f"Run: python -m piper.download_voices {VOICE} "
                 f"--download-dir {os.path.join(ROOT,'models/piper')}")
    print("loading models...")
    wake = load_wake()
    stt  = WhisperModel("small.en", device="cpu", compute_type="int8")
    vad  = RmsVad()
    print(f"calibrating room... floor={calibrate(vad):.5f}")
    agent = build_agent()
    say("Online, sir.")

    with sd.InputStream(samplerate=SR, channels=1, dtype="int16",
                        blocksize=WAKE_BLOCK) as stream:
        print(f'ready - say "hey jarvis"   (model={CHAT_MODEL}, player={PLAYER})')
        while True:
            audio, _ = stream.read(WAKE_BLOCK)
            if max(wake.predict(audio.flatten()).values()) < 0.5:
                continue
            print("\n[woke]")
            stream.stop()
            pcm = record_turn(vad)
            stream.start()
            if pcm.size == 0:
                print("  (no speech)")
                wake.reset()
                continue

            segs, _ = stt.transcribe(pcm, language="en", beam_size=1)
            text = " ".join(s.text for s in segs).strip()
            wake.reset()
            if not text:
                continue
            print(f"  you: {text}")

            # A stop command is handled here, never sent to the model.
            if is_pause_utterance(text):
                print("  (stood down)")
                continue

            try:
                turn = agent.say(text)
            except Exception as exc:
                say("I couldn't reach the model, sir.")
                print("  ", exc)
                continue

            if turn.tools_used:
                print(f"  {DIM}tools: {', '.join(turn.tools_used)}{OFF}")
            say(turn.text)
            # If that was a question, the next utterance answers it: keep the
            # mic open instead of making the user say the wake word again.
            while turn.awaiting_confirmation:
                pcm = record_turn(vad, max_s=8.0)
                if pcm.size == 0:
                    say("I'll leave it, sir.")
                    agent.toolbox.decline(agent.pending.id)
                    agent.pending = None
                    break
                segs, _ = stt.transcribe(pcm, language="en", beam_size=1)
                answer = " ".join(s.text for s in segs).strip()
                if not answer:
                    continue
                print(f"  you: {answer}")
                turn = agent.say(answer)
                say(turn.text)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nshutting down.")
