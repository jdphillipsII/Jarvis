"""The tools JARVIS ships with.

Each declares the lowest agency that permits it. Nothing here reaches above
ACTUATOR except shell.run, which exists mainly to make the ceiling visible:
at the default agency the model is never told it exists.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.bus import Bus
from core.intent import Intent
from core.tools import Agency, Tool, ToolRegistry

ACTIVITIES = ["COMMAND", "WORKSHOP", "FORGE"]


def build(bus: Optional[Bus] = None, briefing=None,
          notes_path: str = "~/jarvis-notes.md",
          heavy_chat=None) -> ToolRegistry:
    reg = ToolRegistry()
    notes = os.path.expanduser(notes_path)

    # Escalation, when a heavy model is configured. Registered first so it sits
    # at the top of the catalogue the fast model reads.
    if heavy_chat is not None:
        from core.escalation import deep_thought_tool
        reg.add(deep_thought_tool(heavy_chat))

    # ---- ADVISORY: read and report ----
    def system_status() -> Dict[str, Any]:
        total, used, free = shutil.disk_usage(os.path.expanduser("~"))
        out: Dict[str, Any] = {"disk_free_gb": round(free / 1e9, 1),
                               "disk_used_pct": round(100 * used / total, 1)}
        try:
            with open("/proc/loadavg") as fh:
                out["load_1m"] = float(fh.read().split()[0])
        except OSError:
            pass
        try:
            temps = subprocess.run(["rocm-smi", "--showtemp", "--json"],
                                   capture_output=True, text=True, timeout=3).stdout
            import json
            for fields in (json.loads(temps) or {}).values():
                if isinstance(fields, dict):
                    for k, v in fields.items():
                        if "Temperature" in k:
                            out["gpu_temp_c"] = float(v)
                            break
        except Exception:
            pass
        return out

    reg.add(Tool("system.status", "Report GPU temperature, disk space and load.",
                 system_status))

    def unit_convert(value: str, to: str) -> str:
        from core.units import convert
        return str(convert(value, to))

    reg.add(Tool("units.convert",
                 "Convert a physical quantity between units. Handles offset "
                 "units correctly (20 degC is 293.15 K, not 20 K) and refuses "
                 "conversions between incompatible dimensions.",
                 unit_convert,
                 parameters={"value": {"type": "quantity",
                                       "description": "the quantity to convert"},
                             "to": {"type": "string",
                                    "description": "target unit, e.g. 'K', 'mm', 'psi'"}},
                 required=("value", "to")))

    def read_briefing() -> str:
        return briefing.summary() if briefing else "Nothing held, sir."

    reg.add(Tool("briefing.read",
                 "Report anything held while the user was away or busy.",
                 read_briefing))

    reg.add(Tool("notes.read", "Read back the most recent notes.",
                 lambda count=10: _tail(notes, int(count)),
                 parameters={"count": {"type": "integer",
                                       "description": "how many lines"}}))

    # ---- ACTUATOR: drive the desktop ----
    def publish(intent_name: str, **args) -> str:
        # NB: first parameter is deliberately not called `name` — several
        # intents carry a `name` argument of their own and would collide.
        if bus is None:
            return "no bus attached"
        bus.publish(Intent(intent_name, source="voice", confidence=1.0, args=args))
        return "done"

    reg.add(Tool("workspace.activity",
                 "Switch the desktop to a named Activity.",
                 lambda name: publish("workspace.activity", name=name),
                 parameters={"name": {"type": "string", "enum": ACTIVITIES}},
                 required=("name",), min_agency=Agency.ACTUATOR, mutates=True,
                 confirm_label="Switch"))

    reg.add(Tool("notes.append", "Append a line to the notes file.",
                 lambda text: _append(notes, text),
                 parameters={"text": {"type": "string"}}, required=("text",),
                 min_agency=Agency.ACTUATOR, mutates=True, confirm_label="Write"))

    # ---- AGENTIC: only visible when the user has raised the ceiling ----
    reg.add(Tool("shell.run", "Run a shell command and return its output.",
                 _shell,
                 parameters={"cmd": {"type": "string"}}, required=("cmd",),
                 min_agency=Agency.AGENTIC, mutates=True, confirm_label="Execute",
                 risk="arbitrary command execution"))
    return reg


def _append(path: str, text: str) -> str:
    with open(path, "a") as fh:
        fh.write(text.rstrip() + "\n")
    return f"noted: {text.strip()}"


def _tail(path: str, count: int) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [ln.rstrip() for ln in fh.readlines()[-max(1, count):]]


def _shell(cmd: str) -> str:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return (r.stdout or r.stderr or "").strip()[:4000]
