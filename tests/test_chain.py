"""Sammanfogning: platatest i stallet for gissad troskel."""

import math

from takeoff import chain


def _line(x0, y0, x1, y1):
    return [(x0, y0), (x1, y1)]


def test_collinear_runs_with_a_gap_are_bridged():
    runs = [_line(0, 0, 10, 0), _line(12, 0, 20, 0)]
    merged, bridges = chain._join(runs, gap=3.0, angle_tol=math.radians(2), offset_tol=1.0)
    assert len(bridges) == 1
    assert len(merged) == 1
    assert chain._polyline_length(merged[0]) == 20.0


def test_gap_larger_than_threshold_is_not_bridged():
    runs = [_line(0, 0, 10, 0), _line(30, 0, 40, 0)]
    merged, bridges = chain._join(runs, gap=3.0, angle_tol=math.radians(2), offset_tol=1.0)
    assert bridges == []
    assert len(merged) == 2


def test_perpendicular_runs_are_never_bridged():
    runs = [_line(0, 0, 10, 0), _line(11, 0, 11, 10)]
    _, bridges = chain._join(runs, gap=3.0, angle_tol=math.radians(2), offset_tol=1.0)
    assert bridges == []


def test_laterally_offset_runs_are_not_bridged():
    """Tva parallella ror bredvid varandra ar inte ett ror."""
    runs = [_line(0, 0, 10, 0), _line(12, 5, 20, 5)]
    _, bridges = chain._join(runs, gap=6.0, angle_tol=math.radians(2), offset_tol=1.0)
    assert bridges == []


def test_plateau_is_found_in_a_step_curve():
    curve = [(i * 0.5, v) for i, v in enumerate([10, 10, 10, 20, 20, 20, 20, 20, 20, 30])]
    thr, width, _ = chain.find_plateau(curve)
    assert width > 0
    assert 1.0 < thr < 4.5
