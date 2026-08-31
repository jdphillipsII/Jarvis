"""Real fluid properties, via CoolProp.

Ideal-gas approximations are fine until they aren't, and near-critical CO2 is
exactly where they aren't: at 80 bar and 35 degC, CO2's specific heat is about
29,600 J/kg/K against an ideal-gas value near 840. A design sized on the wrong
one is wrong by a factor of thirty-five.

Two honesty features, in the style of the Atlas physics tier — return a reason
rather than a confident number outside the domain:

* **Two-phase states are refused.** Below the critical pressure, on the
  saturation line, P and T are not independent — they do not determine the
  state, and any single number returned would be a fiction.
* **Near-critical states are flagged.** Properties there vary violently with
  small changes in either variable, so the caller is told the answer is
  sensitive rather than being left to assume it is robust.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .units import Quantity, UnitError, parse_quantity

# CoolProp key -> (friendly name, SI unit)
PROPERTIES: Dict[str, tuple] = {
    "D": ("density", "kg/m^3"),
    "C": ("cp", "J/kg/K"),
    "CVMASS": ("cv", "J/kg/K"),
    "H": ("enthalpy", "J/kg"),
    "S": ("entropy", "J/kg/K"),
    "V": ("viscosity", "Pa*s"),
    "L": ("conductivity", "W/m/K"),
    "PRANDTL": ("prandtl", "1"),
    "A": ("speed_of_sound", "m/s"),
    "Z": ("compressibility", "1"),
}

# What a thermal engineer actually wants at a state point.
DEFAULT_SET = ("D", "C", "V", "L", "PRANDTL", "H")

NEAR_CRITICAL_P = 0.15      # within 15% of Pcrit
NEAR_CRITICAL_T = 0.05      # within 5% of Tcrit


class FluidError(ValueError):
    """Unavailable backend, unknown fluid, or a state that is not determined."""


def available() -> bool:
    try:
        import CoolProp.CoolProp  # noqa: F401
        return True
    except ImportError:
        return False


def _cp():
    try:
        import CoolProp.CoolProp as CP
        return CP
    except ImportError as exc:
        raise FluidError(
            "CoolProp is not installed — uv pip install CoolProp") from exc


@dataclass
class FluidState:
    fluid: str
    pressure_pa: float
    temperature_k: float
    values: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "fluid": self.fluid,
            "pressure": f"{self.pressure_pa / 1e5:.4g} bar",
            "temperature": f"{self.temperature_k - 273.15:.4g} degC",
        }
        for name, value in self.values.items():
            unit = next((u for n, u in PROPERTIES.values() if n == name), "")
            out[name] = f"{value:.6g} {unit}".strip()
        if self.notes:
            out["notes"] = self.notes
        return out


def critical(fluid: str) -> Dict[str, float]:
    CP = _cp()
    try:
        return {"T_crit_k": CP.PropsSI("Tcrit", fluid),
                "P_crit_pa": CP.PropsSI("Pcrit", fluid)}
    except Exception as exc:
        raise FluidError(f"unknown fluid '{fluid}': {exc}") from exc


def _state_is_determined(CP, fluid: str, p_pa: float, t_k: float) -> Optional[str]:
    """None if P,T determine the state; otherwise why they don't."""
    crit = critical(fluid)
    if p_pa >= crit["P_crit_pa"]:
        return None                      # supercritical: always single phase
    try:
        t_sat = CP.PropsSI("T", "P", p_pa, "Q", 0, fluid)
    except Exception:
        return None                      # no saturation line here; let CoolProp judge
    if abs(t_k - t_sat) < 0.01:
        return (f"at {p_pa / 1e5:.4g} bar the saturation temperature is "
                f"{t_sat - 273.15:.4g} degC — on that line pressure and "
                f"temperature do not determine the state, so specify quality "
                f"or move off saturation")
    return None


def _warnings(fluid: str, p_pa: float, t_k: float) -> List[str]:
    crit = critical(fluid)
    notes = []
    dp = abs(p_pa - crit["P_crit_pa"]) / crit["P_crit_pa"]
    dt = abs(t_k - crit["T_crit_k"]) / crit["T_crit_k"]
    if dp < NEAR_CRITICAL_P and dt < NEAR_CRITICAL_T:
        notes.append(
            "near-critical: properties vary steeply here, so this answer is "
            "sensitive to small changes in pressure or temperature")
    return notes


def state(fluid: str, pressure: Any, temperature: Any,
          properties: Optional[List[str]] = None) -> FluidState:
    """Properties at a (P, T) state point. Pressure and temperature accept
    dimensional strings — "80 bar", "35 degC"."""
    CP = _cp()
    try:
        p = parse_quantity(pressure).to("Pa").value
        t = parse_quantity(temperature).to("K").value
    except UnitError as exc:
        raise FluidError(str(exc)) from exc

    undetermined = _state_is_determined(CP, fluid, p, t)
    if undetermined:
        raise FluidError(undetermined)

    keys = list(properties) if properties else list(DEFAULT_SET)
    out = FluidState(fluid, p, t, notes=_warnings(fluid, p, t))
    for key in keys:
        if key not in PROPERTIES:
            raise FluidError(f"unknown property '{key}'; "
                             f"known: {', '.join(sorted(PROPERTIES))}")
        name, _ = PROPERTIES[key]
        try:
            out.values[name] = CP.PropsSI(key, "P", p, "T", t, fluid)
        except Exception as exc:
            raise FluidError(f"{fluid} at {p/1e5:.4g} bar, {t-273.15:.4g} degC: "
                             f"{exc}") from exc
    return out


def pseudocritical_temperature(fluid: str, pressure: Any) -> Quantity:
    """The temperature where cp peaks at this pressure.

    Above the critical pressure there is no phase change, but cp still has a
    sharp maximum — the pseudocritical or Widom line. It is the temperature a
    near-critical loop is designed around, and it moves with pressure.
    """
    CP = _cp()
    try:
        p = parse_quantity(pressure).to("Pa").value
    except UnitError as exc:
        raise FluidError(str(exc)) from exc

    crit = critical(fluid)
    if p < crit["P_crit_pa"]:
        raise FluidError(
            f"{p/1e5:.4g} bar is below {fluid}'s critical pressure "
            f"({crit['P_crit_pa']/1e5:.4g} bar) — below it there is a real "
            f"phase change, not a pseudocritical point")

    # Coarse scan then golden-section refine; cp is unimodal along this line.
    lo, hi = crit["T_crit_k"] - 5.0, crit["T_crit_k"] + 120.0
    best_t, best_cp = lo, -1.0
    for i in range(120):
        t = lo + (hi - lo) * i / 119
        try:
            c = CP.PropsSI("C", "P", p, "T", t, fluid)
        except Exception:
            continue
        if c > best_cp:
            best_t, best_cp = t, c
    step = (hi - lo) / 119
    a, b = best_t - step, best_t + step
    for _ in range(40):
        m1, m2 = a + (b - a) / 3, b - (b - a) / 3
        try:
            c1 = CP.PropsSI("C", "P", p, "T", m1, fluid)
            c2 = CP.PropsSI("C", "P", p, "T", m2, fluid)
        except Exception:
            break
        if c1 < c2:
            a = m1
        else:
            b = m2
    return Quantity((a + b) / 2 - 273.15, "degC")
