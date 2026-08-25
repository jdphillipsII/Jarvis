#!/usr/bin/env bash
# One-shot setup. Safe to re-run — every step checks before doing.
#
#   bash setup/install.sh              # everything
#   bash setup/install.sh --no-vision  # skip opencv/mediapipe (~500 MB)
#   bash setup/install.sh --core-only  # just enough to run the test suite
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

C='\033[36m'; G='\033[32m'; Y='\033[33m'; O='\033[0m'
say()  { printf "${C}==>${O} %s\n" "$*"; }
ok()   { printf "  ${G}ok${O}   %s\n" "$*"; }
warn() { printf "  ${Y}note${O} %s\n" "$*"; }

VISION=1; CORE_ONLY=0
for a in "$@"; do
  case "$a" in
    --no-vision) VISION=0 ;;
    --core-only) CORE_ONLY=1; VISION=0 ;;
    *) echo "unknown option: $a"; exit 1 ;;
  esac
done

# ---- 1. system packages -----------------------------------------------------
if [[ $CORE_ONLY -eq 0 ]]; then
  say "system packages"
  # portaudio: microphone capture.  pipewire-utils: pw-play for audio out.
  # Fedora is PipeWire, so aplay (alsa-utils) may be absent entirely.
  missing=()
  for p in portaudio portaudio-devel pipewire-utils; do
    rpm -q "$p" >/dev/null 2>&1 || missing+=("$p")
  done
  if ((${#missing[@]})); then
    say "installing: ${missing[*]}"
    sudo dnf install -y "${missing[@]}"
  else
    ok "already present"
  fi
fi

# ---- 2. uv ------------------------------------------------------------------
if ! command -v uv >/dev/null; then
  say "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  ok "uv present"
fi

# ---- 3. venv on 3.11 --------------------------------------------------------
# 3.11 ON PURPOSE. On 3.12+ tflite-runtime has no wheel, so pip silently falls
# back to openwakeword 0.4.x whose API is incompatible — an hour lost the first
# time. mediapipe wheels lag new Python too.
say "python 3.11 venv"
if [[ ! -d .venvs/voice ]]; then
  uv python install 3.11 2>/dev/null || true
  uv venv --python 3.11 .venvs/voice
  ok "created .venvs/voice"
else
  ok ".venvs/voice exists"
fi
# shellcheck disable=SC1091
source .venvs/voice/bin/activate
python -c "import sys; assert sys.version_info[:2]==(3,11), f'wrong python: {sys.version}'" \
  || { echo "venv is not 3.11 — delete .venvs/voice and re-run"; exit 1; }

# ---- 4. python packages -----------------------------------------------------
say "core + test deps"
uv pip install -q -r requirements-dev.txt numpy requests
ok "pyyaml pytest numpy requests"

if [[ $CORE_ONLY -eq 0 ]]; then
  say "voice deps"
  uv pip install -q openwakeword faster-whisper piper-tts sounddevice
  ok "openwakeword faster-whisper piper-tts sounddevice"
fi

if [[ $VISION -eq 1 ]]; then
  say "vision deps (~500 MB)"
  uv pip install -q opencv-python mediapipe
  ok "opencv-python mediapipe"
fi

# ---- 5. models --------------------------------------------------------------
if [[ $CORE_ONLY -eq 0 ]]; then
  say "voice model"
  VOICE="$(sed -n 's/^JARVIS_VOICE=//p' config/jarvis.env | tr -d ' ')"
  VOICE="${VOICE:-en_GB-alan-medium}"
  mkdir -p models/piper
  if [[ -s "models/piper/${VOICE}.onnx" ]]; then
    ok "${VOICE} already downloaded"
  else
    # Never curl these from Hugging Face — redirects fail silently and leave an
    # empty models/piper. Piper's own downloader gets the .onnx + .json pair.
    python -m piper.download_voices "$VOICE" --download-dir models/piper
    ok "downloaded ${VOICE}"
  fi
fi

# ---- 6. verify --------------------------------------------------------------
say "running the test suite"
if python -m pytest -q; then
  ok "tests pass"
else
  echo "tests failed — paste the output"; exit 1
fi

chmod +x cli.py scripts/*.sh setup/*.sh 2>/dev/null || true

printf "\n${G}done.${O}  next:\n"
printf "    source .venvs/voice/bin/activate\n"
printf "    ./cli.py doctor      # checks GPU, ollama, audio; names every fix\n"
printf "    ./cli.py chat        # talk to it in text, full tool loop\n"
printf "    ./cli.py listen      # voice\n"
printf "    ./cli.py watch       # proactive daemon + HUD on :8787\n"
