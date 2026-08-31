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
def test_wall_gate_rejects_the_decade_alternative(result):
    """1:500 ger 2 m tjocka vaggar och ska falla pa rimlighetsgrinden."""
    assert any(f.startswith("wall_gate_rejected") for f in result.scale.flags)
