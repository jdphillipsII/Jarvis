#!/usr/bin/env python3
"""The `jarvis` command.

    jarvis status          what's installed, configured and reachable
    jarvis doctor          check every prerequisite and say what's missing
    jarvis tools           list what JARVIS can do at the current agency
    jarvis bridges         borrowed MCP servers: what is classified, what is not
    jarvis archetypes [id]  the design library: what is proven, and how it fails
    jarvis figures [slug]   explanatory figures, and whether their numbers still hold
    jarvis link            put `jarvis` on PATH (run once, via python3 cli.py link)
    jarvis serve           the one JARVIS: every surface is a view of it
    jarvis app             open the application window
    jarvis companion       open the small pinned window
    jarvis author <subject>  local model: describe the shape, fit it, build it
    jarvis figure-bench [models]  score models on shape, restraint and binding
    jarvis design k=v ...   select an archetype, adapt it, verify it, run the
                            physics — and end by naming what none of it covered
    jarvis chat            text-mode conversation with the full tool loop
    jarvis bench [models]  score models on tool choice, args, persona, speed
    jarvis mcp             serve the toolbox over MCP on stdio
    jarvis listen          the voice loop
    jarvis presence        the camera presence daemon
    jarvis gestures        the camera gesture daemon
    jarvis watch           the proactive daemon (also serves the HUD)
    jarvis hud             open the HUD in a browser
    jarvis up              everything at once
    jarvis install         write systemd user units
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

G = GREEN = '\033[32m'
GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
OK, NO = f"{GREEN}ok{OFF}", f"{RED}missing{OFF}"


from core.config import cfg as _cfg


def _venv_python() -> str:
    p = os.path.join(ROOT, ".venvs/voice/bin/python")
    return p if os.path.exists(p) else sys.executable


# ---- commands ---------------------------------------------------------------

def cmd_doctor(_) -> int:
    print(f"{DIM}jarvis doctor{OFF}\n")
    failures = 0

    def check(label: str, good: bool, hint: str = "") -> None:
        nonlocal failures
        print(f"  {label:<28} {OK if good else NO}")
        if not good and hint:
            print(f"  {DIM}{'':<28} -> {hint}{OFF}")
            failures += 1

    check("jarvis on PATH", linked(),
          f"python3 {ROOT}/cli.py link")

    # The launcher picks this interpreter, so check THAT one can import what
    # the service needs — not whichever python happens to be running doctor.
    runner = _venv_python()
    probe = subprocess.run(
        [runner, "-c", "import yaml, requests"], capture_output=True, text=True)
    check("service imports", probe.returncode == 0,
          f"{runner} -m pip install pyyaml requests"
          + (f"   ({probe.stderr.strip().splitlines()[-1]})"
             if probe.stderr.strip() else ""))

    unit = os.path.expanduser("~/.config/systemd/user/jarvis.service")
    check("jarvis.service", os.path.exists(unit), "jarvis install")
    if os.path.exists(unit):
        active = subprocess.run(["systemctl", "--user", "is-active", "jarvis"],
                                capture_output=True, text=True).stdout.strip()
        check("jarvis running", active == "active",
              "systemctl --user enable --now jarvis")

    groups = subprocess.run(["id", "-nG"], capture_output=True, text=True).stdout.split()
    check("render/video groups", {"render", "video"} <= set(groups),
          "sudo usermod -aG video,render $USER  then reboot")
    check("rocminfo", shutil.which("rocminfo") is not None,
          "sudo dnf install -y rocminfo rocm-smi")
    if shutil.which("rocminfo"):
        info = subprocess.run(["rocminfo"], capture_output=True, text=True).stdout
        check("gfx1100 (7900 XTX)", "gfx1100" in info, "GPU not visible to ROCm")
    check("ollama", shutil.which("ollama") is not None,
          "curl -fsSL https://ollama.com/install.sh | sh")
    check("audio player", any(shutil.which(p) for p in ("pw-play", "paplay", "aplay")),
          "sudo dnf install -y pipewire-utils")
    check("voice venv", os.path.exists(os.path.join(ROOT, ".venvs/voice/bin/python")),
          "bash setup/voice-setup.sh")
    try:
        from core import fluids
        have_cp = fluids.available()
    except Exception:
        have_cp = False
    check("CoolProp (real fluids)", have_cp, "uv pip install CoolProp")
    voice = _cfg("JARVIS_VOICE", "en_GB-alan-medium")
    check(f"piper voice ({voice})",
          os.path.exists(os.path.join(ROOT, "models/piper", voice + ".onnx")),
          f"python -m piper.download_voices {voice} --download-dir models/piper")

    print(f"\n  agency: {DIM}{_cfg('JARVIS_AGENCY', 'advisory')}{OFF}"
          f"   model: {DIM}{_cfg('JARVIS_CHAT_MODEL', '?')}{OFF}")
    print(f"\n{'all clear, sir.' if not failures else f'{failures} thing(s) to fix.'}")
    return 1 if failures else 0


def cmd_tools(_) -> int:
    from core.toolbox import Toolbox
    from core.tools import Agency
    from daemon.toolbox.builtin import build
    agency = Agency.parse(_cfg("JARVIS_AGENCY", "advisory"))
    box = Toolbox(registry=build(), agency=agency)
    print(f"{DIM}agency: {agency.name.lower()}{OFF}\n")
    for tool in sorted(box.registry.available(agency), key=lambda t: t.name):
        mark = "!" if tool.mutates else " "
        print(f" {mark} {tool.name:<22} {tool.description}")
    hidden = len(box.registry) - len(box.registry.available(agency))
    print(f"\n{DIM}! = requires confirmation"
          + (f"   ({hidden} tool(s) hidden above this agency)" if hidden else "")
          + OFF)
    return 0


def cmd_bridges(_) -> int:
    """Show borrowed MCP servers and what each of their tools is permitted to do."""
    from core.bridges import load_manifest, mount
    from core.tools import Agency, ToolRegistry

    manifest = load_manifest()
    if not manifest:
        print("no bridges declared (bridges/manifest.yaml)")
        return 0

    for name, spec in sorted(manifest.items()):
        where = " ".join(spec.command) if spec.transport == "stdio" else spec.url
        state = f"{GREEN}enabled{OFF}" if spec.enabled else f"{DIM}disabled{OFF}"
        print(f"\n{name}  {state}  {DIM}{spec.transport} → {where}{OFF}")
        if spec.description:
            print(f"  {DIM}{spec.description}{OFF}")
        for level in Agency:
            named = sorted(p.name for p in spec.tools.values() if p.agency is level)
            if named:
                print(f"  {level.name.lower():<9} {len(named):>3}  "
                      f"{DIM}{', '.join(named[:4])}"
                      f"{' …' if len(named) > 4 else ''}{OFF}")

        if not spec.enabled:
            continue
        # Enabled means we can ask the server what it actually offers, which is
        # the only way to learn that the manifest has drifted from upstream.
        try:
            client = spec.connect()
        except Exception as exc:
            print(f"  {RED}unavailable{OFF}: {exc}")
            continue
        report = mount(ToolRegistry(), spec, client)
        print(f"  {GREEN}{len(report.mounted)} mounted{OFF}")
        for label, items, colour in (("unclassified", report.unclassified, DIM),
                                     ("absent", report.absent, DIM),
                                     ("disputed", report.disputed, RED)):
            if items:
                print(f"  {colour}{label}{OFF}: {', '.join(items)}")
    print(f"\n{DIM}a tool with no manifest entry is not mounted{OFF}")
    return 0


def cmd_archetypes(a) -> int:
    """Show the archetype library, or one archetype in full."""
    from core.archetypes import Library
    library = Library.load()
    if not len(library):
        print("no archetypes (archetypes/*.yaml)")
        return 0

    wanted = a.extra[0] if a.extra else ""
    if not wanted:
        for arch in sorted(library, key=lambda x: x.id):
            rungs = {"proposed": DIM, "simulated": DIM, "built": GREEN,
                     "measured": GREEN}
            print(f"\n{arch.id}  {rungs.get(arch.status, DIM)}{arch.status}{OFF}")
            print(f"  {arch.summary.strip()}")
            print(f"  {DIM}{len(arch.parameters)} parameters · "
                  f"{len(arch.applicability)} conditions · "
                  f"{len(arch.failure_modes)} known failure modes{OFF}")
        print(f"\n{DIM}jarvis archetypes <id> for one in full{OFF}")
        return 0

    arch = library.get(wanted)
    if arch is None:
        print(f"{RED}no archetype '{wanted}'{OFF}")
        print(f"{DIM}have: {', '.join(sorted(x.id for x in library))}{OFF}")
        return 1

    print(f"{arch.id}  {DIM}{arch.status}{OFF}\n  {arch.summary.strip()}")
    if arch.evidence.strip():
        print(f"\n{DIM}evidence{OFF}\n  {arch.evidence.strip()}")
    print(f"\n{DIM}parameters{OFF}")
    for spec in arch.parameters:
        shown = (lambda v: f"{int(v)}" if spec.integer else f"{v:g}")
        rng = (f"{shown(spec.bounds[0])}–{shown(spec.bounds[1])}"
               if spec.bounds else "fixed")
        print(f"  {spec.name:<16} {shown(spec.default):>8} {spec.unit:<4} "
              f"{DIM}{rng}{OFF}")
    print(f"\n{DIM}applies when{OFF}")
    for condition in arch.applicability:
        print(f"  {condition.describe()}")
        print(f"    {DIM}{' '.join(condition.why.split())}{OFF}")
    print(f"\n{DIM}known failure modes{OFF}")
    for mode in arch.failure_modes:
        print(f"  {RED}{mode.name}{OFF}")
        print(f"    {' '.join(mode.description.split())}")
        detector = mode.detected_by or f"{RED}nothing detects this{OFF}"
        print(f"    {DIM}detected by:{OFF} {detector}")
        if mode.mitigated_by:
            print(f"    {DIM}mitigated by:{OFF} {mode.mitigated_by}")
    return 0


# Operating conditions are stated the way a person says them; the analyses
# want SI. The units layer is what makes "2 L/min" and "15 N" acceptable here.
_CONDITIONS = {"flow": ("flow_m3_s", "m^3/s"), "load": ("load_n", "N")}


def cmd_design(a) -> int:
    """Run a problem through the whole chain: select, adapt, verify, analyse.

    jarvis design coolant_phase=single_phase_liquid flow_regime=laminar \
        source_geometry=flat material_family=copper footprint="90 mm" \
        flow_distribution=parallel set:n_channels=32 at:flow="2 L/min"

      k=v       the problem statement, matched against archetype conditions
      set:k=v   a parameter override — the "adapt" in retrieve and adapt
      at:k=v    an operating condition the analyses need (flow, load)
      --manifold PATH   a manifold genome, so the flow network can be solved
    """
    from core import atlas
    from core.archetypes import Library, instantiate, select
    from core.units import UnitError, convert

    problem, overrides, conditions = {}, {}, {}
    for token in a.extra:
        if "=" not in token:
            print(f"{RED}not a key=value: {token}{OFF}")
            return 2
        key, value = token.split("=", 1)
        if key.startswith("set:"):
            overrides[key[4:]] = value
        elif key.startswith("at:"):
            name, unit = _CONDITIONS.get(key[3:], (key[3:], ""))
            try:
                conditions[name] = convert(value, unit).value if unit else value
            except UnitError as exc:
                print(f"{RED}{key}: {exc}{OFF}")
                return 2
        else:
            problem[key] = value

    if a.manifold:
        import yaml
        with open(os.path.expanduser(a.manifold)) as fh:
            conditions["manifold_document"] = yaml.safe_load(fh)

    library = Library.load()
    if not len(library):
        print("no archetypes (archetypes/*.yaml)")
        return 1

    # ---- 1. select -------------------------------------------------------
    print(f"{DIM}── select ──{OFF}")
    chosen = select(library, problem)
    print(chosen.report())
    if chosen.nothing_applies:
        # The chain stops here on purpose. Adapting an excluded archetype is
        # exactly the failure the library exists to prevent.
        return 1
    archetype = chosen.best

    # ---- 2. adapt --------------------------------------------------------
    print(f"\n{DIM}── adapt ──{OFF}  {archetype.id}")
    try:
        document = instantiate(archetype, overrides, name=a.name or "")
    except Exception as exc:
        print(f"{RED}{exc}{OFF}")
        return 1
    for spec in archetype.parameters:
        value, = [p["value"] for p in document["parameters"] if p["name"] == spec.name]
        changed = spec.name in overrides
        mark = f"{GREEN}→{OFF}" if changed else " "
        note = f"  {DIM}(default {spec.default:g}){OFF}" if changed else ""
        print(f"  {mark} {spec.name:<16} {value:>8} {spec.unit}{note}")

    # ---- 3 & 4. load, verify, analyse -------------------------------------
    print(f"\n{DIM}── atlas ──{OFF}  {DIM}{atlas.root()}{OFF}")
    try:
        answer = atlas.evaluate(document, archetype.analyses, conditions,
                                spec=archetype.id)
    except atlas.AtlasUnavailable as exc:
        print(f"{RED}{exc}{OFF}")
        return 1
    for finding in answer["findings"]:
        print(f"  {RED}{finding}{OFF}")
    if not answer["ok"]:
        print(f"  {RED}the document did not load{OFF}")
        return 1
    print(f"  {GREEN}loaded{OFF}")

    for name, result in answer["results"].items():
        print(f"\n  {name}")
        if name.endswith("verify_part"):
            print(f"    {GREEN}{result['passed']} rule(s) passed{OFF}"
                  + (f", {RED}{len(result['failed'])} failed{OFF}"
                     if result["failed"] else ""))
            for check in result["failed"]:
                print(f"    {RED}{check['rule']}{OFF} {check.get('detail') or ''}")
            # The interesting half of a certificate.
            for dark in result["dark_regions"]:
                print(f"    {DIM}not checked: {dark['aspect']} "
                      f"({dark['reason']}){OFF}")
            continue
        for key, value in result.items():
            if value is None:
                continue
            shown = f"{value:.4g}" if isinstance(value, float) else value
            print(f"    {key:<22} {shown}")

    for name, reason in answer["skipped"].items():
        print(f"\n  {DIM}skipped {name} — {reason}{OFF}")

    # Each analysis is honest on its own and neither knows the other ran. The
    # interesting failures live between them.
    if (notes := atlas.consistency(answer["results"])):
        print(f"\n{DIM}── between the analyses ──{OFF}")
        for note in notes:
            print(f"  {note}")

    # ---- 5. what none of the above covered -------------------------------
    # The chain ends here rather than on a number, because a number that does
    # not say what it left out is the thing we are trying not to build.
    print(f"\n{DIM}── known failure modes of {archetype.id} ──{OFF}")
    for mode in archetype.failure_modes:
        detector = mode.detected_by or f"{RED}nothing detects this{OFF}"
        print(f"  {mode.name:<28} {DIM}detected by:{OFF} {detector}")
        if mode.mitigated_by:
            print(f"  {'':<28} {DIM}mitigated by:{OFF} {mode.mitigated_by}")
    if archetype.status != "measured":
        print(f"\n{DIM}{archetype.id} is '{archetype.status}' — every number "
              f"above is predicted, none of it measured.{OFF}")
    return 0


def cmd_figures(a) -> int:
    """Explanatory figures, and whether their numbers still hold."""
    from core import figures as F
    gallery = F.load_all()
    if not gallery:
        print("no figures (figures/*/figure.yaml)")
        return 0
    wanted = a.extra[0] if a.extra else ""
    if wanted and wanted not in gallery:
        print(f"{RED}no figure '{wanted}'{OFF}")
        print(f"{DIM}have: {', '.join(sorted(gallery))}{OFF}")
        return 1
    shown = [gallery[wanted]] if wanted else list(gallery.values())

    for figure in shown:
        state = F.check(figure)
        colour = {F.FRESH: GREEN, F.STALE: RED,
                  F.UNCHECKABLE: RED, F.MISSING: DIM}[state.state]
        built = f"{GREEN}built{OFF}" if figure.built else f"{DIM}not built{OFF}"
        print(f"\n{figure.slug}  {colour}{state.state}{OFF}  {built}  "
              f"{DIM}{figure.size}{OFF}")
        print(f"  {' '.join(figure.title.split())}")
        print(f"  {DIM}{' '.join(figure.question.split())}{OFF}")
        print(f"  {DIM}numbers from:{OFF} {' '.join(figure.source.split())}")
        if state.reason:
            print(f"  {RED}{state.reason}{OFF}")
        for field, was, now, by in state.moved[:8]:
            print(f"  {RED}moved{OFF} {field}: {was!r} → {now!r} ({by:.2%})")
        if figure.findings:
            print(f"  {DIM}written up in:{OFF} {figure.findings}")
    print(f"\n{DIM}a figure that cannot be re-checked is a picture, not a "
          f"result{OFF}")
    return 0


def cmd_author(a) -> int:
    """Run a subject through the local model: shape, archetype, genome, page."""
    from core import figure_archetypes as fa
    from core.figure_author import author
    from core.figure_compiler import emit
    from core.ollama import OllamaChat

    subject = " ".join(t for t in a.extra if not t.startswith("-")).strip()
    if not subject:
        print("usage: jarvis author <what to explain>")
        return 2
    model = a.model or _cfg("JARVIS_CHAT_MODEL", "qwen2.5:7b")
    library = fa.Library.load()
    print(f"{DIM}{model} · {len(library)} archetypes{OFF}\n")

    draft = author(subject, library, OllamaChat(model))
    print(f"{DIM}shape{OFF}  " + (", ".join(draft.traits) or
                                  f"{DIM}none — no mechanism{OFF}"))
    if draft.lesson:
        print(f"{DIM}lesson{OFF} {draft.lesson}")
    if draft.refusal:
        print(f"\n{RED}refused{OFF}\n{draft.refusal}")
        return 1
    if draft.faults:
        print(f"\n{RED}the binding did not hold{OFF}")
        for fault in draft.faults:
            print(f"  {fault}")
        return 1

    print(f"\n{GREEN}{draft.archetype.id}{OFF} — "
          f"{' '.join(draft.archetype.object.split())}")
    print(f"{DIM}figure{OFF} {draft.genome.figure}")
    print(f"{DIM}question{OFF} {draft.genome.question}")
    for part in draft.genome.parts:
        if part.note:
            print(f"  {part.id:<18} {DIM}{part.note}{OFF}")

    if not a.build:
        print(f"\n{DIM}--build to compile and write the page{OFF}")
        return 0
    import os
    where = os.path.join(ROOT, "figures", draft.genome.figure.replace("_", "-"))
    os.makedirs(where, exist_ok=True)
    import yaml as _yaml
    with open(os.path.join(where, "genome.yaml"), "w") as fh:
        _yaml.safe_dump(draft.document, fh, sort_keys=False)
    with open(os.path.join(where, "build.mjs"), "w") as fh:
        fh.write(emit(draft.genome))
    print(f"\n{GREEN}wrote{OFF} {where}/genome.yaml and build.mjs")
    print(f"{DIM}then:{OFF} cd {where} && node build.mjs")
    return 0


def cmd_figure_bench(a) -> int:
    """Score models on describing a shape — and on refusing when there isn't one."""
    from core import figure_archetypes as fa
    from core.figure_bench import DEFAULT_CASES, render, render_failures, run
    from core.ollama import OllamaChat

    models = [t for t in a.extra if not t.startswith("-")] or \
        [_cfg("JARVIS_CHAT_MODEL", "qwen2.5:7b")]
    library = fa.Library.load()
    print(f"{DIM}{len(DEFAULT_CASES)} cases, "
          f"{sum(1 for c in DEFAULT_CASES if c.is_refusal)} of them refusals · "
          f"{len(library)} archetypes{OFF}\n")
    reports = []
    for model in models:
        try:
            reports.append(run(OllamaChat(model), library,
                               DEFAULT_CASES, model=model))
        except Exception as exc:
            print(f"{RED}{model}: {exc}{OFF}")
    if not reports:
        return 1
    print(render(reports))
    for report in reports:
        if report.failures():
            print(f"\n{DIM}{report.model} missed{OFF}")
            print(render_failures(report))
    print(f"\n{DIM}restraint is weighted the same as shape: a model that "
          f"always finds a mechanism is worse than one that sometimes does"
          f"{OFF}")
    return 0


LAUNCHER = """#!/usr/bin/env bash
# Written by `jarvis link`. Re-run it after moving the checkout.
#
# The venv is resolved at run time rather than baked in, so creating it later
# is enough — this does not need regenerating when the audio stack arrives.
ROOT="{root}"
PY="$ROOT/.venvs/voice/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
exec "$PY" "$ROOT/cli.py" "$@"
"""


def launcher_body(root: str) -> str:
    return LAUNCHER.format(root=root)


def bin_dir() -> str:
    return os.path.expanduser("~/.local/bin")


def linked() -> bool:
    """Is `jarvis` on PATH and pointing at this checkout?"""
    found = shutil.which("jarvis")
    if not found:
        return False
    try:
        with open(found) as fh:
            return f'ROOT="{ROOT}"' in fh.read()
    except OSError:
        return False


def cmd_link(_) -> int:
    """Put `jarvis` on PATH. Bootstrap with: python3 cli.py link"""
    where = bin_dir()
    os.makedirs(where, exist_ok=True)
    target = os.path.join(where, "jarvis")
    with open(target, "w") as fh:
        fh.write(launcher_body(ROOT))
    os.chmod(target, 0o755)
    print(f"  wrote {target}")

    on_path = any(os.path.realpath(p) == os.path.realpath(where)
                  for p in os.environ.get("PATH", "").split(os.pathsep) if p)
    if on_path:
        print(f"\n{GREEN}jarvis is on PATH{OFF} — try: jarvis doctor")
        return 0
    print(f"\n{RED}{where} is not on PATH{OFF}")
    print("  add it for this shell and every future one:")
    print(f'    echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.bashrc')
    print("    source ~/.bashrc")
    return 0


def cmd_serve(a) -> int:
    """Run the one JARVIS. Every other surface is a client of this."""
    from daemon.service import DEFAULT_PORT, Jarvis, serve
    port = int(a.port or DEFAULT_PORT)
    jarvis = Jarvis.start()
    server = serve(jarvis, port=port)
    tools = len(jarvis.toolbox.registry.available(jarvis.toolbox.agency))
    print(f"{GREEN}JARVIS{OFF} on http://127.0.0.1:{port}  "
          f"{DIM}agency {jarvis.toolbox.agency.name.lower()} · "
          f"{tools} tools{OFF}")
    print(f"{DIM}token written to ~/.local/state/jarvis/token (0600){OFF}")
    print(f"{DIM}loopback only — this can confirm a pending command{OFF}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        server.shutdown()
    return 0


def _window(mode: str) -> int:
    launcher = os.path.join(ROOT, "setup", "app", "jarvis-window")
    if not os.path.exists(launcher):
        print(f"{RED}missing {launcher}{OFF}")
        return 1
    return subprocess.call([launcher, mode])


def cmd_app(_) -> int:
    """Open the application window."""
    return _window("app")


def cmd_companion(_) -> int:
    """Open the small pinned window that follows you around."""
    return _window("companion")


def cmd_status(_) -> int:
    from core.client import Client, NotRunning
    # Prefer the running JARVIS: it answers from a warm process, and anything
    # it has pending is real rather than a fresh store that knows nothing.
    try:
        client = Client()
        state = client.state()
    except NotRunning:
        pass
    else:
        print(f"  {'agency':<16} {state['agency']}")
        print(f"  {'uptime':<16} {state['uptime_s']}s")
        result = client.invoke("system.status")
        for key, value in sorted((result.get("value") or {}).items()):
            print(f"  {key:<16} {value}")
        for proposal in state.get("proposals") or []:
            print(f"  {RED}pending{OFF}          {proposal['summary']}")
        return 0

    from daemon.toolbox.builtin import build
    from core.toolbox import Toolbox
    from core.tools import Agency
    box = Toolbox(registry=build(), agency=Agency.parse(_cfg("JARVIS_AGENCY")))
    r = box.invoke("system.status")
    if not r.ok:
        print(f"{RED}{r.error}{OFF}")
        return 1
    for key, value in sorted(r.value.items()):
        print(f"  {key:<16} {value}")
    return 0


def cmd_mcp(_) -> int:
    """Serve the toolbox over MCP on stdio (for Hermes Agent, Claude Desktop, ...)."""
    from core.bus import Bus
    from core.mcp_server import McpServer
    from core.ollama import OllamaChat
    from core.registry import Registry
    from core.toolbox import Toolbox
    from core.tools import Agency
    from daemon.toolbox.builtin import build

    heavy = _cfg("JARVIS_HEAVY_MODEL", "")
    box = Toolbox(registry=build(bus=Bus(registry=Registry.load()),
                                 heavy_chat=OllamaChat(heavy) if heavy else None),
                  agency=Agency.parse(_cfg("JARVIS_AGENCY", "advisory")))
    # stdout is the protocol channel — nothing else may write to it.
    McpServer(box).serve()
    return 0


def cmd_bench(a) -> int:
    """Measure models against your real toolbox: tool choice, args, persona, speed."""
    import tempfile, time
    from core.agent import Agent
    from core.bench import (DEFAULT_CASES, CaseResult, ModelReport,
                            applicable, render, render_failures)
    from core.ollama import OllamaChat
    from core.proposals import ProposalStore
    from core.toolbox import Toolbox
    from core.tools import Agency
    from daemon.proactive import Briefing
    from daemon.toolbox.builtin import build

    models = a.extra or [m for m in (_cfg("JARVIS_CHAT_MODEL"),
                                     _cfg("JARVIS_HEAVY_MODEL")) if m]
    if not models:
        print("usage: ./cli.py bench <model> [model ...]")
        return 1

    # Fail fast rather than timing out ten cases per model against a dead server.
    try:
        import requests
        requests.get("http://127.0.0.1:11434/api/tags", timeout=3).raise_for_status()
    except Exception:
        print(f"{RED}ollama unreachable at 127.0.0.1:11434{OFF}")
        print(f"{DIM}start it, then re-run{OFF}")
        return 1

    # Nothing here may touch the real system: notes go to a scratch file, no bus
    # is attached, and mutating tools stop at a Proposal that is never confirmed.
    scratch = os.path.join(tempfile.mkdtemp(), "bench-notes.md")
    reports = []

    for model in models:
        print(f"\n{DIM}--- {model} " + "-" * max(0, 50 - len(model)) + OFF)
        report = ModelReport(model)
        for case in applicable(DEFAULT_CASES, bool(_cfg('JARVIS_HEAVY_MODEL', ''))):
            heavy = _cfg("JARVIS_HEAVY_MODEL", "")
            box = Toolbox(registry=build(bus=None, briefing=Briefing(),
                                         notes_path=scratch,
                                         heavy_chat=OllamaChat(heavy) if heavy else None),
                          agency=Agency.ACTUATOR, proposals=ProposalStore())
            agent = Agent(toolbox=box, chat=OllamaChat(model))
            started = time.monotonic()
            tool, args, text, err = None, {}, "", ""
            try:
                turn = agent.say(case.prompt)
                text = turn.text
                if turn.tools_used:
                    tool = turn.tools_used[-1]
                if turn.proposal is not None:      # mutating: never confirmed
                    tool, args = turn.proposal.tool, turn.proposal.args
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
            secs = time.monotonic() - started

            r = CaseResult(case, tool, args, text, secs, err)
            report.results.append(r)
            mark = f"{G}ok{OFF}" if (r.ok_tool and r.ok_args) else f"{RED}no{OFF}"
            print(f"  {mark} {secs:5.1f}s  {case.prompt[:44]:<44} "
                  f"{DIM}{tool or '-'}{OFF}")
        reports.append(report)

    print("\n" + render(reports))
    for rep in reports:
        if rep.failures():
            print(f"\n{DIM}{rep.model} missed:{OFF}\n{render_failures(rep)}")
    return 0


def cmd_chat(_) -> int:
    """Text-mode conversation with the full tool loop — no mic, no speakers."""
    from core.agent import Agent
    from core.bus import Bus
    from core.ollama import OllamaChat
    from core.registry import Registry
    from core.toolbox import Toolbox
    from core.tools import Agency
    from daemon.toolbox.builtin import build

    agency = Agency.parse(_cfg("JARVIS_AGENCY", "advisory"))
    fast = _cfg("JARVIS_CHAT_MODEL", "qwen2.5:7b")
    heavy = _cfg("JARVIS_HEAVY_MODEL", "")
    bus = Bus(registry=Registry.load())
    bus.subscribe("*", lambda i: print(f"  {DIM}[bus] {i.intent} {i.args}{OFF}"))
    box = Toolbox(registry=build(bus=bus,
                                 heavy_chat=OllamaChat(heavy) if heavy else None),
                  agency=agency)
    agent = Agent(toolbox=box, chat=OllamaChat(fast))
    if heavy:
        print(f"{DIM}fast={fast}  heavy={heavy} (via reason.deeply){OFF}")

    print(f"{DIM}agency={agency.name.lower()}  "
          f"tools={len(box.registry.available(agency))}  (ctrl-d to exit){OFF}\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        try:
            turn = agent.say(text)
        except Exception as exc:
            print(f"  {RED}{exc}{OFF}")
            continue
        if turn.tools_used:
            print(f"  {DIM}tools: {', '.join(turn.tools_used)}{OFF}")
        print(f"JARVIS> {turn.text}\n")


def cmd_hud(_) -> int:
    """Open the HUD in a browser (the daemon serves it)."""
    port = os.environ.get("JARVIS_HUD_PORT", "8787")
    url = f"http://127.0.0.1:{port}/"
    print(f"opening {url}")
    print(f"{DIM}if nothing loads, start the daemon first: ./cli.py watch{OFF}")
    subprocess.call(["xdg-open", url])
    return 0


def _exec(script: str, extra) -> int:
    return subprocess.call([_venv_python(), os.path.join(ROOT, script), *extra])


def cmd_listen(a) -> int:   return _exec("voice/loop.py", a.extra)
def cmd_presence(a) -> int: return _exec("vision/presence_daemon.py", a.extra)
def cmd_gestures(a) -> int: return _exec("vision/gesture_daemon.py", a.extra)


def cmd_watch(_) -> int:
    from core.bus import Bus, SocketSource
    from core.policy import SpeakPolicy
    from core.registry import Registry
    from daemon.greeter import Greeter
    from daemon.proactive import ProactiveDaemon
    import daemon.watchers  # noqa: F401  — registers the watchers
    import time

    from core.hud_state import HudState
    from hud.server import Hub, serve

    bus = Bus(registry=Registry.load())
    d = ProactiveDaemon(bus=bus, policy=SpeakPolicy())
    Greeter(bus=bus, briefing=d.briefing, policy=d.policy).attach()

    hub = Hub(HudState())
    bus.subscribe("jarvis.*", hub.on_intent, "hud")
    bus.subscribe("presence.*", hub.on_presence, "hud-presence")
    port = int(os.environ.get("JARVIS_HUD_PORT", "8787"))
    try:
        serve(hub, port=port)
        print(f"{DIM}hud on http://127.0.0.1:{port}{OFF}")
    except OSError as exc:
        print(f"{DIM}hud unavailable: {exc}{OFF}")
    bus.subscribe("jarvis.*", lambda i: print(f"  [{i.intent}] {i.args['text']}"
                                              f"  {DIM}({i.args['reason']}){OFF}"))
    sock = os.environ.get("JARVIS_SOCKET", f"/run/user/{os.getuid()}/jarvis.sock")
    try:
        SocketSource(bus, sock).start()
        print(f"{DIM}bus listening on {sock}{OFF}")
    except OSError as exc:
        print(f"{DIM}socket unavailable ({exc}); in-process only{OFF}")
    print("watching. ctrl-c to stop.\n")
    try:
        from daemon.toolbox.builtin import build as build_tools
        from core.toolbox import Toolbox
        from core.tools import Agency
        status = Toolbox(registry=build_tools(), agency=Agency.ADVISORY)
        while True:
            d.tick()
            hub.state.held = len(d.briefing)
            reading = status.invoke("system.status")
            if reading.ok:
                hub.set_telemetry(reading.value)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nstopping.")
    return 0


def cmd_install(a) -> int:
    # Put the command on PATH first: every instruction printed below assumes
    # `jarvis` exists, and for a long time it did not.
    cmd_link(a)
    print()
    unit_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(unit_dir, exist_ok=True)
    py = _venv_python()
    units = {
        "jarvis.service": ("JARVIS — the one process every surface talks to",
                           f"{py} {ROOT}/cli.py serve"),
        "jarvis-watch.service": ("JARVIS proactive daemon", f"{py} {ROOT}/cli.py watch"),
        "jarvis-presence.service": ("JARVIS presence detection",
                                    f"{py} {ROOT}/vision/presence_daemon.py"),
    }
    for name, (desc, cmd) in units.items():
        with open(os.path.join(unit_dir, name), "w") as fh:
            fh.write(f"""[Unit]
Description={desc}
After=graphical-session.target

[Service]
Type=simple
ExecStart={cmd}
Restart=on-failure
RestartSec=5
WorkingDirectory={ROOT}

[Install]
WantedBy=default.target
""")
        print(f"  wrote {unit_dir}/{name}")
    # The desktop entries, with this checkout's path baked in.
    apps = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps, exist_ok=True)
    for name in ("jarvis.desktop", "jarvis-companion.desktop"):
        source = os.path.join(ROOT, "setup", "app", name)
        if not os.path.exists(source):
            continue
        with open(source) as fh:
            body = fh.read().replace("JARVIS_ROOT_PLACEHOLDER", ROOT)
        with open(os.path.join(apps, name), "w") as fh:
            fh.write(body)
        print(f"  wrote {apps}/{name}")

    print("\n  systemctl --user daemon-reload")
    print("  systemctl --user enable --now jarvis jarvis-watch jarvis-presence")
    print(f"\n{DIM}the companion window needs one KWin rule, imported once:{OFF}")
    print("  System Settings -> Window Management -> Window Rules -> Import")
    print(f"  {ROOT}/setup/app/jarvis-companion.kwinrule")
    print(f"\n{DIM}then bind a global shortcut to:{OFF}")
    print(f"  {ROOT}/setup/app/jarvis-window companion")
    return 0


def cmd_up(a) -> int:
    procs = []
    for label, script in (("watch", "cli.py watch"),
                          ("presence", "vision/presence_daemon.py"),
                          ("listen", "voice/loop.py")):
        procs.append(subprocess.Popen([_venv_python(),
                                       *os.path.join(ROOT, script).split()]))
        print(f"  started {label}")
    print("\nctrl-c to stop everything.")
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="jarvis", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, takes_extra in (
            ("doctor", cmd_doctor, False), ("status", cmd_status, False),
            ("tools", cmd_tools, False), ("bridges", cmd_bridges, False),
            ("archetypes", cmd_archetypes, True),
            ("design", cmd_design, True),
            ("figures", cmd_figures, True),
            ("author", cmd_author, True),
            ("link", cmd_link, False),
            ("serve", cmd_serve, False), ("app", cmd_app, False),
            ("companion", cmd_companion, False),
            ("figure-bench", cmd_figure_bench, True),
            ("chat", cmd_chat, False),
            ("bench", cmd_bench, True), ("mcp", cmd_mcp, False),
            ("listen", cmd_listen, True),
            ("presence", cmd_presence, True), ("gestures", cmd_gestures, True),
            ("watch", cmd_watch, False),
            ("install", cmd_install, False), ("up", cmd_up, False)):
        p = sub.add_parser(name, help=fn.__doc__ or name)
        p.set_defaults(fn=fn, passthrough=takes_extra)
    # Flags for the wrapped daemons are collected by parse_known_args and
    # forwarded verbatim. A positional with nargs="*" or REMAINDER cannot do
    # this — argparse refuses to let either absorb tokens starting with "-",
    # so `jarvis gestures --preview` failed instead of passing the flag along.
    for name in ("design",):
        sub.choices[name].add_argument("--name", default="",
                                       help="name for the resulting part")
        sub.choices[name].add_argument(
            "--manifold", default="",
            help="a manifold part.yaml, for the flow-network analysis")
    sub.choices["serve"].add_argument("--port", default="",
                                      help="default 8787")
    sub.choices["author"].add_argument("--model", default="",
                                       help="which local model to ask")
    sub.choices["author"].add_argument("--build", action="store_true",
                                       help="write the genome and build.mjs")
    args, unknown = ap.parse_known_args()
    if unknown and not getattr(args, "passthrough", False):
        ap.error("unrecognized arguments: " + " ".join(unknown))
    args.extra = unknown
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
