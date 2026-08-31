import pytest
from core import fluids
from core.fluids import FluidError, critical, pseudocritical_temperature, state

pytestmark = pytest.mark.skipif(not fluids.available(),
                                reason="CoolProp not installed")


# ---- the reason this exists ----

def test_near_critical_co2_is_nothing_like_an_ideal_gas():
    """At the cooling loop's operating point, cp is ~35x the ideal-gas value.
    A design sized on the wrong one is wrong by that factor."""
    cp = state("CO2", "80 bar", "35 degC").values["cp"]
    assert cp > 20000                      # ideal gas would be ~840 J/kg/K


def test_dimensional_inputs_are_accepted_and_converted():
    a = state("CO2", "80 bar", "35 degC")
    b = state("CO2", "8e6 Pa", "308.15 K")
    assert a.values["density"] == pytest.approx(b.values["density"])


def test_wrong_dimension_is_refused():
    with pytest.raises(FluidError, match="cannot convert"):
        state("CO2", "35 degC", "80 bar")   # arguments swapped


# ---- honesty about the domain ----

def test_two_phase_states_are_refused_not_guessed():
    """On the saturation line P and T do not determine the state."""
    t_sat_c = state("Water", "1 bar", "50 degC")     # safely liquid
    assert t_sat_c.values["density"] > 900
    with pytest.raises(FluidError, match="do not determine the state"):
        state("Water", "1.01325 bar", "99.9743 degC")


def test_near_critical_states_are_flagged():
    assert any("near-critical" in n
               for n in state("CO2", "75 bar", "32 degC").notes)


def test_ordinary_states_are_not_flagged():
    assert state("Water", "1 bar", "20 degC").notes == []


def test_unknown_fluid_names_itself():
    with pytest.raises(FluidError, match="unobtainium"):
        critical("unobtainium")


def test_unknown_property_lists_the_known_ones():
    with pytest.raises(FluidError, match="known:"):
        state("CO2", "80 bar", "35 degC", properties=["SPOOKINESS"])


# ---- pseudocritical line ----

def test_co2_critical_point():
    c = critical("CO2")
    assert c["T_crit_k"] == pytest.approx(304.13, abs=0.1)
    assert c["P_crit_pa"] / 1e5 == pytest.approx(73.77, abs=0.1)


def test_pseudocritical_rises_with_pressure():
    t75 = pseudocritical_temperature("CO2", "75 bar").value
    t80 = pseudocritical_temperature("CO2", "80 bar").value
    t100 = pseudocritical_temperature("CO2", "100 bar").value
    assert t75 < t80 < t100
    assert 30 < t75 < 34                   # just above the critical temperature


def test_pseudocritical_is_meaningless_below_critical_pressure():
    with pytest.raises(FluidError, match="below"):
        pseudocritical_temperature("CO2", "50 bar")


def test_cp_really_does_peak_at_the_reported_temperature():
    """Verify the optimiser rather than trusting it."""
    tpc = pseudocritical_temperature("CO2", "80 bar").value
    at_peak = state("CO2", "80 bar", f"{tpc} degC").values["cp"]
    for offset in (-8, -3, 3, 8):
        assert state("CO2", "80 bar", f"{tpc + offset} degC").values["cp"] < at_peak
