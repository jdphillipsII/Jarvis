"""What a local model is allowed to say when it designs a figure."""
import pytest

from core.figure_genome import (GROUND, KINDS, FigureGenome, load, schema,
                                vocabulary)


def doc(**overrides):
    base = {
        "figure": "token_bucket",
        "question": "why a burst passes and a steady overload does not",
        "subject": "the tokens in the bucket",
        "params": {"plate_w": 300.0, "bucket_r": 30.0},
        "parts": [
            {"id": "plate", "kind": "slab", "on": GROUND,
             "plan": {"w": "$plate_w", "d": 148}, "height": 13},
            {"id": "post", "kind": "slab", "on": "@face:plate/top",
             "plan": {"w": 10, "d": 8}, "height": 120},
            {"id": "bucket", "kind": "turned", "on": "post",
             "profile": "straight", "lit": True},
        ],
    }
    base.update(overrides)
    return base


def ok(**overrides):
    genome, faults = load(doc(**overrides))
    assert not faults, [str(f) for f in faults]
    return genome


# ---- the shape ----

def test_a_well_formed_genome_loads():
    genome = ok()
    assert genome.figure == "token_bucket"
    assert [p.id for p in genome.parts] == ["plate", "post", "bucket"]
    assert genome.lit.id == "bucket"


def test_every_part_says_what_it_sits_on():
    parts = doc()["parts"]
    del parts[1]["on"]
    _, faults = load(doc(parts=parts))
    assert any("says what it sits on" in f.reason for f in faults)


def test_a_part_may_only_sit_on_something_already_built():
    """Which is also why there is no cycle check: a cycle cannot be written."""
    parts = doc()["parts"]
    parts[0]["on"] = "bucket"
    _, faults = load(doc(parts=parts))
    assert any("not a part declared before it" in f.reason for f in faults)


def test_the_support_chain_reaches_the_ground():
    genome = ok()
    assert genome.supports("bucket") == ["post", "plate"]
    assert genome.supports("plate") == []


def test_an_unknown_kind_is_refused_with_the_real_list():
    parts = doc()["parts"]
    parts[2]["kind"] = "sphere"
    _, faults = load(doc(parts=parts))
    fault, = [f for f in faults if "unknown kind" in f.reason]
    assert "turned" in fault.suggestion and "slab" in fault.suggestion


def test_a_kind_missing_what_it_cannot_be_drawn_without_is_refused():
    parts = doc()["parts"]
    del parts[0]["height"]
    _, faults = load(doc(parts=parts))
    assert any("needs height" in f.reason for f in faults)


def test_a_face_the_host_does_not_have_is_refused():
    parts = doc()["parts"]
    parts[1]["on"] = "@face:plate/wall"          # a slab has no wall
    _, faults = load(doc(parts=parts))
    fault, = [f for f in faults if "no face called" in f.reason]
    assert "top, bottom, side" in fault.suggestion


def test_a_part_cannot_sit_on_an_edge():
    parts = doc()["parts"]
    parts[1]["on"] = "@edge:plate/top_rim"
    _, faults = load(doc(parts=parts))
    assert any("sits on a face, not an edge" in f.reason for f in faults)


def test_a_reference_to_an_undeclared_parameter_is_refused():
    parts = doc()["parts"]
    parts[0]["plan"]["d"] = "$depth"
    _, faults = load(doc(parts=parts))
    assert any("undeclared $depth" in f.reason for f in faults)


def test_duplicate_ids_are_refused():
    parts = doc()["parts"]
    parts[2]["id"] = "post"
    _, faults = load(doc(parts=parts))
    assert any("duplicate id 'post'" in f.reason for f in faults)


# ---- the subject ----

def test_exactly_one_part_is_the_lit_subject():
    parts = doc()["parts"]
    parts[1]["lit"] = True
    _, faults = load(doc(parts=parts))
    assert any("found 2" in f.reason for f in faults)


def test_a_figure_with_no_subject_is_refused():
    parts = doc()["parts"]
    parts[2]["lit"] = False
    _, faults = load(doc(parts=parts))
    assert any("found 0" in f.reason for f in faults)


# ---- every fault at once ----

def test_eleven_mistakes_come_back_as_eleven_faults():
    """Sending a model back one mistake at a time is how a loop takes eleven
    round trips."""
    broken = doc(parts=[
        {"id": "Plate", "kind": "slabb", "on": "nowhere"},
        {"id": "x", "kind": "slab", "on": GROUND, "tone": "glowing"},
    ])
    del broken["question"]
    _, faults = load(broken)
    reasons = " | ".join(f.reason for f in faults)
    assert len(faults) >= 5
    for expected in ("required", "lower_snake_case id", "unknown kind",
                     "not a part declared before it", "must be one of"):
        assert expected in reasons, expected


def test_a_genome_with_no_parts_is_refused_rather_than_returned_empty():
    genome, faults = load(doc(parts=[]))
    assert genome is None and any("needs some" in f.reason for f in faults)


# ---- the prompt ----

def test_the_schema_names_every_kind_so_a_grammar_can_hold_the_model_to_them():
    kinds = schema()["properties"]["parts"]["items"]["properties"]["kind"]["enum"]
    assert set(kinds) == set(KINDS)


def test_the_schema_refuses_fields_nobody_declared():
    assert schema()["additionalProperties"] is False


def test_the_schema_asks_for_a_figure_dense_enough_to_read():
    assert schema()["properties"]["parts"]["minItems"] >= 12


def test_the_vocabulary_renders_every_kind_with_its_faces():
    rendered = vocabulary()
    for name in KINDS:
        assert name in rendered
    assert "faces: top, bottom, side" in rendered
    assert "no faces" in rendered
