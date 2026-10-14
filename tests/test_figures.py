"""A figure is a cached view of a computation, and caches go stale."""
import json
import os

import pytest
import yaml

from core import figures
from core.figures import (FRESH, MISSING, STALE, UNCHECKABLE, Figure,
                          FigureError, check, generate, load_all, load_figure,
                          read, write)

GENERATOR = '''
VALUE = 42.0
def table():
    return {"answer": VALUE, "nested": {"list": [1.0, 2.0]}, "label": "ok"}
'''


@pytest.fixture
def figure(tmp_path):
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / "generate.py").write_text(GENERATOR)
    (directory / "figure.yaml").write_text(yaml.safe_dump({
        "slug": "demo", "title": "Demo", "question": "does it work",
        "generator": "generate:table", "source": "a constant"}))
    return load_figure(str(directory))


# ---- the manifest ----

def test_a_figure_loads():
    fig = load_figure("figures/co2-widom")
    assert fig.slug == "co2-widom" and fig.size == "figure"
    assert fig.findings.endswith("co2-pseudocritical-audit.md")


def test_a_missing_manifest_is_an_error(tmp_path):
    with pytest.raises(FigureError, match="no figure.yaml"):
        load_figure(str(tmp_path))


def test_a_manifest_missing_its_question_is_refused(tmp_path):
    (tmp_path / "figure.yaml").write_text(
        yaml.safe_dump({"slug": "x", "title": "X"}))
    with pytest.raises(FigureError, match="'question' is required"):
        load_figure(str(tmp_path))


def test_a_malformed_generator_reference_is_refused(tmp_path):
    (tmp_path / "figure.yaml").write_text(yaml.safe_dump(
        {"slug": "x", "title": "X", "question": "q", "generator": "generate"}))
    with pytest.raises(FigureError, match="module:callable"):
        load_figure(str(tmp_path))


# ---- generating ----

def test_the_generator_runs_and_the_table_round_trips(figure):
    table = generate(figure)
    assert table["answer"] == 42.0
    write(figure, table)
    assert read(figure)["answer"] == 42.0


def test_what_is_written_is_stamped_with_where_it_came_from(figure):
    write(figure, generate(figure))
    stamp = read(figure)["_provenance"]
    assert stamp["generator"] == "generate:table"
    assert stamp["source"] == "a constant"
    assert stamp["generated_at"].endswith("Z") and stamp["digest"]


# ---- freshness, which is the point ----

def test_a_figure_never_generated_is_missing(figure):
    assert check(figure).state == MISSING


def test_a_figure_whose_numbers_still_compute_the_same_is_fresh(figure):
    write(figure, generate(figure))
    assert check(figure).ok
    assert check(figure).summary() == "demo: fresh"


def test_a_figure_whose_model_moved_is_stale_and_says_what_moved(figure):
    """The failure this whole module exists for: a beautiful, audited,
    self-consistent figure quietly showing last spring's answer."""
    write(figure, generate(figure))
    path = os.path.join(figure.directory, "generate.py")
    open(path, "w").write(GENERATOR.replace("VALUE = 42.0", "VALUE = 44.1"))

    state = check(figure)
    assert state.state == STALE and not state.ok
    assert [m[0] for m in state.moved] == ["answer"]
    assert state.moved[0][1] == 42.0 and state.moved[0][2] == 44.1
    assert "STALE" in state.summary() and "answer" in state.summary()


def test_the_worst_move_is_the_one_reported(figure):
    write(figure, generate(figure))
    open(os.path.join(figure.directory, "generate.py"), "w").write(
        GENERATOR.replace("VALUE = 42.0", "VALUE = 42.1")
                 .replace("[1.0, 2.0]", "[1.0, 9.0]"))
    summary = check(figure).summary()
    assert "nested.list[1]" in summary and "2 value(s) moved" in summary


def test_a_move_inside_the_tolerance_is_not_a_move(figure):
    write(figure, generate(figure))
    open(os.path.join(figure.directory, "generate.py"), "w").write(
        GENERATOR.replace("VALUE = 42.0", "VALUE = 42.00000001"))
    assert check(figure).ok


def test_a_new_or_vanished_field_is_a_move(figure):
    write(figure, generate(figure))
    open(os.path.join(figure.directory, "generate.py"), "w").write(
        GENERATOR.replace('"label": "ok"', '"label": "ok", "extra": 1.0'))
    assert [m[0] for m in check(figure).moved] == ["extra"]


def test_a_generator_that_will_not_run_is_uncheckable_not_fresh(figure):
    """Deliberately not a kind of fresh. A figure whose provenance cannot be
    re-executed is a picture, and it is better to say so."""
    write(figure, generate(figure))
    open(os.path.join(figure.directory, "generate.py"), "w").write(
        "import nonexistent_module_xyz\n")
    state = check(figure)
    assert state.state == UNCHECKABLE and not state.ok
    assert "UNCHECKABLE" in state.summary()
    assert "nonexistent_module_xyz" in state.reason


def test_a_figure_with_no_generator_is_uncheckable_forever(tmp_path):
    directory = tmp_path / "static"
    directory.mkdir()
    (directory / "figure.yaml").write_text(yaml.safe_dump(
        {"slug": "static", "title": "T", "question": "q"}))
    fig = load_figure(str(directory))
    (directory / "data.json").write_text('{"a": 1}')
    assert check(fig).state == UNCHECKABLE
    assert "declares no generator" in check(fig).reason


def test_checking_never_writes(figure):
    write(figure, generate(figure))
    before = open(figure.data_path).read()
    open(os.path.join(figure.directory, "generate.py"), "w").write(
        GENERATOR.replace("VALUE = 42.0", "VALUE = 99.0"))
    check(figure)
    assert open(figure.data_path).read() == before


# ---- the shipped figure ----

def test_the_co2_figure_is_fresh():
    """If CoolProp changes its CO2 equation of state, this is the test that
    notices before the drawing does."""
    assert check(load_figure("figures/co2-widom")).ok


def test_the_vessel_geometry_integrates_to_the_real_enthalpy():
    """The figure's one physical claim: area(T) = cp(T), so the volume up to a
    level is the enthalpy. If that is not true the object is decoration."""
    data = read(load_figure("figures/co2-widom"))
    assert data["enthalpy_check"]["worst_relative_error"] < 1e-3


def test_the_figure_reports_the_number_the_audit_said_was_unusable():
    data = read(load_figure("figures/co2-widom"))
    assert 34.0 < data["pseudocritical"]["t_c"] < 35.5
    # Across any realistic operating span you get a fraction of the peak.
    by_width = {s["half_width_k"]: s["fraction_of_peak"] for s in data["spans"]}
    assert by_width[0.5] > by_width[2.0] > by_width[5.0] > by_width[10.0]
    assert by_width[5.0] < 0.4


def test_every_figure_in_the_tree_loads_and_names_its_source():
    found = load_all()
    assert "co2-widom" in found
    for fig in found.values():
        assert fig.source.strip(), f"{fig.slug} does not say where its numbers came from"
        assert fig.question.strip()
