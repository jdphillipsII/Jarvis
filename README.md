# JARVIS

A local-first intelligence layer for Fedora KDE. No cloud, no API keys — wake
word, speech, reasoning and voice all run on the machine.

**Target box:** RX 7900 XTX (gfx1100, 24 GB) + i9-12900K, Fedora 44, KDE Plasma 6.

## Architecture — one bus, many mouths

Every input publishes a normalised **intent**. Every actuator subscribes.
Nothing talks to the compositor directly.

    camera → vision/   ┐
    mic    → voice/    ├──→  intent bus  ──→  KWin script (windows / activities)
    system → daemon/   ┘         │        ──→  workshop drivers (FreeCAD / Blender)
    presence ────────────────────┘        ──→  voice out (Piper)

Contract: `intents/CONTRACT.md` · allowlist: `intents/registry.yaml`

## Presence

    # needs: uv pip install opencv-python mediapipe   (in a 3.11 venv)
    python vision/presence_daemon.py --dry-run        # prints transitions
    JARVIS_CAM=http://PHONE_IP:8080/video python vision/presence_daemon.py

## Quick start

    bash setup/voice-setup.sh        # venv + wake model + Alan voice
    source .venvs/voice/bin/activate
    ./cli.py doctor                  # checks every prerequisite, names the fix
    ./cli.py up                      # voice + presence + watchers

## The `jarvis` command

| command | what it does |
|---|---|
| `doctor` | check every prerequisite and print the exact fix for each |
| `status` | GPU temperature, disk, load |
| `tools` | what JARVIS can do at the current agency, and how many are hidden above it |
| `listen` | the voice loop |
| `presence` | the camera presence daemon |
| `watch` | the proactive daemon |
| `up` | all three |
| `install` | write systemd user units so it starts with your session |

## Tools

Three gates before anything runs: **agency** (a tool above the configured
level is never shown to the model, so it cannot ask for what it cannot see),
**schema** (arguments validated before the handler is entered), and **consent**
(anything mutating returns a proposal; the user confirms).

Agency is set by `JARVIS_AGENCY` in `config/jarvis.env` and is the user's to
raise. An unrecognised value fails closed to `advisory`.

## Build order

- [x] **0** Fedora install
- [x] **1** ROCm gate — `gfx1100` visible, Ollama generating on GPU
- [x] **2** Voice loop — wake → whisper → Ollama → Piper (Alan)
- [x] **3** Presence detection — greet on arrival, hush when away
- [x] **4** Proactive daemon — GPU / disk / systemd watchers, judged by policy
- [ ] **5** Plasma layer — Activities (COMMAND / WORKSHOP / FORGE), Karousel, HUD
- [ ] **6** Gestures — camera → MediaPipe → intents

## Agency level

Set `JARVIS_AGENCY` in `config/jarvis.env`:

| value | meaning |
|---|---|
| `advisory` | talks and shows; no write access |
| `actuator` | desktop + workshop control via the intent allowlist ← **current** |
| `agentic`  | arbitrary shell/file access (needs sandbox + confirm loop) |

## Hard-won notes

- **Python 3.11, not 3.12.** On 3.12 `tflite-runtime` has no wheel, so pip
  silently installs openWakeWord 0.4.x whose API is incompatible.
- **Never `curl` Piper voices from Hugging Face.** Redirects fail silently and
  leave an empty `models/piper`. Use `python -m piper.download_voices`.
- **Fedora is PipeWire.** `aplay` may not exist; `loop.py` picks whichever of
  `pw-play` / `paplay` / `aplay` is present.
- **`rocm-smi` "low-power state" is benign** — idle downclock, not a fault.
- Whisper runs on **CPU on purpose**, keeping all 24 GB of VRAM for the model.
