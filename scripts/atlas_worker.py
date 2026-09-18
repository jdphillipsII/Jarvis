#!/usr/bin/env python3
"""Runs the Atlas physics tier, out of process, one job per invocation.

Out of process for a reason that is not fastidiousness: **both projects own a
package called `core`.** Atlas's `atlas_cad.evolve` does
`from core.evolution.nsga2 import ...`, and with JARVIS on the path that
resolves to JARVIS's `core`, which has no `evolution`. There is no import order
that satisfies both, so the two live in separate interpreters and speak JSON.

Three things fall out of that which are worth having anyway: scipy and numpy
are not imported by the voice loop at startup, an exception in the physics tier
cannot take down the assistant, and the call can be given a timeout.

Protocol — one JSON object in, one JSON object out:

    {"document": {...}, "analyses": [...], "conditions": {...}, "spec": "..."}
    {"ok": bool, "findings": [...], "results": {...}, "skipped": {...}}
"""
import json
import os
import sys


def _adapters():
    from atlas_cad.flow_network import evaluate_loop_network
    from atlas_cad.part import load_part
    from atlas_cad.structural import evaluate_cantilever
    from atlas_cad.thermal import evaluate_cold_plate
    from atlas_cad.tier2_fd import cross_check
    from atlas_cad.verify import verify_part

    def _fields(result):
        return {f: getattr(result, f) for f in result.__dataclass_fields__}

    def verify(part, conditions):
        """`dark_regions` is the field to read: a certificate that passes every
        rule it has and names four aspects it has no rule for is saying
        something a bare pass/fail never would."""
        certificate = verify_part(part, spec=conditions.get("spec", "unspecified"),
                                  backend="analytic")
        checks = [{"rule": c.rule, "verdict": c.verdict, "margin": c.margin,
                   "detail": c.detail} for c in certificate.checks]
        return {"design": certificate.design,
                "passed": sum(1 for c in checks if c["verdict"] == "pass"),
                "failed": [c for c in checks if c["verdict"] != "pass"],
                "checks": checks,
                "dark_regions": [{"aspect": d.aspect, "reason": d.reason}
                                 for d in certificate.dark_regions]}

    return {
        "atlas_cad.verify_part": (verify, ()),
        "atlas_cad.thermal.evaluate_cold_plate": (
            lambda part, c: _fields(evaluate_cold_plate(
                part, flow_m3_s=c["flow_m3_s"])), ("flow_m3_s",)),
        # An independent 2-D finite-difference method whose verdict is
        # agree / refine / disagree — a second opinion that can contradict the
        # first, not a confirmation dressed up as one.
        "atlas_cad.tier2_fd": (lambda part, c: _fields(cross_check(part)), ()),
        "atlas_cad.structural.evaluate_cantilever": (
            lambda part, c: _fields(evaluate_cantilever(
                part, load_n=c["load_n"])), ("load_n",)),
        # The one that detects the straight-channel plate's headline failure
        # mode, and the only analysis here needing a second part: without a
        # manifold there is nothing to distribute the flow unevenly.
        "atlas_cad.flow_network.evaluate_loop_network": (
            lambda part, c: _network(part, c), ("flow_m3_s", "manifold_document")),
    }


def _network(plate, conditions):
    from atlas_cad.flow_network import evaluate_loop_network
    from atlas_cad.part import load_part

    manifold, findings = load_part(dict(conditions["manifold_document"]))
    if manifold is None:
        return {"valid": False,
                "why": "manifold document did not load: "
                       + "; ".join(str(f) for f in findings)}
    result = evaluate_loop_network(plate, manifold,
                                   total_flow_m3_s=conditions["flow_m3_s"])
    out = {f: getattr(result, f) for f in result.__dataclass_fields__}
    flows = out.pop("channel_flows_m3_s", None) or []
    if flows:
        # The list itself is noise at n=32; the spread is the finding.
        out["channels"] = len(flows)
        out["starved_channel_l_per_min"] = min(flows) * 60000.0
        out["best_channel_l_per_min"] = max(flows) * 60000.0
    return out


def run(job):
    from atlas_cad.part import load_part

    part, findings = load_part(dict(job.get("document") or {}))
    out = {"ok": part is not None,
           "findings": [str(f) for f in findings],
           "results": {}, "skipped": {}}
    if part is None:
        return out

    conditions = dict(job.get("conditions") or {})
    conditions.setdefault("spec", job.get("spec", "unspecified"))
    adapters = _adapters()
    for name in job.get("analyses") or []:
        adapter = adapters.get(name)
        if adapter is None:
            out["skipped"][name] = "no adapter in scripts/atlas_worker.py"
            continue
        call, needs = adapter
        missing = [n for n in needs if n not in conditions]
        if missing:
            # Named, never substituted for. An analysis that could not run is
            # not an analysis that passed.
            out["skipped"][name] = f"needs {', '.join(missing)}"
            continue
        try:
            out["results"][name] = call(part, conditions)
        except Exception as exc:
            out["skipped"][name] = f"{type(exc).__name__}: {exc}"
    return out


def main():
    atlas_root = os.environ.get("ATLAS_ROOT", "")
    if atlas_root:
        # Ahead of everything, so Atlas's `core` wins inside this interpreter.
        sys.path.insert(0, atlas_root)
    job = json.loads(sys.stdin.read() or "{}")
    if job.get("probe"):
        import atlas_cad.part  # noqa: F401
        print(json.dumps({"ok": True}))
        return
    try:
        print(json.dumps(run(job), default=str))
    except Exception as exc:
        print(json.dumps({"ok": False, "findings": [f"{type(exc).__name__}: {exc}"],
                          "results": {}, "skipped": {}}))


if __name__ == "__main__":
    main()
