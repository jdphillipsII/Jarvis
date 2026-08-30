import pytest
from core.units import (DIMENSIONS, Quantity, UnitError, convert,
                        dimension_named, parse_quantity, parse_unit)


# ---- parsing units ----

def test_base_and_prefixed():
    assert parse_unit("m")[0] == 1.0
    assert parse_unit("km")[0] == 1000.0
    assert parse_unit("mm")[0] == pytest.approx(1e-3)
    assert parse_unit("kg")[0] == 1.0
    assert parse_unit("g")[0] == pytest.approx(1e-3)


def test_compound_expressions():
    assert parse_unit("m/s^2")[1] == DIMENSIONS["acceleration"]
    assert parse_unit("W/cm^2")[1] == parse_unit("W/m^2")[1]
    assert parse_unit("kW*h")[1] == DIMENSIONS["energy"]


def test_dimensionless_spellings():
    for s in ("1", "rad", "%"):
        assert parse_unit(s)[1].is_dimensionless


def test_unknown_symbol_names_itself():
    with pytest.raises(UnitError, match="flurbles"):
        parse_unit("flurbles")


# ---- the affine trap ----

def test_celsius_is_an_offset_not_a_scaling():
    """20 degC is 293.15 K. A factor-only conversion would say 20 K."""
    assert convert("20 degC", "K").value == pytest.approx(293.15)
    assert convert("293.15 K", "degC").value == pytest.approx(20.0)


def test_fahrenheit():
    assert convert("212 degF", "degC").value == pytest.approx(100.0)
    assert convert("32 degF", "degC").value == pytest.approx(0.0)


@pytest.mark.parametrize("alias", ["°C", "celsius"])
def test_celsius_aliases(alias):
    assert convert(f"20 {alias}", "K").value == pytest.approx(293.15)


def test_offset_units_are_refused_inside_expressions():
    """A DIFFERENCE of 1 degC is 1 K, so W/degC is a category error."""
    with pytest.raises(UnitError, match="offset unit"):
        parse_unit("W/degC")


# ---- conversion ----

@pytest.mark.parametrize("frm,to,expect", [
    ("80 bar", "Pa", 8e6), ("1 inch", "mm", 25.4), ("1 h", "s", 3600.0),
    ("1 L", "m^3", 1e-3), ("14.5037738 psi", "bar", 1.0)])
def test_conversions(frm, to, expect):
    assert convert(frm, to).value == pytest.approx(expect, rel=1e-6)


def test_incompatible_dimensions_are_refused():
    with pytest.raises(UnitError, match="cannot convert"):
        convert("5 kg", "m")


def test_round_trip():
    q = parse_quantity("3.5 mm")
    assert q.to("m").to("mm").value == pytest.approx(3.5)


# ---- quantity parsing ----

@pytest.mark.parametrize("raw,value,unit", [
    ("3 mm", 3.0, "mm"), ("3mm", 3.0, "mm"), ("-2.5e3 Pa", -2500.0, "Pa"),
    (".5 m", 0.5, "m")])
def test_quantity_strings(raw, value, unit):
    q = parse_quantity(raw)
    assert q.value == pytest.approx(value) and q.unit == unit


def test_bare_number_is_dimensionless():
    assert parse_quantity(7).dim.is_dimensionless


def test_object_form():
    q = parse_quantity({"value": 80, "unit": "bar"})
    assert q.si == pytest.approx(8e6)


def test_a_bad_unit_is_caught_at_parse_not_at_use():
    with pytest.raises(UnitError):
        parse_quantity("3 flurbles")


@pytest.mark.parametrize("junk", [None, [], True])
def test_garbage_refused(junk):
    with pytest.raises(UnitError):
        parse_quantity(junk)


# ---- named dimensions ----

def test_named_dimensions_match_their_units():
    assert dimension_named("pressure") == parse_unit("Pa")[1]
    assert dimension_named("thermal_resistance") == parse_unit("K/W")[1]
    assert dimension_named("thermal_conductivity") == parse_unit("W/m/K")[1]
    assert dimension_named("volume_flow") == parse_unit("m^3/s")[1]


def test_unknown_dimension_lists_the_known_ones():
    with pytest.raises(UnitError, match="known:"):
        dimension_named("spookiness")
