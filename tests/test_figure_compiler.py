"""The arithmetic the model does not do."""
import pytest
import yaml

from core.figure_compiler import CompileError, Placed, emit, place, resolve
from core.figure_genome import load


def genome(parts, **extra):
    doc = {"figure": "demo", "question": "q", "subject": "s",
           "params": {"w": 100.0}, "parts": parts}
    doc.update(extra)
    built, faults = load(doc)
    assert not faults, [str(f) for f in faults]
    return built


def slab(part_id, sits_on, **more):
    base = {"id": part_id, "kind": "slab", "sits_on": sits_on,
            "plan": {"w": 40, "d": 20}, "height": 10}
    base.update(more)
    return base


# ---- the solve ----

def test_a_part_on_the_ground_starts_at_zero():
    spots = place(genome([slab("bed", "ground", lit=True)]))
    assert spots["bed"].z == 0 and spots["bed"].top == 10


def test_a_part_sits_on_its_host_s_top_rather_than_a_number_somebody_typed():
    spots = place(genome([slab("bed", "ground"),
                          slab("post", "bed", height=30, lit=True)]))
    assert spots["post"].z == spots["bed"].top == 10
    assert spots["post"].top == 40


def test_changing_a_host_moves_everything_above_it():
    """The edit that breaks a hand-written build: make the bench thicker."""
    thin = place(genome([slab("bed", "ground", height=10),
                         slab("post", "bed", lit=True)]))
    thick = place(genome([slab("bed", "ground", height=25),
                          slab("post", "bed", lit=True)]))
    assert thick["post"].z - thin["post"].z == 15


def test_offsets_are_in_the_host_s_frame_and_compound():
    spots = place(genome([
        slab("bed", "ground"),
        slab("post", "bed", at={"x": 20, "y": -5}),
        slab("arm", "post", at={"x": 7, "y": 2}, lit=True)]))
    assert (spots["post"].x, spots["post"].y) == (20, -5)
    assert (spots["arm"].x, spots["arm"].y) == (27, -3)


def test_a_part_on_a_side_face_keeps_its_host_s_floor():
    """A side-mounted part that said nothing would otherwise land on the
    host's top, which is not what 'on the side' means to anyone."""
    spots = place(genome([
        slab("post", "ground", height=80),
        {"id": "dial", "kind": "ring", "sits_on": "@face:post/side",
         "radius": 9, "at": {"z": 50}, "lit": True}]))
    assert spots["dial"].z == 50


def test_a_part_on_a_bottom_face_hangs_below():
    spots = place(genome([
        slab("bed", "ground"),
        {"id": "foot", "kind": "cylinder", "sits_on": "@face:bed/bottom",
         "radius": 4, "height": 6, "at": {"z": 6}, "lit": True}]))
    assert spots["foot"].z == -6


def test_declaration_order_is_painter_s_order():
    """It falls out of the support rule rather than being imposed: a part can
    only sit on something declared earlier, so it is always drawn after it."""
    built = genome([slab("bed", "ground"), slab("post", "bed"),
                    slab("arm", "post", lit=True)])
    order = [p.id for p in built.parts]
    spots = place(built)
    assert order == ["bed", "post", "arm"]
    assert [spots[i].z for i in order] == sorted(spots[i].z for i in order)


# ---- parameters ----

def test_a_parameter_reaches_the_geometry():
    spots = place(genome([slab("bed", "ground", plan={"w": "$w", "d": 20},
                               lit=True)]))
    assert spots["bed"].plan == (100.0, 20.0)


def test_a_bare_reference_keeps_its_type_and_an_expression_stays_one():
    assert resolve("$w", {"w": 12.0}) == 12.0
    assert resolve("$w * 0.25", {"w": 12.0}) == "12.0 * 0.25"


def test_an_undeclared_reference_is_refused_at_compile():
    with pytest.raises(CompileError, match=r"undeclared \$missing"):
        resolve("$missing", {})


# ---- kinds that need more than a box ----

def test_a_turned_body_takes_its_height_and_reach_from_its_profile():
    spots = place(genome([
        {"id": "vessel", "kind": "turned", "sits_on": "ground", "lit": True,
         "profile": [[0, 8], [20, 30], [40, 6]]}]))
    assert spots["vessel"].height == 40 and spots["vessel"].radius == 30


def test_a_turned_body_without_a_profile_is_refused():
    with pytest.raises(CompileError, match="needs a profile"):
        place(genome([{"id": "v", "kind": "turned", "sits_on": "ground",
                       "profile": [[0, 1]], "lit": True}]))


def test_a_scatter_rule_is_not_an_offset():
    """`at: corners:bed` places marks over a host; it is not a coordinate."""
    spots = place(genome([
        slab("bed", "ground", lit=True),
        {"id": "screws", "kind": "dots", "sits_on": "bed", "at": "corners:bed"}]))
    assert (spots["screws"].x, spots["screws"].y) == (0, 0)


def test_a_malformed_at_says_what_both_forms_look_like():
    with pytest.raises(CompileError, match="corners:<part>"):
        place(genome([slab("bed", "ground", at=7, lit=True)]))


# ---- emission ----

def test_the_emitted_build_draws_every_part_in_order():
    built = genome([slab("bed", "ground"),
                    {"id": "pin", "kind": "cylinder", "sits_on": "bed",
                     "radius": 3, "height": 9, "lit": True}])
    source = emit(built)
    assert source.index("// bed") < source.index("// pin")
    assert "k.slabOf(" in source and "k.cylinder(" in source
    assert "lit: true" in source


def test_the_emitted_build_imports_the_installed_skill():
    source = emit(genome([slab("bed", "ground", lit=True)]))
    assert '".claude", "skills", "anatomy"' in source
    assert "ANATOMY_ROOT" in source


def test_the_camera_holds_every_part():
    source = emit(genome([slab("bed", "ground"),
                          slab("tower", "bed", height=200, lit=True)]))
    assert "fitProjection" in source and "210" in source


# ---- the shipped genome ----

def test_the_tool_gate_genome_loads_places_and_emits():
    with open("figures/tool-gate/genome.yaml") as fh:
        built, faults = load(yaml.safe_load(fh))
    assert not faults, [str(f) for f in faults]
    spots = place(built)
    # the rail rests on the bench, and the call rests on the rail
    assert spots["rail"].z == spots["bed"].top
    assert spots["token"].z == spots["rail"].top
    # all three gates stand on the same bench, at the same height
    gates = [spots[g] for g in ("gate_agency", "gate_schema", "gate_consent")]
    assert len({g.z for g in gates}) == 1
    assert len({round(g.x) for g in gates}) == 3
    assert "k.slabOf(" in emit(built)


def test_an_unquoted_on_key_in_yaml_is_named_rather_than_mystifying():
    """YAML 1.1 reads `on:` as True, so a hand-written genome silently loses
    every support declaration. It should say so once, not fifteen times."""
    doc = yaml.safe_load("parts:\n  - id: bed\n    kind: slab\n    on: ground\n")
    built, faults = load({"figure": "f", "question": "q", "subject": "s", **doc})
    assert any("boolean True" in f.reason for f in faults)
    assert any("sits_on" in f.suggestion for f in faults)
