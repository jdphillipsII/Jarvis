"""The tools JARVIS ships with.

Each declares the lowest agency that permits it. Nothing here reaches above
ACTUATOR except shell.run, which exists mainly to make the ceiling visible:
at the default agency the model is never told it exists.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.bus import Bus
from core.intent import Intent
from core.tools import Agency, Tool, ToolRegistry

log = logging.getLogger("jarvis.toolbox.builtin")

ACTIVITIES = ["COMMAND", "WORKSHOP", "FORGE"]


def build(bus: Optional[Bus] = None, briefing=None,
          notes_path: str = "~/jarvis-notes.md",
          heavy_chat=None, bridges: bool = True) -> ToolRegistry:
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

    # Real fluid properties, when CoolProp is present. Registered only if it
    # imports — the model should not be offered a tool it cannot run.
    from core import fluids
    if fluids.available():
        reg.add(Tool(
            "fluid.state",
            "Real thermophysical properties of a fluid at a pressure and "
            "temperature: density, cp, viscosity, conductivity, Prandtl, "
            "enthalpy. Use this rather than ideal-gas values near the critical "
            "point, where they differ by more than an order of magnitude.",
            lambda fluid, pressure, temperature: fluids.state(
                fluid, pressure, temperature).as_dict(),
            parameters={
                "fluid": {"type": "string",
                          "description": "e.g. CO2, Water, Nitrogen, R134a"},
                "pressure": {"type": "quantity", "dimension": "pressure"},
                "temperature": {"type": "quantity", "dimension": "temperature"}},
            required=("fluid", "pressure", "temperature")))

        reg.add(Tool(
            "fluid.pseudocritical",
            "The temperature where specific heat peaks at a given pressure "
            "(the Widom line). Above the critical pressure there is no phase "
            "change, but cp still has a sharp maximum — this is the "
            "temperature a near-critical loop is designed around.",
            lambda fluid, pressure: str(
                fluids.pseudocritical_temperature(fluid, pressure)),
            parameters={
                "fluid": {"type": "string"},
                "pressure": {"type": "quantity", "dimension": "pressure"}},
            required=("fluid", "pressure")))

        reg.add(Tool(
            "fluid.critical",
            "Critical temperature and pressure of a fluid.",
            lambda fluid: {
                "T_crit": f"{fluids.critical(fluid)['T_crit_k'] - 273.15:.4g} degC",
                "P_crit": f"{fluids.critical(fluid)['P_crit_pa'] / 1e5:.4g} bar"},
            parameters={"fluid": {"type": "string"}}, required=("fluid",)))

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

    # ---- the archetype library: retrieve and adapt, or say nothing fits ----
    from core import archetypes as _arch
    library = _arch.Library.load()
    if len(library):
        def list_archetypes() -> List[Dict[str, Any]]:
            return [{"id": a.id, "summary": a.summary.strip(), "status": a.status,
                     "parameters": [p.name for p in a.parameters],
                     "analyses": list(a.analyses)} for a in library]

        reg.add(Tool(
            "design.archetypes",
            "List the proven designs in the archetype library. Start here for "
            "any 'design me a ...' request: adapting a design that has been "
            "evaluated beats generating one that has not.",
            list_archetypes))

        def describe(archetype_id: str) -> Dict[str, Any]:
            a = library.get(archetype_id)
            if a is None:
                raise KeyError(f"no archetype '{archetype_id}'")
            return {
                "id": a.id, "summary": a.summary.strip(), "intent": a.intent,
                "status": a.status, "evidence": a.evidence.strip(),
                "provenance": a.provenance.strip(),
                "parameters": [{"name": p.name, "unit": p.unit,
                                "default": p.default, "bounds": p.bounds,
                                "description": p.description} for p in a.parameters],
                "applies_when": [{"condition": c.describe(), "why": c.why.strip()}
                                 for c in a.applicability],
                "failure_modes": [{"name": f.name,
                                   "description": f.description.strip(),
                                   "detected_by": f.detected_by,
                                   "mitigated_by": f.mitigated_by}
                                  for f in a.failure_modes],
                "analyses": list(a.analyses)}

        reg.add(Tool(
            "design.archetype",
            "Everything known about one archetype: its parameters, the "
            "conditions under which it applies, how it is known to fail, and "
            "what backs it. Read the failure modes before proposing it.",
            describe,
            parameters={"archetype_id": {"type": "string"}},
            required=("archetype_id",)))

        def choose(problem: Dict[str, Any]) -> Dict[str, Any]:
            chosen = _arch.select(library, problem)
            return {"applies": [a.archetype.id for a in chosen.applicable],
                    "report": chosen.report(),
                    "nothing_applies": chosen.nothing_applies}

        reg.add(Tool(
            "design.select",
            "Given a problem — coolant_phase, flow_regime, source_geometry, "
            "material_family, footprint, flow_distribution, load_type, span, "
            "and so on — say which archetypes apply. If none does, it says so "
            "and names what it excluded and why. Do not adapt an excluded "
            "archetype; nothing applying is a real answer.",
            choose,
            parameters={"problem": {
                "type": "object",
                "description": "stated quantities, e.g. "
                               "{\"footprint\": \"90 mm\", \"flow_regime\": \"laminar\"}"}},
            required=("problem",)))

        def build_part(archetype_id: str, values: Optional[Dict[str, Any]] = None,
                       name: str = "") -> Dict[str, Any]:
            a = library.get(archetype_id)
            if a is None:
                raise KeyError(f"no archetype '{archetype_id}'")
            return {"from_archetype": a.id, "status": a.status,
                    "known_failure_modes": [m.name for m in a.failure_modes],
                    "document": _arch.instantiate(a, values or {}, name=name)}

        reg.add(Tool(
            "design.instantiate",
            "Adapt an archetype into a part document: the archetype's program "
            "plus the numbers this job needs. Values may carry units ('4 mm'); "
            "anything not supplied keeps the archetype's working default.",
            build_part,
            parameters={"archetype_id": {"type": "string"},
                        "values": {"type": "object",
                                   "description": "parameter overrides"},
                        "name": {"type": "string",
                                 "description": "name for the resulting part"}},
            required=("archetype_id",)))

        # Registered on the checkout existing rather than on a live probe:
        # probing means spawning a Python that imports scipy, and paying that
        # on every toolbox build would put seconds into the wake path. The
        # tool reports AtlasUnavailable clearly if the checkout is broken.
        from core import atlas as _atlas
        if os.path.isdir(_atlas.root()):
            def evaluate_design(archetype_id: str,
                                values: Optional[Dict[str, Any]] = None,
                                conditions: Optional[Dict[str, Any]] = None
                                ) -> Dict[str, Any]:
                a = library.get(archetype_id)
                if a is None:
                    raise KeyError(f"no archetype '{archetype_id}'")
                document = _arch.instantiate(a, values or {})
                answer = _atlas.evaluate(document, a.analyses, conditions or {},
                                         spec=a.id)
                answer["between_the_analyses"] = _atlas.consistency(
                    answer["results"])
                answer["known_failure_modes"] = [
                    {"name": m.name, "detected_by": m.detected_by or None}
                    for m in a.failure_modes]
                answer["status"] = a.status
                return answer

            reg.add(Tool(
                "design.evaluate",
                "Adapt an archetype and run the physics it declares: the "
                "checker battery, the thermal or structural model, and the "
                "independent cross-check. Reports what each analysis could "
                "NOT check, where two analyses disagree, and the failure "
                "modes none of them covers. Conditions are SI: flow_m3_s, "
                "load_n.",
                evaluate_design,
                parameters={"archetype_id": {"type": "string"},
                            "values": {"type": "object",
                                       "description": "parameter overrides"},
                            "conditions": {"type": "object",
                                           "description": "operating conditions, "
                                                          "e.g. {\"flow_m3_s\": 3.3e-5}"}},
                required=("archetype_id",)))

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

    # ---- borrowed: MCP servers that live somewhere else ----
    # The CAD-driver layer is commodity (docs/PRIOR_ART.md), so we bridge it
    # rather than rebuild it. Mounted last, so the tools we own read first in
    # the catalogue. Nothing in the manifest ships enabled, which makes this a
    # no-op until the user turns a bridge on.
    if bridges:
        from core.bridges import mount_all
        for report in mount_all(reg):
            log.info("%s", report.summary())
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
