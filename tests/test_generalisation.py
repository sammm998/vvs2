"""Generaliseringsgrind: regeln kalibreras pa EN ritning och maste halla pa de ovriga.

Det ar detta test som skiljer en motor fran en motor kalibrerad mot en enda
ritning. Kalibreringen sker pa 0011; 0013 och 0023 ar HALLNA UTE och far
aldrig pavarka nagon parameter.
"""

import os

import pytest

CAL = "data/W501A0011-single.pdf"
CAL_MARKED = "data/W501A0011-bundle.pdf"
# ritning -> (facit langd i meter, facit antal vertikala ror)
HELD_OUT = {
    "data/W501A0013-single.pdf": (112.9, 24),
    "data/W501A0023-single.pdf": (36.4, 9),
    "data/W501A0014-single.pdf": (50.9, 16),
}

needs_set = pytest.mark.skipif(
    not all(os.path.exists(p) for p in [CAL, CAL_MARKED, *HELD_OUT]),
    reason="ritningarna ligger i data/ som ar gitignorerad",
)


@pytest.fixture(scope="module")
def rule():
    from takeoff import groundtruth, layergrammar, pipeline

    result = pipeline.run(CAL, layer_rule=None)
    geom = groundtruth.load_markup_geometry(CAL_MARKED)
    return layergrammar.calibrate(result, geom)


@needs_set
def test_calibration_yields_a_valid_single_field_rule(rule):
    assert rule.valid, rule.reason
    assert len(rule.tokens) == 1, f"forvantade ett faltvarde, fick {rule.tokens}"
    assert rule.project_key


@needs_set
def test_rule_is_never_reused_across_projects(rule):
    """R2: profilen far ateranvandas inom samma projekt, aldrig mellan."""
    assert rule.applies_to(rule.project_key)
    assert not rule.applies_to("ett-annat-projekt")
    assert not rule.applies_to(None)


@needs_set
@pytest.mark.parametrize("pdf,facit", sorted((k, v[0]) for k, v in HELD_OUT.items()))
def test_held_out_drawing_within_ten_percent(rule, pdf, facit):
    from takeoff import pipeline

    result = pipeline.run(pdf, layer_rule=rule)
    assert result.scale.verified, f"skala overifierad: {result.scale.flags}"
    assert result.scale.value == 50.0
    err = (result.total_length_m - facit) / facit * 100
    assert abs(err) <= 10.0, f"{pdf}: {result.total_length_m:.1f} m mot facit {facit} ({err:+.1f}%)"


@needs_set
@pytest.mark.parametrize("pdf,facit", sorted((k, v[1]) for k, v in HELD_OUT.items()))
def test_held_out_vertical_count_within_ten(rule, pdf, facit):
    from takeoff import pipeline

    result = pipeline.run(pdf, layer_rule=rule)
    n = len(result.net.verticals)
    assert abs(n - facit) <= 10, f"{pdf}: {n} vertikala mot facit {facit}"


@needs_set
@pytest.mark.parametrize("pdf", sorted(HELD_OUT))
def test_masked_zone_is_reported_not_discarded(rule, pdf):
    """Det som maskas bort maste ga att se - annars ar det tyst filtrering."""
    from takeoff import pipeline

    result = pipeline.run(pdf, layer_rule=rule)
    if result.masked_length_m > 0:
        assert any(f.startswith("masked_zone:") for f in result.flags)


@needs_set
@pytest.mark.parametrize("pdf", sorted(HELD_OUT))
def test_held_out_drawing_keeps_full_coverage(rule, pdf):
    from takeoff import pipeline

    result = pipeline.run(pdf, layer_rule=rule)
    assert result.coverage == 1.0
