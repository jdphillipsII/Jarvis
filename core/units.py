"""Dimensional types for tool arguments.

Ported from Atlas's `atlas_spec/units.py` — seven SI base dimensions with
Fraction exponents and a practical unit-string parser. Zero dependencies.

The reason this exists here: a tool argument declared `{"type": "number"}` will
happily accept 45 when the handler wanted kelvin and the model was thinking in
Celsius. Declaring `{"type": "quantity", "dimension": "temperature"}` turns that
into a refusal at the call boundary instead of a plausible wrong answer three
steps downstream.

Two additions beyond the Atlas original:

* **Affine units.** degC and degF are offsets, not scalings, so a factor-only
  conversion is silently wrong — 20 degC is 293.15 K, not 20 K. They are handled
  explicitly and are absolute-temperature only: a *difference* of 5 degC is 5 K,
  so compound expressions like W/K must use K.
* **Named dimensions**, so a schema can say "temperature" rather than spell out
  an exponent vector.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Dict, Optional, Tuple

_BASE: Tuple[str, ...] = ("kg", "m", "s", "A", "K", "mol", "cd")
_N = len(_BASE)


class UnitError(ValueError):
    """Unparseable unit, or a conversion between incompatible dimensions."""


@dataclass(frozen=True)
class Dim:
    exponents: Tuple[Fraction, ...]

    def __post_init__(self) -> None:
        if len(self.exponents) != _N:
            raise ValueError(f"Dim needs {_N} exponents, got {len(self.exponents)}")

    def __mul__(self, o: "Dim") -> "Dim":
        return Dim(tuple(a + b for a, b in zip(self.exponents, o.exponents)))

    def __truediv__(self, o: "Dim") -> "Dim":
        return Dim(tuple(a - b for a, b in zip(self.exponents, o.exponents)))

    def __pow__(self, p) -> "Dim":
        f = Fraction(p)
        return Dim(tuple(a * f for a in self.exponents))

    @property
    def is_dimensionless(self) -> bool:
        return all(e == 0 for e in self.exponents)

    def __str__(self) -> str:
        if self.is_dimensionless:
            return "1"
        num, den = [], []
        for sym, e in zip(_BASE, self.exponents):
            if e == 0:
                continue
            (num if e > 0 else den).append(
                sym if abs(e) == 1 else f"{sym}^{abs(e)}")
        out = "*".join(num) if num else "1"
        return out + ("/" + "/".join(den) if den else "")


def _dim(**exps) -> Dim:
    vec = [Fraction(0)] * _N
    for sym, e in exps.items():
        vec[_BASE.index(sym)] = Fraction(e)
    return Dim(tuple(vec))


DIMENSIONLESS = _dim()

# symbol -> (SI factor, Dim). Extend by appending; never repurpose a symbol.
_UNITS: Dict[str, Tuple[float, Dim]] = {
    "kg": (1.0, _dim(kg=1)), "m": (1.0, _dim(m=1)), "s": (1.0, _dim(s=1)),
    "A": (1.0, _dim(A=1)), "K": (1.0, _dim(K=1)), "mol": (1.0, _dim(mol=1)),
    "cd": (1.0, _dim(cd=1)),
    "g": (1e-3, _dim(kg=1)),                     # gram is the prefixable symbol
    "1": (1.0, DIMENSIONLESS), "rad": (1.0, DIMENSIONLESS),
    "sr": (1.0, DIMENSIONLESS), "%": (0.01, DIMENSIONLESS),
    "Hz": (1.0, _dim(s=-1)), "N": (1.0, _dim(kg=1, m=1, s=-2)),
    "Pa": (1.0, _dim(kg=1, m=-1, s=-2)), "J": (1.0, _dim(kg=1, m=2, s=-2)),
    "W": (1.0, _dim(kg=1, m=2, s=-3)), "C": (1.0, _dim(A=1, s=1)),
    "V": (1.0, _dim(kg=1, m=2, s=-3, A=-1)),
    "F": (1.0, _dim(kg=-1, m=-2, s=4, A=2)),
    "ohm": (1.0, _dim(kg=1, m=2, s=-3, A=-2)),
    "S": (1.0, _dim(kg=-1, m=-2, s=3, A=2)),
    "Wb": (1.0, _dim(kg=1, m=2, s=-2, A=-1)), "T": (1.0, _dim(kg=1, s=-2, A=-1)),
    "H": (1.0, _dim(kg=1, m=2, s=-2, A=-2)),
    "L": (1e-3, _dim(m=3)), "min": (60.0, _dim(s=1)), "h": (3600.0, _dim(s=1)),
    "day": (86400.0, _dim(s=1)),
    "eV": (1.602176634e-19, _dim(kg=1, m=2, s=-2)),
    "bar": (1e5, _dim(kg=1, m=-1, s=-2)),
    "atm": (101325.0, _dim(kg=1, m=-1, s=-2)),
    "psi": (6894.757293168, _dim(kg=1, m=-1, s=-2)),
    "inch": (0.0254, _dim(m=1)), "ft": (0.3048, _dim(m=1)),
}

# Affine: si = value * scale + offset. Absolute temperature only — a DIFFERENCE
# of 5 degC is 5 K, so compound expressions (W/K, K/W) must use K.
_AFFINE: Dict[str, Tuple[float, float, Dim]] = {
    "degC": (1.0, 273.15, _dim(K=1)),
    "degF": (5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0, _dim(K=1)),
}
_AFFINE_ALIASES = {"°C": "degC", "C°": "degC", "celsius": "degC",
                   "°F": "degF", "fahrenheit": "degF"}

_PREFIXES: Dict[str, float] = {
    "da": 1e1, "Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12,
    "G": 1e9, "M": 1e6, "k": 1e3, "h": 1e2, "d": 1e-1, "c": 1e-2,
    "m": 1e-3, "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
    "a": 1e-18, "z": 1e-21, "y": 1e-24,
}

_TOKEN = re.compile(r"^([A-Za-zµ%°]+|1)(?:\s*(?:\^|\*\*)\s*([+-]?\d+))?$")

# Named dimensions, so a schema says "pressure" rather than an exponent vector.
DIMENSIONS: Dict[str, Dim] = {
    "dimensionless": DIMENSIONLESS,
    "length": _dim(m=1), "area": _dim(m=2), "volume": _dim(m=3),
    "mass": _dim(kg=1), "time": _dim(s=1), "temperature": _dim(K=1),
    "current": _dim(A=1), "amount": _dim(mol=1),
    "force": _dim(kg=1, m=1, s=-2), "pressure": _dim(kg=1, m=-1, s=-2),
    "energy": _dim(kg=1, m=2, s=-2), "power": _dim(kg=1, m=2, s=-3),
    "voltage": _dim(kg=1, m=2, s=-3, A=-1),
    "resistance": _dim(kg=1, m=2, s=-3, A=-2),
    "frequency": _dim(s=-1), "velocity": _dim(m=1, s=-1),
    "acceleration": _dim(m=1, s=-2),
    "mass_flow": _dim(kg=1, s=-1), "volume_flow": _dim(m=3, s=-1),
    "density": _dim(kg=1, m=-3),
    "thermal_resistance": _dim(K=1, kg=-1, m=-2, s=3),      # K/W
    "thermal_conductivity": _dim(kg=1, m=1, s=-3, K=-1),    # W/(m*K)
}


def _resolve(sym: str) -> Tuple[float, Dim]:
    if sym in _UNITS:
        return _UNITS[sym]
    # Explain rather than say "unknown": degC inside W/degC is a category
    # error, not a typo, and the message should teach the difference.
    if _AFFINE_ALIASES.get(sym, sym) in _AFFINE:
        raise UnitError(
            f"'{sym}' is an offset unit and cannot appear in an expression — "
            f"use K (a difference of 1 degC is 1 K)")
    for plen in (2, 1):
        prefix, rest = sym[:plen], sym[plen:]
        if prefix in _PREFIXES and rest in _UNITS and rest != "1":
            factor, dim = _UNITS[rest]
            return (_PREFIXES[prefix] * factor, dim)
    raise UnitError(f"unknown unit symbol '{sym}'")


def affine_of(text: str) -> Optional[Tuple[float, float, Dim]]:
    """(scale, offset, dim) if this is a bare affine unit, else None."""
    key = _AFFINE_ALIASES.get(text.strip(), text.strip())
    return _AFFINE.get(key)


def parse_unit(text: str) -> Tuple[float, Dim]:
    """Parse "m/s^2", "kW*h", "W/cm^2", "1" -> (SI factor, Dim).

    Affine units are rejected here on purpose: they have no single factor, so
    they are only meaningful as a standalone quantity, never inside a compound.
    """
    if not isinstance(text, str) or not text.strip():
        raise UnitError("empty unit string")
    if affine_of(text) is not None:
        raise UnitError(
            f"'{text.strip()}' is an offset unit and cannot be used in an "
            f"expression — use K (a difference of 1 degC is 1 K)")
    s = text.replace("·", "*").replace("**", "^").strip()
    parts = re.split(r"\s*([*/])\s*", s)
    factor, dim, op = 1.0, DIMENSIONLESS, "*"
    for i, part in enumerate(parts):
        if i % 2 == 1:
            op = part
            continue
        m = _TOKEN.match(part.strip())
        if not m:
            raise UnitError(f"cannot parse unit token '{part}' in '{text}'")
        f, d = _resolve(m.group(1))
        exp = int(m.group(2)) if m.group(2) is not None else 1
        f, d = f ** exp, d ** exp
        if op == "*":
            factor, dim = factor * f, dim * d
        else:
            factor, dim = factor / f, dim / d
    return factor, dim


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str

    @property
    def si(self) -> float:
        """Magnitude in SI base units."""
        aff = affine_of(self.unit)
        if aff:
            scale, offset, _ = aff
            return self.value * scale + offset
        return self.value * parse_unit(self.unit)[0]

    @property
    def dim(self) -> Dim:
        aff = affine_of(self.unit)
        return aff[2] if aff else parse_unit(self.unit)[1]

    def to(self, unit: str) -> "Quantity":
        aff = affine_of(unit)
        target_dim = aff[2] if aff else parse_unit(unit)[1]
        if self.dim != target_dim:
            raise UnitError(
                f"cannot convert {self.unit} ({self.dim}) to {unit} ({target_dim})")
        if aff:
            scale, offset, _ = aff
            return Quantity((self.si - offset) / scale, unit)
        return Quantity(self.si / parse_unit(unit)[0], unit)

    def __str__(self) -> str:
        return f"{self.value:g} {self.unit}"


_QTY = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*$")


def parse_quantity(text: Any) -> Quantity:
    """Accept "3 mm", "3mm", 3 (dimensionless), or {"value": 3, "unit": "mm"}."""
    if isinstance(text, Quantity):
        return text
    if isinstance(text, dict):
        if "value" not in text:
            raise UnitError("quantity object needs a 'value'")
        return Quantity(float(text["value"]), str(text.get("unit", "1")))
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return Quantity(float(text), "1")
    if not isinstance(text, str):
        raise UnitError(f"cannot read a quantity from {type(text).__name__}")
    m = _QTY.match(text)
    if not m:
        raise UnitError(f"cannot parse quantity '{text}'")
    unit = m.group(2) or "1"
    q = Quantity(float(m.group(1)), unit)
    q.dim          # validate the unit now rather than at use
    return q


def convert(value: Any, to_unit: str) -> Quantity:
    return parse_quantity(value).to(to_unit)


def dimension_named(name: str) -> Dim:
    if name not in DIMENSIONS:
        raise UnitError(f"unknown dimension '{name}'; "
                        f"known: {', '.join(sorted(DIMENSIONS))}")
    return DIMENSIONS[name]
