"""The two small jobs a local model is trusted with."""
import json

import pytest
import yaml

from core import figure_archetypes as fa
from core.figure_author import (apply_binding, author, bind, binding_schema,
                                describe)
from core.figure_genome import load


class Scripted:
    """A model that answers by the shape it was held to.

    Which is itself the point: under a grammar there is only one shape it can
    answer in, so a test model and a real one differ in judgement, not format.
    """

    def __init__(self, traits=("conditions_all_required", "conditions_ordered"),
                 lesson="order decides", binding=None, fail=False):
        self.traits, self.lesson = list(traits), lesson
        self.binding = binding
        self.fail = fail
        self.schemas = []

    def __call__(self, messages, tools=None, schema=None):
        self.schemas.append(schema)
        if self.fail:
            return {"content": "I think the answer is probably a lock?"}
        props = (schema or {}).get("properties", {})
        if "traits" in props:
            body = {"traits": self.traits, "lesson": self.lesson}
        else:
            body = self.binding if self.binding is not None else {
                "figure": "demo_figure", "question": "why order decides",
                "subject": "the request on the rail",
                "params": {"post_h": 110.0},
                "labels": {"gate_agency": "authentication"}}
        return {"content": json.dumps(body)}


@pytest.fixture
def library():
    return fa.Library.load()


# ---- describing ----

def test_the_model_is_asked_for_a_shape_and_never_for_an_object(library):
    model = Scripted()
    describe("a request passing three checks", model)
    asked = model.schemas[0]
    assert set(asked["properties"]) == {"subject", "lesson", "traits"}
    assert "archetype" not in json.dumps(asked)


def test_an_empty_trait_list_is_carried_rather_than_corrected():
    draft = describe("why a sonnet's volta works", Scripted(traits=[]))
    assert draft.traits == []


def test_an_answer_that_is_not_the_shape_it_was_held_to_is_empty_not_a_crash():
    assert describe("anything", Scripted(fail=True)).traits == []


# ---- binding ----

def gate_genome():
    with open("figures/tool-gate/genome.yaml") as fh:
        genome, faults = load(yaml.safe_load(fh))
    assert not faults
    return genome


def test_the_binding_grammar_is_cut_to_one_genome():
    """A model cannot name a parameter or a part that is not in this figure —
    the class of error that would otherwise cost a round trip to find."""
    schema = binding_schema(gate_genome())
    assert set(schema["properties"]["params"]["properties"]) == {
        "bed_w", "bed_d", "bed_h", "post_h", "gate_gap", "rail_h", "token_r"}
    assert "gate_agency" in schema["properties"]["labels"]["properties"]
    assert "nonexistent" not in schema["properties"]["labels"]["properties"]
    assert schema["properties"]["params"]["additionalProperties"] is False


def test_the_binding_asks_for_words_and_numbers_and_not_for_layout():
    schema = binding_schema(gate_genome())
    assert set(schema["properties"]) == {"figure", "question", "subject",
                                         "params", "labels"}
    assert "parts" not in schema["properties"]
    assert "sits_on" not in json.dumps(schema)


def test_the_machine_is_described_to_the_model_including_its_limits(library):
    model = Scripted()
    archetype = library.get("gate.series_apertures")
    bind("a login flow", archetype, gate_genome(), model)
    # the prompt went in as the system turn of the second call
    assert model.schemas[-1]["properties"].get("labels")


# ---- applying ----

def test_a_binding_changes_words_and_numbers_only():
    with open("figures/tool-gate/genome.yaml") as fh:
        document = yaml.safe_load(fh)
    out = apply_binding(document, {
        "figure": "login_flow", "question": "why order decides",
        "subject": "the request", "params": {"post_h": 120.0},
        "labels": {"gate_agency": "password"}})
    assert out["figure"] == "login_flow"
    assert out["params"]["post_h"] == 120.0
    assert out["params"]["bed_w"] == document["params"]["bed_w"]
    gate = [p for p in out["parts"] if p["id"] == "gate_agency"][0]
    assert gate["note"] == "password"
    # layout untouched: every sits_on is the archetype's
    assert [p.get("sits_on") for p in out["parts"]] == \
        [p.get("sits_on") for p in document["parts"]]


def test_the_original_genome_is_not_mutated():
    with open("figures/tool-gate/genome.yaml") as fh:
        document = yaml.safe_load(fh)
    before = json.dumps(document, sort_keys=True)
    apply_binding(document, {"figure": "other", "params": {"post_h": 1.0}})
    assert json.dumps(document, sort_keys=True) == before


def test_a_parameter_the_genome_does_not_have_is_dropped():
    with open("figures/tool-gate/genome.yaml") as fh:
        document = yaml.safe_load(fh)
    out = apply_binding(document, {"params": {"invented": 9.0}})
    assert "invented" not in out["params"]


# ---- the whole run ----

def test_a_subject_of_a_built_shape_comes_back_placeable(library):
    draft = author("a request passing auth, then authz, then quota",
                   library, Scripted())
    assert draft.ok, draft.faults or draft.refusal
    assert draft.archetype.id == "gate.series_apertures"
    assert draft.genome.figure == "demo_figure"
    assert draft.genome.params["post_h"] == 110.0


def test_a_subject_with_no_mechanism_is_refused_in_the_library_s_words(library):
    draft = author("the causes of the Thirty Years War", library,
                   Scripted(traits=[]))
    assert not draft.ok
    assert "worse than prose" in draft.refusal
    assert draft.archetype is None


def test_a_shape_with_no_genome_yet_says_build_it_once(library):
    """The ratchet, stated where someone will meet it."""
    draft = author("a reservoir with a spillway", library,
                   Scripted(traits=["accumulates", "drains", "has_ceiling"]))
    assert not draft.ok and draft.archetype.id == "bucket.inflow_outflow"
    assert "Build that one by hand once" in draft.refusal
    assert "automatic" in draft.refusal


def test_a_binding_that_breaks_the_genome_comes_back_as_faults_not_a_page(library):
    draft = author("a login flow", library,
                   Scripted(binding={"figure": "Bad Name"}))
    assert not draft.ok and draft.faults
    assert any("lower_snake" in f or "figure" in f for f in draft.faults)


def test_the_run_compiles_all_the_way_to_a_built_page(library, tmp_path):
    """Subject in, page out, with nothing hand-written in between."""
    from core.figure_compiler import emit
    draft = author("a request passing auth, then authz, then quota",
                   library, Scripted())
    source = emit(draft.genome)
    assert "k.slabOf(" in source and "fitProjection" in source
    assert "authentication" in source      # the model's label reached the drawing
