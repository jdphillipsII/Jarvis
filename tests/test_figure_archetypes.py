"""Mechanisms indexed by shape, not by subject."""
import pytest

from core.figure_archetypes import (MATCHED, NO_MECHANISM, NOTHING_FITS,
                                    ArchetypeError, Library, load_archetype,
                                    schema, select, vocabulary)


def entry(**over):
    base = {"id": "demo.thing", "relationship": "r", "object": "o",
            "moves": "m", "cannot_show": "its limits",
            "needs": ["accumulates"]}
    base.update(over)
    return base


def lib(*entries):
    return Library(load_archetype(e) for e in entries)


# ---- the library is strict about its own entries ----

def test_an_entry_must_name_what_it_cannot_show():
    """An archetype that claims no limit will be reached for when it does not
    fit."""
    doc = entry()
    del doc["cannot_show"]
    with pytest.raises(ArchetypeError, match="claims no limit"):
        load_archetype(doc)


def test_an_entry_with_no_needs_matches_everything_and_is_refused():
    with pytest.raises(ArchetypeError, match="same as matching nothing"):
        load_archetype(entry(needs=[]))


def test_a_trait_outside_the_vocabulary_is_refused():
    with pytest.raises(ArchetypeError, match="'sparkles' is not a trait"):
        load_archetype(entry(needs=["sparkles"]))


def test_a_trait_cannot_be_both_required_and_disqualifying():
    with pytest.raises(ArchetypeError, match="both"):
        load_archetype(entry(needs=["accumulates"], rules_out=["accumulates"]))


def test_built_means_a_genome_exists():
    with pytest.raises(ArchetypeError, match="name it"):
        lib(entry(status="built")).check()


def test_a_genome_that_is_not_there_is_refused():
    with pytest.raises(ArchetypeError, match="is not there"):
        lib(entry(status="built", genome="figures/nope/genome.yaml")).check()


# ---- selection ----

BUCKET = entry(id="bucket", needs=["accumulates", "drains", "has_ceiling"],
               object="a bucket under a tap")
VESSEL = entry(id="vessel", needs=["varies_with_one", "accumulates"],
               object="a graduated vessel")


def test_the_shape_decides_not_the_subject():
    """A rate limiter and a reservoir are the same machine."""
    library = lib(BUCKET, VESSEL)
    for traits in (["accumulates", "drains", "has_ceiling", "overflows"],
                   ["accumulates", "drains", "has_ceiling", "feedback"]):
        assert select(library, traits).best.id == "bucket"


def test_the_entry_that_accounts_for_more_of_the_shape_comes_first():
    chosen = select(lib(BUCKET, VESSEL),
                    ["accumulates", "drains", "has_ceiling", "varies_with_one"])
    assert [a.id for a in chosen.matches] == ["bucket", "vessel"]


def test_a_disqualifying_trait_excludes_rather_than_ranks_low():
    library = lib(entry(id="lock", needs=["matches_a_key"],
                        rules_out=["conditions_ordered"]))
    assert select(library, ["matches_a_key"]).best.id == "lock"
    assert select(library, ["matches_a_key", "conditions_ordered"]).matches == []


def test_a_real_shape_the_library_lacks_is_nothing_fits():
    chosen = select(lib(BUCKET), ["propagates", "delayed"])
    assert chosen.verdict == NOTHING_FITS and chosen.best is None
    assert "no archetype in the library has this shape" in chosen.report()
    assert "joins the library and is never hand-built again" in chosen.report()


def test_nothing_fits_names_the_near_misses_and_what_they_would_need():
    chosen = select(lib(BUCKET), ["accumulates"])
    assert chosen.verdict == NOTHING_FITS
    assert chosen.near and chosen.near[0][1] == ["drains", "has_ceiling"]
    assert "needs drains, has_ceiling" in chosen.report()


def test_a_subject_with_no_mechanism_is_refused_and_that_is_correct():
    """A poem, a judgement, a list of dates. Forcing a machine onto those
    produces decoration, and decoration dressed as explanation is worse."""
    chosen = select(lib(BUCKET, VESSEL), [])
    assert chosen.verdict == NO_MECHANISM and chosen.matches == []
    assert "worse than prose" in chosen.report()


def test_a_word_that_is_not_a_trait_is_ignored_and_said_so():
    chosen = select(lib(BUCKET), ["accumulates", "drains", "has_ceiling",
                                  "thermodynamics"])
    assert chosen.verdict == MATCHED
    assert chosen.unknown == ["thermodynamics"]
    assert "ignored, not traits: thermodynamics" in chosen.report()


def test_only_unrecognised_words_still_means_no_mechanism():
    assert select(lib(BUCKET), ["vibes", "poetry"]).verdict == NO_MECHANISM


# ---- the prompt ----

def test_the_schema_holds_a_model_to_the_trait_vocabulary():
    traits = schema()["properties"]["traits"]["items"]["enum"]
    assert "accumulates" in traits and "sparkles" not in traits
    assert schema()["properties"]["traits"]["minItems"] == 0, \
        "an empty trait list is a valid answer: it means no mechanism"


def test_the_model_describes_rather_than_chooses():
    """There is no field in which a model names an archetype."""
    assert set(schema()["properties"]) == {"subject", "lesson", "traits"}
    assert schema()["additionalProperties"] is False


def test_the_vocabulary_explains_each_trait():
    rendered = vocabulary()
    assert "accumulates: something builds up" in rendered
    assert rendered.count("\n") >= 20


# ---- the shipped library ----

def test_the_shipped_library_loads():
    library = Library.load()
    assert len(library) >= 9
    library.check()


def test_every_entry_names_a_limit_and_a_subject_it_has_explained():
    for archetype in Library.load():
        assert archetype.cannot_show.strip(), archetype.id
        assert archetype.seen_as, f"{archetype.id} has never been used"


def test_entries_from_unrelated_fields_land_on_one_machine():
    library = Library.load()
    rate_limiter = ["accumulates", "drains", "has_ceiling", "overflows"]
    glucose = ["accumulates", "drains", "has_ceiling", "feedback"]
    assert select(library, rate_limiter).best.id == "bucket.inflow_outflow"
    assert select(library, glucose).best.id == "bucket.inflow_outflow"

    cache_key = ["matches_a_key", "conditions_all_required"]
    assert select(library, cache_key).best.id == "lock.all_pins_match"


def test_ordered_conditions_pick_the_gate_and_unordered_pick_the_lock():
    library = Library.load()
    assert select(library, ["conditions_all_required", "conditions_ordered"]
                  ).best.id == "gate.series_apertures"
    assert select(library, ["conditions_all_required", "matches_a_key"]
                  ).best.id == "lock.all_pins_match"


def test_the_one_built_entry_points_at_a_genome_that_exists():
    built = [a for a in Library.load() if a.built]
    assert [a.id for a in built] == ["gate.series_apertures"]
    import os
    assert os.path.exists(built[0].genome)
