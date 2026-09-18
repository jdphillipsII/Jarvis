"""Mounting somebody else's MCP server behind our own gate.

The survey (docs/PRIOR_ART.md) found the CAD-driver layer is commodity —
SolidWorks, FreeCAD, build123d, DXF all have maintained MCP servers already.
Borrowing them is obviously right. Trusting them is obviously not: every one of
those servers executes on call, with no notion of an agency ceiling and no
proposal step.

So a bridged server does not get to say what it is allowed to do. The manifest
does. For each advertised tool we require an entry naming an agency level and
whether it mutates; a tool with no entry is **not mounted at all**. That is the
property that matters when the upstream project ships a new version: a tool
that appears between one launch and the next is invisible until a human has
classified it.

Two smaller rules follow from the same idea:

  * A manifest error is loud. Runtime input fails closed and carries on, but a
    typo in our own configuration is a bug we want to hear about at load, not
    a capability that quietly downgraded itself to advisory.
  * If the server's own annotations say a tool writes and our manifest says it
    reads, the tool is refused rather than reconciled. We are wrong in exactly
    the direction that matters, and guessing which side is stale is not a
    decision to make at boot.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import yaml

from .mcp_client import HttpTransport, McpClient, McpError, RemoteTool, StdioTransport
from .tools import Agency, Tool, ToolRegistry

log = logging.getLogger("jarvis.bridges")

_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "bridges", "manifest.yaml")


class ManifestError(ValueError):
    """Our configuration is wrong. Raised at load, never swallowed."""


@dataclass(frozen=True)
class ToolPolicy:
    """What we permit, independent of what the server offers."""
    name: str
    agency: Agency
    mutates: bool = False
    confirm_label: str = "Confirm"
    risk: str = ""
    description: str = ""                        # overrides the server's
    quantities: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BridgeSpec:
    name: str
    transport: str                               # "stdio" | "http"
    tools: Mapping[str, ToolPolicy]
    command: Sequence[str] = ()
    url: str = ""
    cwd: str = ""
    timeout_s: float = 30.0
    enabled: bool = False                        # declared != connected
    description: str = ""

    def connect(self) -> McpClient:
        if self.transport == "stdio":
            transport: Any = StdioTransport(self.command, cwd=self.cwd or None)
        else:
            transport = HttpTransport(self.url, timeout_s=self.timeout_s)
        client = McpClient(transport, name=self.name)
        client.initialize()
        return client


@dataclass
class MountReport:
    bridge: str
    mounted: List[str] = field(default_factory=list)
    unclassified: List[str] = field(default_factory=list)   # offered, not in manifest
    absent: List[str] = field(default_factory=list)         # in manifest, not offered
    disputed: List[str] = field(default_factory=list)       # server says it writes
    error: str = ""

    def summary(self) -> str:
        if self.error:
            return f"{self.bridge}: unavailable ({self.error})"
        bits = [f"{len(self.mounted)} mounted"]
        for label, items in (("unclassified", self.unclassified),
                             ("absent", self.absent),
                             ("disputed", self.disputed)):
            if items:
                bits.append(f"{len(items)} {label}")
        return f"{self.bridge}: " + ", ".join(bits)


# ---------------------------------------------------------------- the manifest

def load_manifest(path: Optional[str] = None) -> Dict[str, BridgeSpec]:
    source = path or _DEFAULT
    if not os.path.exists(source):
        return {}
    with open(source) as fh:
        raw = yaml.safe_load(fh) or {}
    return {name: _spec(name, body) for name, body in raw.items()
            if isinstance(body, dict)}


def _spec(name: str, body: Dict[str, Any]) -> BridgeSpec:
    transport = str(body.get("transport", "")).strip().lower()
    if transport not in ("stdio", "http"):
        raise ManifestError(f"{name}: transport must be 'stdio' or 'http'")
    command = tuple(body.get("command") or ())
    url = str(body.get("url") or "")
    if transport == "stdio" and not command:
        raise ManifestError(f"{name}: stdio transport needs a command")
    if transport == "http" and not url:
        raise ManifestError(f"{name}: http transport needs a url")

    policies: Dict[str, ToolPolicy] = {}
    for tool_name, meta in (body.get("tools") or {}).items():
        policies[str(tool_name)] = _policy(name, str(tool_name), meta or {})

    return BridgeSpec(
        name=name, transport=transport, tools=policies, command=command, url=url,
        cwd=str(body.get("cwd") or ""),
        timeout_s=float(body.get("timeout_s", 30.0)),
        enabled=bool(body.get("enabled", False)),
        description=str(body.get("description") or ""))


def _policy(bridge: str, tool: str, meta: Dict[str, Any]) -> ToolPolicy:
    where = f"{bridge}.{tool}"
    raw_agency = str(meta.get("agency", "")).strip().upper()
    if raw_agency not in Agency.__members__:
        raise ManifestError(
            f"{where}: agency must be one of "
            f"{', '.join(a.lower() for a in Agency.__members__)}")
    agency = Agency[raw_agency]
    mutates = bool(meta.get("mutates", False))
    if mutates and agency < Agency.ACTUATOR:
        raise ManifestError(
            f"{where}: a tool that mutates cannot be advisory — advisory means "
            f"no side effects")
    quantities = {str(k): str(v) for k, v in (meta.get("quantities") or {}).items()}
    return ToolPolicy(
        name=tool, agency=agency, mutates=mutates,
        confirm_label=str(meta.get("confirm_label") or "Confirm"),
        risk=str(meta.get("risk") or ""),
        description=str(meta.get("description") or ""),
        quantities=quantities)


# ---------------------------------------------------------------- mounting

def mount(registry: ToolRegistry, spec: BridgeSpec, client: McpClient) -> MountReport:
    """Add the server's classified tools to the registry. Never raises."""
    report = MountReport(bridge=spec.name)
    try:
        offered = client.list_tools()
    except McpError as exc:
        report.error = str(exc)
        return report

    seen = set()
    for remote in offered:
        seen.add(remote.name)
        policy = spec.tools.get(remote.name)
        if policy is None:
            report.unclassified.append(remote.name)
            log.warning("%s offers %r with no manifest entry — not mounted",
                        spec.name, remote.name)
            continue
        if remote.read_only is False and not policy.mutates:
            report.disputed.append(remote.name)
            log.error("%s.%s: server says it writes, manifest says it reads — "
                      "not mounted", spec.name, remote.name)
            continue
        registry.add(_wrap(spec, remote, policy, client))
        report.mounted.append(remote.name)

    report.absent = sorted(set(spec.tools) - seen)
    for missing in report.absent:
        log.warning("%s: manifest declares %r but the server does not offer it",
                    spec.name, missing)
    return report


def _wrap(spec: BridgeSpec, remote: RemoteTool, policy: ToolPolicy,
          client: McpClient) -> Tool:
    def handler(**args: Any) -> Any:
        return client.call_tool(remote.name, args)

    parameters = remote.properties
    # A borrowed tool has no idea what a dimension is. Naming one here buys the
    # same fail-closed check our own physics tools get: "45" for a temperature
    # is refused at the boundary rather than becoming 45 K three steps later.
    for arg, dimension in policy.quantities.items():
        if arg in parameters:
            hint = str(parameters[arg].get("description") or "")
            parameters[arg] = {"type": "quantity", "dimension": dimension,
                               "description": hint}

    return Tool(
        name=f"{spec.name}.{remote.name}",
        description=policy.description or remote.description or remote.name,
        handler=handler,
        parameters=parameters,
        required=remote.required,
        min_agency=policy.agency,
        mutates=policy.mutates,
        confirm_label=policy.confirm_label,
        risk=policy.risk)


def mount_all(registry: ToolRegistry,
              manifest: Optional[Mapping[str, BridgeSpec]] = None,
              connect: Optional[Callable[[BridgeSpec], McpClient]] = None,
              path: Optional[str] = None) -> List[MountReport]:
    """Mount every enabled bridge. A bridge that is not running is a warning.

    JARVIS has to boot with the workshop cold — the SolidWorks bridge lives on
    the other half of a dual boot and is absent more often than present.
    """
    specs = manifest if manifest is not None else load_manifest(path)
    connect = connect or (lambda s: s.connect())
    reports: List[MountReport] = []
    for spec in specs.values():
        if not spec.enabled:
            continue
        try:
            client = connect(spec)
        except Exception as exc:                 # unreachable, crashed, absent
            report = MountReport(bridge=spec.name, error=f"{type(exc).__name__}: {exc}")
            log.warning("bridge %s unavailable: %s", spec.name, exc)
        else:
            report = mount(registry, spec, client)
        reports.append(report)
    return reports
