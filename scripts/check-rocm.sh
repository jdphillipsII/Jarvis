#!/usr/bin/env bash
# Gate: does ROCm see the 7900 XTX, and can a model run on it?
set -uo pipefail
c() { printf '\033[36m>>> %s\033[0m\n' "$*"; }
fail=0

c "groups (need video + render)"
groups | tr ' ' '\n' | grep -E '^(video|render)$' || {
  echo "MISSING - run: sudo usermod -aG video,render \$USER   then reboot"; fail=1; }

c "rocminfo - looking for gfx1100"
if command -v rocminfo >/dev/null; then
  rocminfo 2>/dev/null | grep -E 'gfx[0-9]+' | head || { echo "no gfx line"; fail=1; }
else
  echo "not installed - sudo dnf install -y rocminfo rocm-smi"; fail=1
fi

c "ollama"
command -v ollama >/dev/null && ollama --version || \
  echo "not installed - curl -fsSL https://ollama.com/install.sh | sh"

echo
# NOTE: "AMD GPU device(s) is/are in a low-power state" from rocm-smi is BENIGN.
# The card downclocks when idle and spins up under load. Ignore it.
[[ $fail -eq 0 ]] \
  && echo "GATE OK - now: ollama run qwen2.5:7b 'hello'  (watch rocm-smi in another terminal)" \
  || echo "GATE BLOCKED - fix the above, re-run."
