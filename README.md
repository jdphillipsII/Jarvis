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

    ./cli.py gestures --dry-run --preview

### Using a phone as the camera

Any MJPEG source works — `JARVIS_CAM` accepts a URL as readily as a device
index, so no v4l2loopback and no kernel module:

    # config/jarvis.env
    JARVIS_CAM=http://192.168.1.42:8080/video

Android: install **IP Webcam**, set 640x480, and **lock focus and exposure** —
autofocus hunting is the single biggest cause of unstable landmarks. Over USB
instead of wifi (`adb forward tcp:8080 tcp:8080`, then `http://localhost:8080/video`)
latency drops from ~150 ms to ~60 ms.

Environment always overrides the file, so a single run can ignore it:

    JARVIS_CAM=0 ./cli.py gestures --preview

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

Your settings live in `config/jarvis.env`, which is gitignored and created from
`config/jarvis.env.example` on first install. Edits there survive every pull.

## The `jarvis` command

| command | what it does |
|---|---|
| `doctor` | check every prerequisite and print the exact fix for each |
| `status` | GPU temperature, disk, load |
| `tools` | what JARVIS can do at the current agency, and how many are hidden above it |
| `chat` | text-mode conversation with the full tool loop — no mic needed |
| `bench` | score models on tool choice, arguments, persona and speed |
| `mcp` | serve the toolbox over MCP on stdio |
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

### Choosing a model

    ./cli.py bench qwen3.6:27b hermes4:14b mistral-small:24b

Public benchmarks predict very little about the thing that matters here. This
runs a fixed suite against your real toolbox and reports what does:

| column | meaning |
|---|---|
| `tool` | picked the right tool — **including correctly picking none** |
| `args` | arguments survived schema validation and matched the case |
| `persona` | stayed in character on turns that produced speech |
| `mean` / `worst` | latency, which you feel on every voice turn |

Three of the ten cases expect *no* tool call, because over-eagerly reaching for
one is as wrong as picking the wrong one. Nothing is executed: notes go to a
scratch file, no bus is attached, and mutating tools stop at a proposal that is
never confirmed.

## MCP — sharing the toolbox

    ./cli.py mcp        # stdio JSON-RPC; wire into any MCP client

JARVIS's tools — desktop control, workshop, notes, telemetry, escalation — are
publishable over MCP, which is what Hermes Agent, Claude Desktop and most other
agents already speak. Register it as a stdio server:

```json
{
  "mcpServers": {
    "jarvis": { "command": "/home/you/jarvis/cli.py", "args": ["mcp"] }
  }
}
```

**The consent model survives the crossing.** A mutating tool called over MCP
does not execute — it returns a proposal and an id, and a separate
`jarvis_confirm` call runs it. An external agent cannot do anything
irreversible without a second, deliberate act. Tools above the configured
agency are not listed, and calling one is made indistinguishable from calling a
tool that does not exist.

### Two tiers

The fast model answers and routes; when a question genuinely exceeds it, it
escalates by calling `reason.deeply`. Making that a **tool** rather than a
heuristic means the model that actually read the question decides, instead of
a keyword list guessing from outside — and it makes escalation measurable:
`bench` scores both reaching for the slow model when a question deserves it and
resisting when it doesn't.

    JARVIS_CHAT_MODEL=qwen2.5:7b      # routes and answers
    JARVIS_HEAVY_MODEL=qwen2.5:32b    # thinks; leave empty to disable

The heavy model is given **no tools**. It reasons, it does not act — every side
effect stays on the fast path where the consent gate lives. A heavy model that
is unreachable degrades to an error the fast model can recover from, not a
broken turn.

### Reasoning models

Hybrid-reasoning models emit deliberation as `<think>...</think>` and sometimes
tool calls as `<tool_call>{...}</tool_call>` text rather than in the API's
structured field. Both are fine in a chat window and wrong for a voice
assistant — unstripped reasoning gets read aloud, and a tool call the transport
never surfaced never runs.

`core/reasoning.py` normalises any such model to behave like a plain one. The
structured field always wins, so a model that does it properly is untouched.
Swapping models is a one-line config change.

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
