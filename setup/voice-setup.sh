#!/usr/bin/env bash
# Builds the voice venv and pulls the wake + TTS models. Idempotent.
# Usage:  bash setup/voice-setup.sh     (run from the repo root)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
say() { printf '\033[36m[voice-setup]\033[0m %s\n' "$*"; }

# ---- system deps ------------------------------------------------------------
# portaudio: mic capture.  pipewire-utils: pw-play for audio out.
say "system packages"
sudo dnf install -y portaudio portaudio-devel pipewire-utils || true

# ---- python venv ------------------------------------------------------------
# 3.11 ON PURPOSE. On 3.12 pip silently falls back to openwakeword 0.4.x
# (no download_models, path-only API) because tflite-runtime has no 3.12 wheel.
if ! command -v uv >/dev/null; then
  say "installing uv"; curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv python install 3.11 2>/dev/null || true
[[ -d .venvs/voice ]] || uv venv --python 3.11 .venvs/voice
# shellcheck disable=SC1091
source .venvs/voice/bin/activate

say "python deps"
uv pip install -q openwakeword faster-whisper piper-tts sounddevice numpy requests

# ---- models -----------------------------------------------------------------
# Use piper's own downloader. A raw curl to huggingface fails silently on
# redirects and leaves an EMPTY models/piper dir -- that cost us an hour once.
VOICE_NAME="$(sed -n 's/^JARVIS_VOICE=//p' config/jarvis.env | tr -d ' ')"
VOICE_NAME="${VOICE_NAME:-en_GB-alan-medium}"
mkdir -p models/piper
if [[ ! -s "models/piper/${VOICE_NAME}.onnx" ]]; then
  say "downloading voice ${VOICE_NAME}"
  python -m piper.download_voices "$VOICE_NAME" --download-dir models/piper
fi
ls -la models/piper

say "done.  test:  source .venvs/voice/bin/activate && python voice/loop.py"
