"""The allowlist. Fail closed: unknown intent -> rejected, always.

Loads intents/registry.yaml. Every actuator consults this before acting, so
adding a capability is a config change, not a code change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import yaml

from .intent import Intent

_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "intents", "registry.yaml")


@dataclass(frozen=True)
class IntentSpec:
    name: str
    desc: str = ""
    floor: float = 1.0          # confidence below this is refused
    args: tuple = ()


class Rejection(str):
    """Truthy reason string explaining why an intent was refused."""


class Registry:
    def __init__(self, specs: Dict[str, IntentSpec]):
        self._specs = specs

    # ---- construction ----
    @classmethod
    def load(cls, path: Optional[str] = None) -> "Registry":
        with open(path or _DEFAULT) as fh:
            raw = yaml.safe_load(fh) or {}
        specs: Dict[str, IntentSpec] = {}
        for group, entries in raw.items():
            if not isinstance(entries, dict):
                continue
            for name, meta in entries.items():
                meta = meta or {}
                if not name.startswith(f"{group}."):
                    raise ValueError(f"{name!r} must be namespaced under {group!r}")
                specs[name] = IntentSpec(
                    name=name,
                    desc=meta.get("desc", ""),
                    floor=float(meta.get("floor", 1.0)),
                    args=tuple(meta.get("args", []) or []),
                )
        return cls(specs)

    # ---- queries ----
    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)

    def names(self) -> Iterable[str]:
        return sorted(self._specs)

    def spec(self, name: str) -> Optional[IntentSpec]:
        return self._specs.get(name)

    # ---- the gate ----
    def check(self, intent: Intent) -> Optional[Rejection]:
        """None means 'permitted'. A Rejection means refused, with the reason."""
        spec = self._specs.get(intent.intent)
        if spec is None:
            return Rejection(f"unknown intent {intent.intent!r} (not in registry)")
        if intent.confidence < spec.floor:
            return Rejection(
                f"{intent.intent} confidence {intent.confidence:.2f} < floor {spec.floor:.2f}")
        missing = [a for a in spec.args if a not in intent.args]
        if missing:
            return Rejection(f"{intent.intent} missing required args: {missing}")
        return None
