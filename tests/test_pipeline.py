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
def test_selection_method_is_always_declared(result):
    """Metoden far aldrig vara underforstadd.

    Ett strukturellt urval ar betydligt osakrare an ett som foljer projektets
    lagerregel, och skillnaden maste synas i leveransen (R3).
    """
    assert result.selection.method in {"layer_rule", "anchor_vote", "structural"}
    flags = result.selection.flags
    if result.selection.method == "structural":
        assert "pipe_style:structural" in flags
    elif result.selection.method == "layer_rule":
        assert any(f.startswith("pipe_style:layer_rule:") for f in flags)


@needs_drawing
def test_each_vertical_is_counted_once(result):
    centers = [v.center for v in result.net.verticals]
    assert len(centers) == len(set(centers))


@needs_drawing
def test_length_is_measured_on_graph_edges_not_paths(result):
    """Summan over strak = mangd + maskad langd. Inget forsvinner (R6/R10)."""
    from_strands = result.scale.to_m(sum(s.length for s in result.net.strands))
    accounted = result.total_length_m + result.masked_length_m
    assert abs(from_strands - accounted) < 1e-6


@needs_drawing
def test_masked_length_is_reported_not_discarded(result):
    """Langd i maskad zon far aldrig tystas bort - den bar en egen flagga."""
    for q in result.quantities:
        if q.masked_length_m > 0:
            assert "length_in_masked_zone_excluded" in q.flags
