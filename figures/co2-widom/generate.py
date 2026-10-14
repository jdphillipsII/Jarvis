"""The numbers behind the CO2 heat-capacity vessel.

The figure draws a vessel whose cross-sectional AREA at height T is the
specific heat cp(T) of CO2 at 80 bar. That is not a decorative mapping, it is
an identity: pour energy in and the level rises by dT = dQ / cp(T), so the
volume enclosed up to any level is exactly the enthalpy change from the floor.
The vessel is the integral of its own profile.

Which means the geometry can be checked against physics rather than taste:
integrate the cp profile the vessel is cut from, and it must reproduce
CoolProp's enthalpy. `check` below does that, and the figure prints the error.

Everything here comes from CoolProp's reference equation of state for CO2
(Span & Wagner 1996). Nothing is fitted, smoothed or rounded for looks.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import CoolProp.CoolProp as CP

FLUID = "CO2"
PRESSURE_PA = 80e5                 # 80 bar — the loop's own operating point
T_LOW_C, T_HIGH_C = 20.0, 50.0     # the window the figure shows
STEP_K = 0.05                      # fine enough to resolve the peak

# Ideal-gas cp for CO2 near room temperature, for the contrast the audit drew.
IDEAL_CP = 846.0                   # J/kg/K, CoolProp's ideal-gas limit at 35 C


def _grid() -> List[float]:
    n = int(round((T_HIGH_C - T_LOW_C) / STEP_K)) + 1
    return [T_LOW_C + i * STEP_K for i in range(n)]


def table() -> Dict[str, Any]:
    kelvin = 273.15
    temps = _grid()
    cp = [CP.PropsSI("C", "P", PRESSURE_PA, "T", t + kelvin, FLUID) for t in temps]
    rho = [CP.PropsSI("D", "P", PRESSURE_PA, "T", t + kelvin, FLUID) for t in temps]
    enthalpy = [CP.PropsSI("H", "P", PRESSURE_PA, "T", t + kelvin, FLUID)
                for t in temps]

    peak = max(range(len(cp)), key=lambda i: cp[i])
    t_pc, cp_peak = temps[peak], cp[peak]

    # The vessel: area(T) = cp(T), so radius(T) = sqrt(cp / pi). Normalised so
    # the widest point is 1; the figure scales that to world units.
    radius = [math.sqrt(c / math.pi) for c in cp]
    widest = max(radius)
    profile = [{"t_c": round(t, 4), "r": round(r / widest, 6)}
               for t, r in zip(temps, radius)]

    # The identity the geometry has to satisfy: trapezoid-integrate cp over the
    # window and compare with CoolProp's own enthalpy difference.
    integrated = 0.0
    worst = 0.0
    for i in range(1, len(temps)):
        integrated += 0.5 * (cp[i] + cp[i - 1]) * (temps[i] - temps[i - 1])
        actual = enthalpy[i] - enthalpy[0]
        if actual:
            worst = max(worst, abs(integrated - actual) / abs(actual))

    # Where a real loop actually sits, and what it actually gets. The audit's
    # finding in three numbers: the peak is unreachable, and what you get
    # across a working span is the average, not the maximum.
    def cp_at(t_c: float) -> float:
        return CP.PropsSI("C", "P", PRESSURE_PA, "T", t_c + kelvin, FLUID)

    def mean_cp(a_c: float, b_c: float) -> float:
        return (CP.PropsSI("H", "P", PRESSURE_PA, "T", b_c + kelvin, FLUID)
                - CP.PropsSI("H", "P", PRESSURE_PA, "T", a_c + kelvin, FLUID)) \
            / (b_c - a_c)

    spans = []
    for half_width in (0.5, 2.0, 5.0, 10.0):
        low, high = t_pc - half_width, t_pc + half_width
        spans.append({
            "half_width_k": half_width,
            "low_c": round(low, 3), "high_c": round(high, 3),
            "mean_cp": round(mean_cp(low, high), 1),
            "fraction_of_peak": round(mean_cp(low, high) / cp_peak, 4)})

    return {
        "fluid": FLUID,
        "pressure_bar": PRESSURE_PA / 1e5,
        "coolprop_version": CP.get_global_param_string("version"),
        "equation_of_state": "Span & Wagner 1996 reference EOS for CO2",
        "critical": {
            "t_c": round(CP.PropsSI("Tcrit", "", 0, "", 0, FLUID) - kelvin, 4),
            "p_bar": round(CP.PropsSI("pcrit", "", 0, "", 0, FLUID) / 1e5, 4)},
        "window": {"low_c": T_LOW_C, "high_c": T_HIGH_C, "step_k": STEP_K},
        "pseudocritical": {
            "t_c": round(t_pc, 4),
            "cp_peak": round(cp_peak, 1),
            "rho": round(rho[peak], 3),
            "over_ideal_gas": round(cp_peak / IDEAL_CP, 1)},
        "ideal_gas_cp": IDEAL_CP,
        "edges": {
            "low": {"t_c": T_LOW_C, "cp": round(cp[0], 1),
                    "fraction_of_peak": round(cp[0] / cp_peak, 4)},
            "high": {"t_c": T_HIGH_C, "cp": round(cp[-1], 1),
                     "fraction_of_peak": round(cp[-1] / cp_peak, 4)}},
        "spans": spans,
        "enthalpy_check": {
            "worst_relative_error": round(worst, 9),
            "means": "trapezoid integral of the drawn cp profile against "
                     "CoolProp enthalpy; the vessel's volume IS the enthalpy"},
        "profile": profile,
    }


if __name__ == "__main__":
    import json
    t = table()
    small = {k: v for k, v in t.items() if k != "profile"}
    print(json.dumps(small, indent=1))
    print(f"profile points: {len(t['profile'])}")
