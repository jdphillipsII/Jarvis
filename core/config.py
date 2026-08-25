"""Config lookup, one place.

Precedence: environment variable, then config/jarvis.env, then the default.
Env first so a single run can be overridden without editing the file:

    JARVIS_CAM=0 ./cli.py gestures      # ignore the configured phone, use the webcam
"""
from __future__ import annotations

import os
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "jarvis.env")


def cfg(key: str, default: str = "", path: Optional[str] = None) -> str:
    env = os.environ.get(key)
    if env:
        return env
    p = path or CONFIG_PATH
    if os.path.exists(p):
        for line in open(p):
            line = line.split("#", 1)[0].strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default
