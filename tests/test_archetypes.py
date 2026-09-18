"""Retrieve and adapt — and, more importantly, refuse."""
import pytest
import yaml

from core.archetypes import (Archetype, ArchetypeError, Condition, Library,
                             ParamSpec, assess, instantiate, load_archetype,
                             select)

MINIMAL = {
    "id": "test.thing", "summary": "a thing", "intent": "testing",
    "parameters": [{"name": "width", "unit": "mm", "default": 10.0,
                    "bounds": [5.0, 20.0]}],
    "program": [{"op": "sketch", "id": "outline", "width": "$width"},
                {"op": "pad", "id": "body", "profile": "outline", "depth": "$width"}],
}


def doc(**overrides):
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in MINIMAL.items()}
    out.update(overrides)
    return out


# ---- the library is data, and its errors are loud ----

def test_a_minimal_archetype_loads():
    a = load_archetype(doc())
    assert a.id == "test.thing" and a.status == "proposed"


def test_a_parameter_without_a_default_is_refused():
    """An archetype is a working design, not a form to fill in."""
    with pytest.raises(ArchetypeError, match="needs a default"):
        load_archetype(doc(parameters=[{"name": "w", "unit": "mm"}]))


def test_a_default_outside_its_own_bounds_is_refused():
    with pytest.raises(ArchetypeError, match="out of its own range"):
        load_archetype(doc(parameters=[{"name": "w", "unit": "mm", "default": 99.0,
                                        "bounds": [1.0, 10.0]}]))


def test_a_program_referencing_an_undeclared_parameter_is_refused():
    with pytest.raises(ArchetypeError, match=r"undeclared \$height"):
        load_archetype(doc(program=[{"op": "sketch", "id": "o", "h": "$height"}]))


def test_a_broken_topology_pointer_is_refused_at_load():
    """The two halves meet here: an archetype is checked by core.topology
    before it can ever be instantiated."""
    program = MINIMAL["program"] + [
        {"op": "fillet", "edges": ["@edge:body/floor_rim"], "radius": "1 mm"}]
    with pytest.raises(ArchetypeError, match="makes no edge called 'floor_rim'"):
        load_archetype(doc(program=program))


def test_a_condition_with_no_reason_is_refused():
    """A bound with no reason cannot be argued with, and a library is a thing
    you argue with."""
    with pytest.raises(ArchetypeError, match="no 'why'"):
        load_archetype(doc(applicability=[{"quantity": "load", "maximum": "10 N"}]))


def test_a_condition_that_bounds_nothing_is_refused():
    with pytest.raises(ArchetypeError, match="bounds nothing"):
        load_archetype(doc(applicability=[{"quantity": "load", "why": "because"}]))


def test_a_condition_bound_without_units_is_refused_at_load():
    with pytest.raises(ArchetypeError, match="load"):
        load_archetype(doc(applicability=[{"quantity": "load", "why": "x",
                                           "maximum": "10 flurbles"}]))


# ---- the evidence ladder ----

def test_claiming_a_rung_without_citing_evidence_is_refused():
    with pytest.raises(ArchetypeError, match="cite it in `evidence`"):
        load_archetype(doc(status="built"))


def test_measured_requires_a_predicted_versus_measured_record():
    """The top rung is the loop closure, which is exactly the arrow the
    engineering suite lists as having no home. It cannot be claimed by
    assertion."""
    with pytest.raises(ArchetypeError, match="predicted-vs-measured"):
        load_archetype(doc(status="measured", evidence="ran it on the bench"))
    ok = load_archetype(doc(status="measured",
                            evidence="rig run 2026-09-02; predicted 0.081 K/W "
                                     "against measured 0.088 K/W"))
    assert ok.rung == 3


def test_an_unknown_status_is_refused():
    with pytest.raises(ArchetypeError, match="status must be"):
        load_archetype(doc(status="pretty_sure"))


# ---- cross references ----

def test_a_failure_mode_pointing_at_a_missing_archetype_is_refused():
    lib = Library([load_archetype(doc(failure_modes=[
        {"name": "x", "description": "y", "mitigated_by": "test.nonexistent"}]))])
    with pytest.raises(ArchetypeError, match="not in the library"):
        lib.check_cross_references()


def test_an_archetype_cannot_be_its_own_mitigation():
    lib = Library([load_archetype(doc(failure_modes=[
        {"name": "x", "description": "y", "mitigated_by": "test.thing"}]))])
    with pytest.raises(ArchetypeError, match="its own mitigation"):
        lib.check_cross_references()


# ---- selection ----

def cooling_library():
    return Library.load()


BASE = {"coolant_phase": "single_phase_liquid", "flow_regime": "laminar",
        "source_geometry": "flat", "material_family": "copper",
        "footprint": "90 mm", "flow_distribution": "parallel"}


def test_a_problem_the_library_covers_returns_the_covering_archetype():
    chosen = select(cooling_library(), BASE)
    assert chosen.best.id == "cold_plate.straight_channel"


def test_one_failed_condition_excludes_rather_than_ranks_low():
    """Conditions are not a score. A design that is wrong in one way that
    matters is not a 4-out-of-5 design."""
    chosen = select(cooling_library(), {**BASE, "coolant_phase": "two_phase"})
    assert chosen.nothing_applies
    assert "cold_plate.straight_channel" in [a.archetype.id for a in chosen.excluded]


def test_nothing_applies_names_the_near_misses_and_refuses_to_offer_them():
    report = select(cooling_library(),
                    {"coolant_phase": "two_phase", "flow_regime": "turbulent",
                     "source_geometry": "flat"}).report()
    assert "no archetype in the library covers this problem" in report
    assert "designing from scratch is the honest next step" in report
    assert "two_phase" in report          # says WHY the closest was thrown out


def test_stating_the_constraint_that_motivated_the_second_archetype_selects_it():
    """The pair is the point: serpentine exists because straight-channel's
    known failure mode is flow maldistribution."""
    chosen = select(cooling_library(), {**BASE, "flow_distribution": "single_path"})
    assert [a.archetype.id for a in chosen.applicable] == \
        ["cold_plate.serpentine_channel"]


def test_the_failure_mode_names_the_archetype_that_fixes_it():
    straight = cooling_library().get("cold_plate.straight_channel")
    mode, = [m for m in straight.failure_modes if m.name == "flow_maldistribution"]
    assert mode.mitigated_by == "cold_plate.serpentine_channel"


def test_an_untested_archetype_is_unproven_not_applicable():
    """A cooling problem must not surface a bracket just because nothing in it
    contradicts one."""
    chosen = select(cooling_library(), {"coolant_phase": "single_phase_liquid"})
    assert "bracket.l_cantilever" in [a.archetype.id for a in chosen.unproven]
    assert "bracket.l_cantilever" not in [a.archetype.id for a in chosen.applicable]


def test_what_could_not_be_checked_is_reported_not_assumed():
    chosen = select(cooling_library(), {k: v for k, v in BASE.items()
                                        if k != "material_family"})
    straight, = [a for a in chosen.applicable
                 if a.archetype.id == "cold_plate.straight_channel"]
    assert [c for c, _ in straight.unchecked] == ["material_family in "
                                                  "{copper, aluminum, stainless_steel, "
                                                  "nickel_superalloy, carbon_steel}"]
    assert "unchecked" in chosen.report()


def test_a_dimension_mismatch_in_the_problem_is_a_failure_not_a_crash():
    chosen = select(cooling_library(), {**BASE, "footprint": "90 kg"})
    excluded = [a for a in chosen.excluded
                if a.archetype.id == "cold_plate.straight_channel"]
    assert excluded and "condition is about" in excluded[0].why_not()


def test_evidence_outranks_novelty_in_the_ordering():
    chosen = select(cooling_library(), {k: v for k, v in BASE.items()
                                        if k != "flow_distribution"})
    ids = [a.archetype.id for a in chosen.applicable]
    assert ids.index("cold_plate.straight_channel") < \
        ids.index("cold_plate.serpentine_channel")


# ---- adaptation ----

def test_instantiating_with_no_overrides_gives_the_working_design():
    a = cooling_library().get("cold_plate.straight_channel")
    document = instantiate(a)
    values = {p["name"]: p["value"] for p in document["parameters"]}
    assert values["n_channels"] == 24 and values["plate_width"] == 100.0
    assert document["manufacturing"] == {"material": "CU_C110",
                                         "process": "CNC_5AXIS_MILLING"}


def test_adapting_changes_only_what_was_asked_for():
    a = cooling_library().get("cold_plate.straight_channel")
    document = instantiate(a, {"n_channels": 32}, name="dlc_plate_v3")
    values = {p["name"]: p["value"] for p in document["parameters"]}
    assert values["n_channels"] == 32 and values["base_thickness"] == 6.0
    assert document["part"] == "dlc_plate_v3"


def test_a_value_with_units_is_converted_into_the_archetypes_own():
    a = cooling_library().get("cold_plate.straight_channel")
    document = instantiate(a, {"plate_width": "0.08 m"})
    values = {p["name"]: p["value"] for p in document["parameters"]}
    assert values["plate_width"] == pytest.approx(80.0)


def test_a_value_of_the_wrong_dimension_is_refused():
    a = cooling_library().get("cold_plate.straight_channel")
    with pytest.raises(ArchetypeError, match="plate_width"):
        instantiate(a, {"plate_width": "80 kg"})


def test_a_value_outside_the_archetypes_range_is_refused():
    a = cooling_library().get("cold_plate.straight_channel")
    with pytest.raises(ArchetypeError, match="outside the archetype's range"):
        instantiate(a, {"n_channels": 200})


def test_a_parameter_the_archetype_does_not_have_is_refused_with_the_real_list():
    a = cooling_library().get("cold_plate.straight_channel")
    with pytest.raises(ArchetypeError, match="channel_height"):
        instantiate(a, {"channel_height": 3})


def test_an_integer_parameter_stays_an_integer():
    a = cooling_library().get("cold_plate.straight_channel")
    document = instantiate(a, {"n_channels": 30.0})
    n, = [p for p in document["parameters"] if p["name"] == "n_channels"]
    assert n["value"] == 30 and isinstance(n["value"], int)


# ---- the shipped library ----

def test_the_shipped_library_loads_and_cross_references_resolve():
    lib = Library.load()
    assert len(lib) >= 3
    lib.check_cross_references()


def test_the_shipped_programs_all_pass_the_topology_checker():
    from core.topology import check_program
    for archetype in Library.load():
        assert check_program(archetype.program) == [], archetype.id


def test_nothing_in_the_library_claims_to_be_measured_yet():
    """Because predicted-vs-measured has no home yet. When it does, this test
    is the thing that should change."""
    assert [a.id for a in Library.load() if a.status == "measured"] == []


def test_every_archetype_names_at_least_one_way_it_fails():
    for archetype in Library.load():
        assert archetype.failure_modes, f"{archetype.id} claims no failure modes"


def test_every_archetype_says_where_it_came_from():
    for archetype in Library.load():
        assert archetype.provenance.strip(), archetype.id


def test_the_document_carries_no_field_the_atlas_loader_would_reject():
    """Found by running the chain end to end: load_part refuses unknown
    top-level fields, and it is right to. Provenance travels beside the
    document, not inside it."""
    a = cooling_library().get("cold_plate.straight_channel")
    assert set(instantiate(a)) == {"part", "role", "parameters", "program",
                                   "manufacturing", "ports"}


def test_the_genome_file_keeps_its_provenance_in_the_header():
    from core.archetypes import to_yaml
    a = cooling_library().get("cold_plate.straight_channel")
    text = to_yaml(a, instantiate(a))
    assert text.startswith("# generated from archetype cold_plate.straight_channel")
    assert "known failure mode: flow_maldistribution" in text
    assert yaml.safe_load(text)["part"] == "cold_plate_straight_channel"


def test_an_undetected_failure_mode_is_shouted_in_the_header():
    from core.archetypes import to_yaml
    a = cooling_library().get("bracket.l_cantilever")
    assert "NOTHING DETECTS THIS" in to_yaml(a, instantiate(a))
