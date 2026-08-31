"""R4 - skalan verifieras geometriskt, aldrig antas."""

import pytest

from takeoff import scale
from tests.conftest import needs_drawing


def test_candidate_set_keeps_only_standard_scales():
    # 5,6695 pt per etikettenhet: dm ger 1:50, m ger 1:500, cm ger 1:5 (ej standard)
    cands = scale._candidate_scales(5.6695, scale.GRID_LABEL_UNITS_MM)
    assert set(cands) == {50.0, 500.0}


def test_snap_rejects_non_standard():
    assert scale._snap(50.02) == 50.0
    assert scale._snap(37.0) is None


def test_result_refuses_to_measure_without_a_scale():
    r = scale.ScaleResult(None, False, [], None, ["no_geometric_source"], [])
    with pytest.raises(ValueError):
        _ = r.m_per_pt


@needs_drawing
def test_scale_is_verified_by_at_least_two_sources(result):
    sc = result.scale
    assert sc.value == 50.0
    assert sc.verified, f"skalan overifierad: {sc.flags}"
    assert sc.error_pct is not None and sc.error_pct <= 0.5
    assert len(sc.candidates) == 1, "flera standardskalor overlevde - tvetydigt"


@needs_drawing
def test_scale_rests_on_at_least_two_independent_sources(result):
    """En ensam kalla far aldrig faststalla skalan (R4)."""
    names = {s.name for s in result.scale.sources if s.ok}
    assert len(names & {"grid", "scalebar", "project_scalebar"}) >= 2
    assert "single_source_only" not in result.scale.flags


def test_ambiguous_scale_is_never_resolved_by_picking_one():
    """Flera overlevande standardskalor => ingen skala alls, inte den minsta.

    Det var precis detta fel som lat 0013 matas i 1:20 och gav -59 %.
    """
    import takeoff.scale as sc

    bar = sc.ScaleSource("scalebar", 283.56, {50.0: 49.98, 100.0: 99.97, 200.0: 199.9})
    support = {50.0: [bar], 100.0: [bar], 200.0: [bar]}
    surviving = sorted(support)
    assert len(surviving) > 1
    # Motsvarande logik i determine(): tvetydigt => value None, verified False
    result = sc.ScaleResult(None, False, [bar], None, ["ambiguous"], surviving)
    assert result.value is None
    with pytest.raises(ValueError):
        _ = result.m_per_pt
