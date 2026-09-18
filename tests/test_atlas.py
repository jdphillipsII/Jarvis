"""The bridge to the Atlas physics tier.

The parts that need Atlas on disk are skipped without it; everything that can
be tested without it, is.
"""
import os

import pytest

from core import atlas

HAVE_ATLAS = os.path.isdir(os.path.expanduser(
    os.environ.get("JARVIS_ATLAS_ROOT", "~/atlas-research")))
needs_atlas = pytest.mark.skipif(not HAVE_ATLAS, reason="no Atlas checkout")


# ---- what happens when Atlas is not there ----

def test_a_missing_checkout_is_a_named_failure_not_an_import_error(monkeypatch):
    monkeypatch.setattr(atlas, "root", lambda: "/nonexistent/atlas")
    with pytest.raises(atlas.AtlasUnavailable, match="JARVIS_ATLAS_ROOT"):
        atlas.evaluate({"part": "x"})


def test_available_is_false_rather_than_raising(monkeypatch):
    monkeypatch.setattr(atlas, "root", lambda: "/nonexistent/atlas")
    assert atlas.available() is False


# ---- between the analyses ----
#      Pure, so it is tested without Atlas at all.

def test_a_worse_real_maldistribution_than_the_thermal_model_assumed_is_flagged():
    """The finding that came out of the first end-to-end run: r_th_worst
    assumes the starved channel gets 70% of mean flow, and the flow network
    computed 65% for this manifold. The conservative number was not
    conservative."""
    notes = atlas.consistency({
        atlas.THERMAL: {"valid": True, "r_th_worst_k_per_w": 0.04},
        atlas.NETWORK: {"valid": True, "worst_fraction": 0.6457}})
    assert any("optimistic — it is not a bound" in n for n in notes)
    assert any("70%" in n and "65%" in n for n in notes)


def test_a_maldistribution_inside_the_assumption_says_so_rather_than_staying_quiet():
    notes = atlas.consistency({
        atlas.THERMAL: {"valid": True},
        atlas.NETWORK: {"valid": True, "worst_fraction": 0.92}})
    assert any("within r_th_worst's" in n for n in notes)


def test_a_turbulent_manifold_under_laminar_channels_is_flagged():
    notes = atlas.consistency({
        atlas.NETWORK: {"valid": True, "max_gallery_reynolds": 7924.0}})
    assert any("turbulent even where the channels are laminar" in n for n in notes)


def test_a_second_method_that_declines_to_agree_is_reported():
    notes = atlas.consistency({
        atlas.CROSS: {"valid": True, "verdict": "disagree", "deviation": 0.31}})
    assert any("not confirmed" in n and "31" in n for n in notes)


def test_an_agreeing_cross_check_adds_no_note():
    assert atlas.consistency({atlas.CROSS: {"valid": True, "verdict": "agree",
                                            "deviation": 0.02}}) == []


def test_nothing_to_compare_produces_nothing():
    assert atlas.consistency({}) == []
    assert atlas.consistency({atlas.THERMAL: {"valid": True}}) == []


# ---- the real chain ----

@needs_atlas
def test_atlas_is_reachable():
    assert atlas.available()


@needs_atlas
def test_an_archetype_instantiates_into_a_document_atlas_accepts():
    """The regression that produced `to_yaml`: load_part rejects unknown
    top-level fields, so instantiate must emit nothing extra."""
    from core.archetypes import Library, instantiate
    archetype = Library.load().get("cold_plate.straight_channel")
    answer = atlas.evaluate(instantiate(archetype), [])
    assert answer["ok"], answer["findings"]
    assert answer["findings"] == []


@needs_atlas
def test_the_archetype_passes_every_rule_the_hand_written_genome_passes():
    """17 and 0, the same as atlas_cad/examples/cold_plate.part.yaml. The first
    run scored 16 and 5 because the archetype hid pattern geometry behind a
    `source` reference; the DFM rules read it off the pattern op."""
    from core.archetypes import Library, instantiate
    archetype = Library.load().get("cold_plate.straight_channel")
    answer = atlas.evaluate(instantiate(archetype), ["atlas_cad.verify_part"])
    certificate = answer["results"]["atlas_cad.verify_part"]
    assert certificate["failed"] == []
    assert certificate["passed"] == 17
    assert certificate["dark_regions"]          # and it says what it could not check


@needs_atlas
def test_an_analysis_missing_its_operating_condition_is_skipped_not_faked():
    from core.archetypes import Library, instantiate
    archetype = Library.load().get("cold_plate.straight_channel")
    answer = atlas.evaluate(instantiate(archetype),
                            ["atlas_cad.thermal.evaluate_cold_plate"])
    assert answer["results"] == {}
    assert "flow_m3_s" in answer["skipped"]["atlas_cad.thermal.evaluate_cold_plate"]


@needs_atlas
def test_the_physics_runs_on_an_adapted_archetype():
    from core.archetypes import Library, instantiate
    archetype = Library.load().get("cold_plate.straight_channel")
    document = instantiate(archetype, {"n_channels": 32})
    answer = atlas.evaluate(document, ["atlas_cad.thermal.evaluate_cold_plate",
                                       "atlas_cad.tier2_fd"],
                            {"flow_m3_s": 2.0 / 60000})
    thermal = answer["results"]["atlas_cad.thermal.evaluate_cold_plate"]
    assert thermal["valid"] and 0.01 < thermal["r_th_k_per_w"] < 0.1
    assert thermal["reynolds"] < 2300          # inside the archetype's own claim
    assert answer["results"]["atlas_cad.tier2_fd"]["verdict"] == "agree"


@needs_atlas
def test_atlas_refuses_outside_its_domain_rather_than_extrapolating():
    """The property worth preserving across the bridge: a wrapper that
    smoothed this over would be discarding the reason to use Atlas."""
    from core.archetypes import Library, instantiate
    archetype = Library.load().get("cold_plate.straight_channel")
    document = instantiate(archetype)
    answer = atlas.evaluate(document, ["atlas_cad.thermal.evaluate_cold_plate"],
                            {"flow_m3_s": 2.0})        # 120,000 L/min
    thermal = answer["results"]["atlas_cad.thermal.evaluate_cold_plate"]
    assert not thermal["valid"] and thermal["why"]
