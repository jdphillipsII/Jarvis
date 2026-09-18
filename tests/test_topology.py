"""Pointers that survive the edit, and the ones that shouldn't."""
import pytest

from core.topology import (AmbiguousPointer, DanglingPointer, Pointer,
                           PointerError, Problem, Provenance, check_program,
                           find_pointers, resolve)


def plate():
    """A cold plate, roughly: pad the outline, pocket the channel, fillet the
    channel floor, drill the inlet."""
    return [
        {"op": "sketch", "id": "outline", "plane": "XY"},
        {"op": "pad", "id": "base", "profile": "outline", "length": "$base_thickness"},
        {"op": "pocket", "id": "channel", "face": "@face:base/top",
         "depth": "$channel_depth"},
        {"op": "fillet", "id": "break", "edges": ["@edge:channel/floor_rim"],
         "radius": "1 mm"},
        {"op": "hole", "id": "inlet", "face": "@face:base/side#1",
         "diameter": "$port_diameter"},
    ]


# ---- the grammar ----

def test_a_pointer_round_trips():
    for text in ("@face:base/top", "@edge:channel/mouth", "@face:inlet/bore#3"):
        assert str(Pointer.parse(text)) == text


def test_parsing_gives_the_parts():
    p = Pointer.parse("@face:inlet_hole/bore#2")
    assert (p.kind, p.op_id, p.role, p.ordinal) == ("face", "inlet_hole", "bore", 2)
    assert Pointer.parse("@face:base/top").ordinal is None


def test_nonsense_is_refused_with_the_shape_spelled_out():
    for bad in ("face:base/top", "@face:base", "@vertex:base/tip",
                "@face:base/Top", "@face:9base/top", ""):
        with pytest.raises(PointerError, match="topology pointer"):
            Pointer.parse(bad)


def test_ordinals_are_one_based():
    with pytest.raises(PointerError, match="1-based"):
        Pointer.parse("@face:base/side#0")


def test_pointers_are_found_wherever_they_are_nested():
    params = {"edges": ["@edge:a/tangent", {"deep": "@face:b/top"}], "r": "1 mm"}
    assert find_pointers(params) == ["@edge:a/tangent", "@face:b/top"]


# ---- what the checker catches, with no kernel in sight ----

def test_a_good_program_is_quiet():
    assert check_program(plate()) == []


def test_thickening_the_plate_changes_nothing():
    """The whole reason for any of this: the edit that breaks index-based
    selection does not touch a pointer."""
    thicker = plate()
    thicker[1]["length"] = "$base_thickness_plus_3"
    assert check_program(thicker) == []
    assert find_pointers(thicker) == find_pointers(plate())


def test_inserting_a_step_changes_nothing():
    program = plate()
    program.insert(1, {"op": "datum_plane", "id": "mid", "offset": "5 mm"})
    assert check_program(program) == []


def test_deleting_the_op_a_pointer_names_is_loud():
    program = [step for step in plate() if step["id"] != "base"]
    problems = check_program(program)
    assert [p.pointer for p in problems] == ["@face:base/top", "@face:base/side#1"]
    assert all("no op with id 'base'" in p.reason for p in problems)


def test_a_role_the_op_does_not_make_is_refused_with_the_real_ones_listed():
    program = plate()
    program[2]["face"] = "@face:base/floor"        # pad makes no floor
    problem, = check_program(program)
    assert "makes no face called 'floor'" in problem.reason
    assert "top, bottom, side" in problem.suggestion


def test_a_face_role_used_as_an_edge_says_so():
    program = plate()
    program[3]["edges"] = ["@edge:base/top"]
    problem, = check_program(program)
    assert "'top' is a face role" in problem.suggestion


def test_a_pointer_at_a_later_step_is_refused():
    program = plate()
    program[1]["profile"] = "@face:channel/floor"   # channel comes after
    problem, = check_program(program)
    assert "points at a later step" in problem.reason


def test_a_pointer_at_its_own_op_is_refused():
    program = plate()
    program[2]["face"] = "@face:channel/floor"
    problem, = check_program(program)
    assert "points at itself" in problem.reason


def test_duplicate_ids_are_refused_before_anything_can_point_at_them():
    program = plate()
    program[4]["id"] = "channel"
    reasons = [p.reason for p in check_program(program)]
    assert "duplicate op id" in reasons


def test_an_op_needs_an_id_only_if_something_points_at_it():
    program = [{"op": "sketch", "plane": "XY"},
               {"op": "pad", "id": "base", "length": "$t"},
               {"op": "chamfer", "edges": ["@edge:base/top_rim"], "size": "1 mm"}]
    assert check_program(program) == []


# ---- patterns, where an ordinal is not optional ----

def pattern_program(**overrides):
    program = [
        {"op": "sketch", "id": "sk", "plane": "XY"},
        {"op": "pad", "id": "base", "length": "$t"},
        {"op": "hole", "id": "port", "face": "@face:base/top", "diameter": "$d"},
        {"op": "pattern_linear", "id": "ports", "source": "port", "count": 6},
        {"op": "chamfer", "edges": ["@edge:ports/entry_rim#1"], "size": "0.5 mm"},
    ]
    program[3].update(overrides)
    return program


def test_a_pointer_into_a_pattern_resolves_through_its_source():
    assert check_program(pattern_program()) == []


def test_an_instanced_feature_without_an_ordinal_is_refused():
    program = pattern_program()
    program[4]["edges"] = ["@edge:ports/entry_rim"]
    problem, = check_program(program)
    assert "needs an ordinal" in problem.reason
    assert "#1" in problem.suggestion


def test_a_pattern_that_does_not_name_its_source_cannot_be_pointed_into():
    program = pattern_program()
    del program[3]["source"]
    problem, = check_program(program)
    assert "does not name the op it instances" in problem.reason


def test_a_role_the_patterned_op_does_not_make_is_refused():
    program = pattern_program()
    program[4]["edges"] = ["@edge:ports/floor_rim#1"]
    problem, = check_program(program)
    assert "instanced by 'ports'" in problem.reason


# ---- honesty about what an ordinal does not promise ----

def test_a_role_pointer_claims_nothing_it_cannot_keep():
    assert Pointer.parse("@face:base/top").caveat == ""


def test_an_ordinal_pointer_says_what_it_does_not_survive():
    caveat = Pointer.parse("@face:base/side#2").caveat
    assert "survives a dimension change but not a reordering" in caveat


# ---- resolution, against a kernel that is a dictionary ----

def prov():
    p = Provenance()
    p.record("base", "face", "top", ["f_top"])
    p.record("base", "face", "side", ["f_n", "f_e", "f_s", "f_w"])
    p.record("ports", "edge", "entry_rim", ["e1", "e2", "e3"])
    return p


def test_a_role_with_one_match_resolves():
    assert resolve("@face:base/top", prov()) == "f_top"


def test_an_ordinal_picks_the_instance():
    assert resolve("@edge:ports/entry_rim#2", prov()) == "e2"


def test_ambiguity_is_an_error_not_the_first_match():
    """A kernel asked for 'the side face' of a four-sided pad hands back the
    first of four and carries on. That is how the fillet moves."""
    with pytest.raises(AmbiguousPointer, match="matches 4 faces"):
        resolve("@face:base/side", prov())


def test_the_ambiguity_message_shows_the_way_out():
    with pytest.raises(AmbiguousPointer, match=r"@face:base/side#1"):
        resolve("@face:base/side", prov())


def test_a_pointer_to_nothing_raises_rather_than_returning_none():
    with pytest.raises(DanglingPointer, match="resolves to nothing"):
        resolve("@face:base/counterbore", prov())


def test_an_ordinal_past_the_end_raises():
    with pytest.raises(DanglingPointer, match="instance 9 of 3"):
        resolve("@edge:ports/entry_rim#9", prov())
