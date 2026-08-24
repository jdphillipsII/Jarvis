"""Watcher registry and a dispatcher that cannot be taken down by one watcher.

Two patterns lifted from Axon and deliberately kept apart, because it got this
split right: the registry is a dumb list (registering twice is a silent no-op,
which makes double-import safe), and ALL failure isolation lives in the
dispatcher. A watcher that raises, hangs, or returns garbage costs its own slot
and nothing else.

The timeout matters more than it looks. `sensors` on a wedged i2c bus or a
journald query against a corrupt ring buffer will block forever, and without a
per-source budget one bad watcher silently stops all proactive intelligence.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .observation import Observation

log = logging.getLogger("jarvis.sources")

Watcher = Callable[[], List[Observation]]

_SOURCES: Dict[str, "SourceSpec"] = {}


@dataclass(frozen=True)
class SourceSpec:
    name: str
    fn: Watcher
    interval_s: float = 60.0
    timeout_s: float = 2.0


def source(name: str, *, interval_s: float = 60.0, timeout_s: float = 2.0):
    """Decorator. Registering the same name twice is a no-op, not an error."""
    def deco(fn: Watcher) -> Watcher:
        if name not in _SOURCES:
            _SOURCES[name] = SourceSpec(name, fn, interval_s, timeout_s)
        return fn
    return deco


def get_sources() -> List[SourceSpec]:
    return list(_SOURCES.values())


def clear_sources() -> None:
    _SOURCES.clear()


@dataclass
class CollectResult:
    observations: List[Observation] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)   # (name, reason)
    ran: List[str] = field(default_factory=list)


class SourceRunner:
    """Runs due watchers concurrently, each on its own timeout budget."""

    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 max_workers: int = 4):
        self._clock = clock
        self._last: Dict[str, float] = {}
        self._pool = ThreadPoolExecutor(max_workers=max_workers,
                                        thread_name_prefix="jarvis-watch")

    def due(self, specs: List[SourceSpec]) -> List[SourceSpec]:
        now = self._clock()
        return [s for s in specs
                if now - self._last.get(s.name, float("-inf")) >= s.interval_s]

    def collect(self, specs: Optional[List[SourceSpec]] = None) -> CollectResult:
        specs = self.due(specs if specs is not None else get_sources())
        result = CollectResult()
        if not specs:
            return result

        futures = {self._pool.submit(s.fn): s for s in specs}
        for fut, spec in futures.items():
            self._last[spec.name] = self._clock()
            result.ran.append(spec.name)
            try:
                obs = fut.result(timeout=spec.timeout_s)
            except FutureTimeout:
                result.failed.append((spec.name, "timeout"))
                fut.cancel()
                log.warning("watcher %s timed out after %.1fs", spec.name, spec.timeout_s)
                continue
            except Exception as exc:
                result.failed.append((spec.name, f"error: {exc}"))
                log.exception("watcher %s failed", spec.name)
                continue
            if not obs:
                continue
            for o in obs:
                if isinstance(o, Observation):
                    result.observations.append(o)
                else:
                    result.failed.append((spec.name, "returned a non-Observation"))
        return result

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)
