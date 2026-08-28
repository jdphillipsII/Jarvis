#!/usr/bin/env python3
"""The `jarvis` command.

    jarvis status          what's installed, configured and reachable
    jarvis doctor          check every prerequisite and say what's missing
    jarvis tools           list what JARVIS can do at the current agency
    jarvis chat            text-mode conversation with the full tool loop
    jarvis bench [models]  score models on tool choice, args, persona, speed
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


def cmd_status(_) -> int:
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


def cmd_bench(a) -> int:
    """Measure models against your real toolbox: tool choice, args, persona, speed."""
    import tempfile, time
    from core.agent import Agent
    from core.bench import (DEFAULT_CASES, CaseResult, ModelReport,
                            render, render_failures)
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
        for case in DEFAULT_CASES:
            box = Toolbox(registry=build(bus=None, briefing=Briefing(),
                                         notes_path=scratch),
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
    bus = Bus(registry=Registry.load())
    bus.subscribe("*", lambda i: print(f"  {DIM}[bus] {i.intent} {i.args}{OFF}"))
    box = Toolbox(registry=build(bus=bus), agency=agency)
    agent = Agent(toolbox=box, chat=OllamaChat(_cfg("JARVIS_CHAT_MODEL", "qwen2.5:7b")))

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


def cmd_install(_) -> int:
    unit_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(unit_dir, exist_ok=True)
    py = _venv_python()
    units = {
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
    print("\n  systemctl --user daemon-reload")
    print("  systemctl --user enable --now jarvis-watch jarvis-presence")
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
            ("tools", cmd_tools, False), ("chat", cmd_chat, False),
            ("bench", cmd_bench, True),
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
    args, unknown = ap.parse_known_args()
    if unknown and not getattr(args, "passthrough", False):
        ap.error("unrecognized arguments: " + " ".join(unknown))
    args.extra = unknown
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
