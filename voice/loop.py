#!/usr/bin/env python3
"""JARVIS voice loop — wake -> listen -> think -> speak.

    "hey jarvis"  -> openWakeWord fires
                  -> record until you stop talking (silence endpointing)
                  -> faster-whisper transcribes (CPU; the 12900K eats it)
                  -> Ollama replies in the JARVIS persona
                  -> Piper speaks it as Alan

Run:  source .venvs/voice/bin/activate && python voice/loop.py
"""
import os, sys, time, queue, shutil, subprocess, tempfile
import numpy as np, sounddevice as sd, requests
from openwakeword.model import Model as WakeModel
from faster_whisper import WhisperModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def cfg(key, default):
    """Read config/jarvis.env without extra deps."""
    path = os.path.join(ROOT, "config/jarvis.env")
    if os.path.exists(path):
        for line in open(path):
            line = line.split("#", 1)[0].strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return default

CHAT_MODEL = cfg("JARVIS_CHAT_MODEL", "qwen2.5:7b")
VOICE      = cfg("JARVIS_VOICE", "en_GB-alan-medium")
PIPER_ONNX = os.path.join(ROOT, "models/piper", VOICE + ".onnx")
OLLAMA     = "http://127.0.0.1:11434/api/chat"
SR         = 16000          # openWakeWord and whisper both want 16 kHz mono
WAKE_BLOCK = 1280           # 80 ms @ 16 kHz — oWW's expected frame size

PERSONA = (
    "You are JARVIS, a dry, clipped British AI assistant. Address the user as 'sir'. "
    "Be concise - one or two sentences unless asked to expand. Mild wit, never chirpy, "
    "never say you are an AI or a language model. If you don't know, say so plainly."
)

# ---- audio out --------------------------------------------------------------
# Fedora is PipeWire; aplay may be absent. Pick whatever exists, once.
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
def record_until_silence(max_s=12, silence_s=1.0, thresh=0.010):
    """Capture mono 16k until ~1s of quiet, or max_s. Returns float32 [-1,1]."""
    q, chunks, quiet_for, t0 = queue.Queue(), [], 0.0, time.time()
    block = int(SR * 0.05)   # 50 ms
    def cb(indata, frames, tinfo, status): q.put(indata.copy())
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        blocksize=block, callback=cb):
        print("  listening...")
        while time.time() - t0 < max_s:
            buf = q.get()
            chunks.append(buf)
            rms = float(np.sqrt(np.mean(buf ** 2)))
            quiet_for = quiet_for + 0.05 if rms < thresh else 0.0
            if quiet_for >= silence_s and len(chunks) > 10:
                break
    return np.concatenate(chunks).flatten()

# ---- think ------------------------------------------------------------------
def think(user_text, history):
    msgs = ([{"role": "system", "content": PERSONA}] + history +
            [{"role": "user", "content": user_text}])
    r = requests.post(OLLAMA, json={"model": CHAT_MODEL, "messages": msgs,
                                    "stream": False}, timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]

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

def main():
    if not os.path.exists(PIPER_ONNX):
        sys.exit(f"Voice missing: {PIPER_ONNX}\n"
                 f"Run: python -m piper.download_voices {VOICE} "
                 f"--download-dir {os.path.join(ROOT,'models/piper')}")
    print("loading models...")
    wake = load_wake()
    stt  = WhisperModel("small.en", device="cpu", compute_type="int8")
    history = []
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
            pcm = record_until_silence()
            stream.start()
            wake.reset()

            segs, _ = stt.transcribe(pcm, language="en", beam_size=1)
            text = " ".join(s.text for s in segs).strip()
            if not text:
                continue
            print(f"  you: {text}")
            try:
                reply = think(text, history[-6:])
            except Exception as e:
                say("I couldn't reach the model, sir."); print("  ", e); continue
            say(reply)
            history += [{"role": "user", "content": text},
                        {"role": "assistant", "content": reply}]

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nshutting down.")
