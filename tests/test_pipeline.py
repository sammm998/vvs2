"""Genomgaende egenskaper for hela kedjan."""

from tests.conftest import needs_drawing


@needs_drawing
def test_track_a_is_detected(result):
    assert result.triage.track == "A"
    assert result.triage.has_ocgs


@needs_drawing
def test_drawing_text_is_recognised_as_vectorised(result):
    """Ritningstexten ar SHX-vektoriserad; det maste synas i triagen."""
    assert result.triage.text_is_vectorised


@needs_drawing
def test_structural_selection_is_flagged_as_such(result):
    """Utan ankare far resultatet aldrig se ut som ankarbelagd matning (R3)."""
    assert result.selection.method == "structural"
    assert "pipe_style:structural" in result.selection.flags


@needs_drawing
def test_each_vertical_is_counted_once(result):
    centers = [v.center for v in result.net.verticals]
    assert len(centers) == len(set(centers))


@needs_drawing
def test_length_is_measured_on_graph_edges_not_paths(result):
    """Summan over strak ska stamma med summan over kluster."""
    from_strands = sum(s.length for s in result.net.strands)
    from_quantities = sum(q.length_m for q in result.quantities)
    assert abs(result.scale.to_m(from_strands) - from_quantities) < 1e-6
