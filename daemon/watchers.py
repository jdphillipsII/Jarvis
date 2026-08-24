"""Watchers for this machine.

Each is split in two: a PURE parser over already-captured text, and a thin IO
shim that captures it. The parsers carry all the judgment and are tested with
recorded fixtures; the shims are three lines each and untested by design.

`key` on every Observation must be STABLE across ticks — cooldowns hash on it,
so embedding a changing temperature would defeat the cooldown entirely.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import List, Optional

from core.observation import Observation
from core.policy import Urgency
from core.sources import source

# ---- GPU -------------------------------------------------------------------
GPU_WARN_C, GPU_CRIT_C = 85.0, 95.0
VRAM_WARN_PCT = 92.0


def parse_rocm_smi(payload: str) -> List[Observation]:
    """Parse `rocm-smi --showtemp --showmemuse --json`.

    Note: 'low-power state' warnings in rocm-smi output are benign idle
    downclocking and are deliberately ignored.
    """
    out: List[Observation] = []
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return out

    for card, fields in (data or {}).items():
        if not isinstance(fields, dict):
            continue
        temp = _first_float(fields, ("Temperature (Sensor edge) (C)",
                                     "Temperature (Sensor junction) (C)"))
        if temp is not None:
            if temp >= GPU_CRIT_C:
                out.append(Observation(
                    f"The GPU is at {temp:.0f} degrees, sir. That's past thermal limits.",
                    Urgency.CRITICAL, "gpu", f"{card}:temp-critical", {"celsius": temp}))
            elif temp >= GPU_WARN_C:
                out.append(Observation(
                    f"GPU's running warm, sir - {temp:.0f} degrees.",
                    Urgency.WARN, "gpu", f"{card}:temp-high", {"celsius": temp}))

        used, total = fields.get("VRAM Total Used Memory (B)"), fields.get("VRAM Total Memory (B)")
        try:
            pct = 100.0 * int(used) / int(total)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if pct >= VRAM_WARN_PCT:
            out.append(Observation(
                f"VRAM is {pct:.0f} percent full, sir. A larger model won't fit.",
                Urgency.WARN, "gpu", f"{card}:vram-high", {"percent": pct}))
    return out


def _first_float(fields: dict, keys) -> Optional[float]:
    for k in keys:
        if k in fields:
            try:
                return float(fields[k])
            except (TypeError, ValueError):
                pass
    return None


# ---- disk ------------------------------------------------------------------
DISK_WARN_PCT, DISK_CRIT_PCT = 90.0, 96.0


def check_disk_usage(path: str = "/home", *, _usage=None) -> List[Observation]:
    total, used, free = _usage or shutil.disk_usage(path)
    pct = 100.0 * used / total if total else 0.0
    gb = free / 1e9
    if pct >= DISK_CRIT_PCT:
        return [Observation(
            f"Disk is {pct:.0f} percent full, sir - {gb:.1f} gigabytes left.",
            Urgency.CRITICAL, "disk", f"{path}:critical", {"percent": pct, "free_gb": gb})]
    if pct >= DISK_WARN_PCT:
        return [Observation(
            f"Storage is getting tight, sir - {gb:.0f} gigabytes free.",
            Urgency.WARN, "disk", f"{path}:low", {"percent": pct, "free_gb": gb})]
    return []


# ---- systemd ---------------------------------------------------------------
def parse_failed_units(payload: str) -> List[Observation]:
    """Parse `systemctl --failed --no-legend --plain`."""
    units = [line.split()[0] for line in (payload or "").splitlines()
             if line.strip() and not line.startswith(" ")]
    units = [u for u in units if u.endswith((".service", ".timer", ".mount", ".socket"))]
    if not units:
        return []
    if len(units) == 1:
        text = f"{units[0]} has failed, sir."
    else:
        text = f"{len(units)} units have failed, sir - including {units[0]}."
    return [Observation(text, Urgency.WARN, "systemd",
                        "failed:" + ",".join(sorted(units)), {"units": units})]


# ---- IO shims (registered watchers) ----------------------------------------
def _run(cmd: List[str], timeout: float = 3.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


@source("gpu", interval_s=30.0, timeout_s=4.0)
def watch_gpu() -> List[Observation]:
    return parse_rocm_smi(_run(["rocm-smi", "--showtemp", "--showmemuse", "--json"]))


@source("disk", interval_s=600.0)
def watch_disk() -> List[Observation]:
    return check_disk_usage("/home")


@source("systemd", interval_s=120.0)
def watch_systemd() -> List[Observation]:
    return parse_failed_units(_run(["systemctl", "--failed", "--no-legend", "--plain"]))
