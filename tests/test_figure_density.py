"""The density probe, and the negative result it carries.

See docs/findings/2026-10-15-density-probe.md. These tests pin the behaviour
that was measured, including the part that makes it unfit as a gate — so that
if anyone later wires it into a pass/fail, the test that says why fails first.
"""
import numpy as np
import pytest

from core.figure_density import Survey, ink, page_colour, read, silhouette, survey


def page(width=640, height=480, value=0.08):
    return np.full((height, width), value, dtype=np.float32)


def box(grey, x0, y0, x1, y1, value=0.9, fill=False):
    grey[y0:y1, x0:x1] = value if fill else grey[y0:y1, x0:x1]
    if not fill:
        grey[y0, x0:x1] = value
        grey[y1 - 1, x0:x1] = value
        grey[y0:y1, x0] = value
        grey[y0:y1, x1 - 1] = value
    return grey


def write(tmp_path, grey, name="page.png"):
    from PIL import Image
    path = tmp_path / name
    Image.fromarray((grey * 255).astype(np.uint8), mode="L").save(path)
    return str(path)


# ---- reading the page ----

def test_the_page_colour_is_measured_from_the_border_not_assumed():
    dark = page(value=0.07)
    box(dark, 160, 120, 480, 360)
    assert page_colour(dark) == pytest.approx(0.07, abs=0.01)
    light = page(value=0.98)
    box(light, 160, 120, 480, 360, value=0.1)
    assert page_colour(light) == pytest.approx(0.98, abs=0.01)


def test_light_and_dark_are_the_same_measurement_with_the_sign_flipped():
    dark = box(page(value=0.07), 160, 120, 480, 360, value=0.9)
    light = box(page(value=0.95), 160, 120, 480, 360, value=0.1)
    assert ink(dark).sum() == ink(light).sum()


def test_a_png_round_trips_through_read(tmp_path):
    grey = box(page(), 160, 120, 480, 360)
    loaded = read(write(tmp_path, grey))
    assert loaded.shape == grey.shape
    assert ink(loaded).sum() == pytest.approx(ink(grey).sum(), rel=0.02)


# ---- the silhouette, which is the whole correction ----

def test_what_an_outline_encloses_counts_as_inside_it():
    grey = box(page(), 160, 120, 480, 360)
    body = silhouette(ink(grey), step=4)
    assert body[240 // 4, 320 // 4], "the middle of an outlined box is enclosed"
    assert not body[20 // 4, 20 // 4], "the card's corner is not"


def test_proximity_is_not_enclosure(tmp_path):
    """The first version measured 'near the ink' and could not tell any of
    anatomy's reference figures apart from a first draft."""
    grey = box(page(), 160, 120, 480, 360)
    body = silhouette(ink(grey), step=4)
    assert not body[(120 - 24) // 4, 320 // 4], "just outside the outline"


def test_quiet_space_around_an_object_is_not_judged(tmp_path):
    grey = box(page(), 260, 200, 380, 280, fill=True)
    found = survey(write(tmp_path, grey), cells=8)
    # the card around a small solid object is never counted as enclosed
    assert all(not c.inside for c in found.cells if c.density == 0 and c.col == 0)


# ---- what it actually reports ----

def test_an_empty_enclosed_region_is_flagged(tmp_path):
    grey = box(page(), 80, 60, 560, 420)
    found = survey(write(tmp_path, grey), cells=8)
    assert found.bare, "an outlined empty box is enclosed and unmarked"
    assert "flat faces" in found.summary()


def test_a_filled_region_is_not_flagged(tmp_path):
    grey = box(page(), 80, 60, 560, 420, fill=True)
    found = survey(write(tmp_path, grey), cells=8)
    assert not found.bare


def test_a_flagged_cell_names_where_to_look(tmp_path):
    grey = box(page(), 80, 60, 560, 420)
    cell = survey(write(tmp_path, grey), cells=8).bare[0]
    assert "+" in cell.crop() and "x" in cell.crop()


def test_nothing_drawn_is_said_plainly(tmp_path):
    found = survey(write(tmp_path, page()), cells=8)
    assert found.summary() == "nothing drawn"


# ---- the finding ----

def test_a_large_correct_flat_face_is_flagged_and_that_is_the_problem():
    """This is the negative result, pinned.

    An outlined panel with nothing on it is exactly what the probe reports, and
    on anatomy's own arcade-cabinet every flagged cell sat on the interior wall
    and side panel — correctly drawn surfaces that are supposed to be empty.
    A model pushed to minimise this number would add clutter to a correct
    panel. If this ever becomes a gate, this test is the one that should have
    stopped it.
    """
    import os
    import tempfile
    grey = box(page(), 80, 60, 560, 420)          # a plain, correctly drawn panel
    with tempfile.TemporaryDirectory() as tmp:
        from PIL import Image
        path = os.path.join(tmp, "panel.png")
        Image.fromarray((grey * 255).astype(np.uint8), mode="L").save(path)
        found = survey(path, cells=8)
    assert found.bare, "the probe calls a correct empty panel unfinished"


def test_enclosed_count_is_the_part_that_survives(tmp_path):
    """It tracks how much of its own extent an object actually fills, which is
    honest — a solid body against a thin diagonal of the same reach."""
    solid = survey(write(tmp_path, box(page(), 80, 60, 560, 420, fill=True),
                         "solid.png"), cells=8)
    thin = page()
    for i in range(480):
        thin[60 + i * 360 // 480, 80 + i] = 0.9
    assert len(solid.inside) > len(survey(write(tmp_path, thin, "thin.png"),
                                          cells=8).inside)


def test_a_hairline_outline_still_seals_the_fill(tmp_path):
    """Striding the downsample dropped one-pixel strokes unless they landed on
    a multiple of step, and the fill leaked out through the gaps."""
    grey = box(page(), 81, 61, 559, 419)        # deliberately off every multiple
    found = survey(write(tmp_path, grey), cells=8)
    assert found.inside, "a hairline box encloses its interior"
