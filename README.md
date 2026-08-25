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

## HUD

    ./cli.py watch      # daemon + HUD on http://127.0.0.1:8787
    ./cli.py hud        # open it

### Visual language

Light drawn on black, never paint on a surface. Nothing has a fill; framing is
corner brackets, never a box. Every stroke is drawn three times in pure R/G/B
offset by sub-pixels and composited additively, so crossings brighten and edges
carry a faint prism — that is what makes it read as projected rather than
rendered. Three depth planes, the far one counter-rotating. Rotation rates are
deliberately incommensurate (0.18 / -0.31 / 0.07 rad/s) so the pattern never
visibly repeats.

Type departs from the repo-wide system on this one surface: Chakra Petch and
Saira 100 replace Fraunces, which is a warm editorial serif and fights
everything here. Amber and red are alarm only, never decoration; the brightest
pixel on screen is near-white, with the hue living in the falloff.

Everything obeys `prefers-reduced-motion` — and the composition still has to
hold when all of it stops, so nothing depends on motion to be legible.

Operational state drives the whole visual language and is derived in exactly
one place (`core/hud_state.py`). Precedence is deliberate:

| state | when | ring |
|---|---|---|
| `critical` | a critical offer is pending | red, fast pulse |
| `focused` | deep work — quiet even with noise pending | dim, slowest |
| `elevated` | something is waiting | amber |
| `calm` | nothing to say | cyan, slow tide |

CRITICAL outranks FOCUSED because the one thing allowed to break flow is the
thing that costs more to miss. FOCUSED outranks ELEVATED because a warning you
have already deferred should not keep the room amber while you work.

Only answerable offers change the state; a badge is just a mark in the feed.
The page falls back to a self-running demo when no daemon is attached, so the
design can be reviewed anywhere.

## Gestures

    python vision/gesture_daemon.py --dry-run --preview

| gesture | intent |
|---|---|
| open palm | `window.dismiss` |
| fist | `mic.mute` |
| point | `window.focus` |
| two fingers | `workspace.next` |
| pinch + move | `model.orbit` (continuous) |

Everything is normalised against hand span, so a hand at arm's length and a
hand near the lens classify identically and produce the same drag deltas.
Pinch bypasses the debouncer — it is a continuous drag, not a one-shot — and
holding still publishes nothing rather than spraying zero-deltas.

An unrecognised pose returns `None` rather than a guess, which breaks the
debouncer's streak; guessing would fire an action.

## Presence

    # needs: uv pip install opencv-python mediapipe   (in a 3.11 venv)
    python vision/presence_daemon.py --dry-run        # prints transitions
    JARVIS_CAM=http://PHONE_IP:8080/video python vision/presence_daemon.py

## Quick start

    git clone https://github.com/jdphillipsII/Jarvis.git ~/jarvis
    cd ~/jarvis
    bash setup/install.sh            # venv, deps, models, then runs the tests

    source .venvs/voice/bin/activate
    ./cli.py doctor                  # checks every prerequisite, names the fix
    ./cli.py chat                    # text mode, full tool loop, no mic needed

Options: `--no-vision` skips opencv/mediapipe (~500 MB), `--core-only` installs
just enough to run the test suite. The script is idempotent — re-run it freely.

## The `jarvis` command

| command | what it does |
|---|---|
| `doctor` | check every prerequisite and print the exact fix for each |
| `status` | GPU temperature, disk, load |
| `tools` | what JARVIS can do at the current agency, and how many are hidden above it |
| `chat` | text-mode conversation with the full tool loop — no mic needed |
| `listen` | the voice loop |
| `presence` | the camera presence daemon |
| `gestures` | the camera gesture daemon |
| `watch` | the proactive daemon (also serves the HUD) |
| `hud` | open the HUD in a browser |
| `up` | all three |
| `install` | write systemd user units so it starts with your session |

## Tools

Three gates before anything runs: **agency** (a tool above the configured
level is never shown to the model, so it cannot ask for what it cannot see),
**schema** (arguments validated before the handler is entered), and **consent**
(anything mutating returns a proposal; the user confirms).

Agency is set by `JARVIS_AGENCY` in `config/jarvis.env` and is the user's to
raise. An unrecognised value fails closed to `advisory`.

### Tool calls in conversation

    you> how's the GPU?
      tools: system.status
    JARVIS> Sixty-one degrees, sir. Nothing to worry about.

    you> note that I should order the camera mount
      tools: notes.append
    JARVIS> Append a line to the notes file (text='order the camera mount'). Shall I, sir?
    you> yes
    JARVIS> noted: order the camera mount

Mutating tools never run inside the loop — they return a proposal and JARVIS
asks. Only a bare yes counts: "yes but call it something else" is a new
request, not consent. Moving on to another subject cancels the offer, so a
later unrelated "yes" cannot fire it.

Tool errors are fed back to the model rather than raised, so a wrong argument
becomes something it corrects on the next round instead of a dead end.

## Build order

- [x] **0** Fedora install
- [x] **1** ROCm gate — `gfx1100` visible, Ollama generating on GPU
- [x] **2** Voice loop — wake → whisper → Ollama → Piper (Alan)
- [x] **3** Presence detection — greet on arrival, hush when away
- [x] **4** Proactive daemon — GPU / disk / systemd watchers, judged by policy
- [x] **5a** HUD — arc-reactor state ring, offers you can answer, live telemetry
- [ ] **5b** Plasma layer — Activities (COMMAND / WORKSHOP / FORGE), Karousel
- [x] **6** Gestures — camera → MediaPipe → intents

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
