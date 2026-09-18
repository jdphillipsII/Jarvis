"""Reaching the Atlas physics tier from JARVIS.

The archetype library says which analyses apply to a shape. This runs them, by
handing a part document to `scripts/atlas_worker.py` in a separate interpreter.

Separate because **both projects own a package called `core`** — Atlas's
`atlas_cad.evolve` does `from core.evolution.nsga2 import ...`, and with JARVIS
on the path that resolves to *our* `core`. There is no import order that
satisfies both. The suite doc called this tier "in-process"; it cannot be,
short of renaming a package in one of the two projects.

Optional in the way `fluids.py` is optional: if Atlas is not on the machine,
the tools are never registered and the model is never told they exist, rather
than being offered something that fails when called.

The physics, the checker battery and the certificate are Atlas's, unchanged.
Atlas refuses outside its validity domain instead of extrapolating, and a
wrapper that smoothed that over would be discarding the property worth having.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from typing import Any, Dict, Mapping, Optional, Sequence

log = logging.getLogger("jarvis.atlas")

_DEFAULT_ROOT = "~/atlas-research"
_WORKER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scripts", "atlas_worker.py")
TIMEOUT_S = 120.0          # tier2_fd is a grid solve; it is not instant


class AtlasUnavailable(RuntimeError):
    pass


def root() -> str:
    from .config import cfg
    return os.path.expanduser(cfg("JARVIS_ATLAS_ROOT", _DEFAULT_ROOT))


def _call(job: Mapping[str, Any], timeout_s: float = TIMEOUT_S) -> Dict[str, Any]:
    where = root()
    if not os.path.isdir(where):
        raise AtlasUnavailable(f"no Atlas checkout at {where} — set JARVIS_ATLAS_ROOT")
    environment = {**os.environ, "ATLAS_ROOT": where}
    # The worker must not inherit our PYTHONPATH: that is how our `core` would
    # get in front of Atlas's again.
    environment.pop("PYTHONPATH", None)
    try:
        done = subprocess.run([sys.executable, _WORKER], input=json.dumps(job),
                              capture_output=True, text=True, timeout=timeout_s,
                              env=environment)
    except subprocess.TimeoutExpired as exc:
        raise AtlasUnavailable(f"Atlas did not answer within {timeout_s:g}s") from exc
    if done.returncode != 0 or not done.stdout.strip():
        detail = (done.stderr or "").strip().splitlines()[-1:] or ["no output"]
        raise AtlasUnavailable(f"Atlas worker failed: {detail[0]}")
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        raise AtlasUnavailable("Atlas worker did not answer with JSON") from exc


def available() -> bool:
    try:
        return bool(_call({"probe": True}, timeout_s=60.0).get("ok"))
    except Exception as exc:
        log.debug("atlas unavailable: %s", exc)
        return False


def evaluate(document: Mapping[str, Any],
             analyses: Sequence[str] = (),
             conditions: Optional[Mapping[str, Any]] = None,
             spec: str = "unspecified") -> Dict[str, Any]:
    """Load the document through Atlas's loader, then run the named analyses.

    Returns `{ok, findings, results, skipped}`. An analysis with no adapter, or
    one whose operating condition was not supplied, appears in `skipped` with
    the reason — never dropped, and certainly never substituted for. An
    analysis that could not run is not an analysis that passed.
    """
    return _call({"document": dict(document), "analyses": list(analyses),
                  "conditions": dict(conditions or {}), "spec": spec})


# `evaluate_cold_plate`'s default `maldistribution_fraction`: the share of mean
# flow it assumes the worst-fed channel gets when computing r_th_worst.
ASSUMED_WORST_FRACTION = 0.7

THERMAL = "atlas_cad.thermal.evaluate_cold_plate"
NETWORK = "atlas_cad.flow_network.evaluate_loop_network"
CROSS = "atlas_cad.tier2_fd"


def consistency(results: Mapping[str, Any]) -> list:
    """Where two analyses of the same part disagree.

    Each analysis is honest on its own and neither knows the other ran. The
    interesting failures live between them: a worst case assumed by one and
    computed by the other, a second method that declines to agree. Nothing here
    adjusts a number — it says which one to distrust and why.
    """
    notes = []
    thermal = results.get(THERMAL) or {}
    network = results.get(NETWORK) or {}
    cross = results.get(CROSS) or {}

    worst = network.get("worst_fraction")
    if thermal.get("valid") and network.get("valid") and worst is not None:
        if worst < ASSUMED_WORST_FRACTION:
            notes.append(
                f"r_th_worst assumes the starved channel carries "
                f"{ASSUMED_WORST_FRACTION:.0%} of mean flow; the flow network "
                f"computes {worst:.0%} for this manifold. The thermal worst "
                f"case is optimistic — it is not a bound.")
        else:
            notes.append(
                f"the flow network's worst channel ({worst:.0%} of mean) is "
                f"within r_th_worst's {ASSUMED_WORST_FRACTION:.0%} assumption")

    gallery = network.get("max_gallery_reynolds")
    if gallery is not None and gallery > 2300:
        notes.append(
            f"gallery Reynolds is {gallery:.0f} — the manifold is turbulent "
            f"even where the channels are laminar, so its pressure figure "
            f"comes from a correlation outside the one the plate was sized on")

    if cross.get("valid") and cross.get("verdict") in ("refine", "disagree"):
        notes.append(
            f"the independent 2-D method says '{cross['verdict']}' at "
            f"{cross.get('deviation', 0):.1%} deviation — the analytic R_th is "
            f"not confirmed")
    return notes
