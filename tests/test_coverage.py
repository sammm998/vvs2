"""R6 - tackningen ska alltid vara 1,00. Detta ar ett assert, inte ett debugmatt."""

from tests.conftest import needs_drawing


@needs_drawing
def test_every_path_lands_in_exactly_one_cluster(sheet):
    from takeoff import styles

    index = styles.build(sheet)
    assigned = [pid for c in index.clusters for pid in c.path_ids]
    assert len(assigned) == len(sheet.paths)
    assert len(set(assigned)) == len(sheet.paths)


@needs_drawing
def test_accepted_plus_blocked_equals_total(result):
    accepted = sum(
        len(result.styles.get(cid).path_ids) for cid in result.selection.pipe_clusters
    )
    assert accepted + len(result.selection.blocked) == len(result.sheet.paths)
    assert result.coverage == 1.0


@needs_drawing
def test_every_blocked_path_has_a_reason_and_step(result):
    for b in result.selection.blocked:
        assert b.reason
        assert b.step


@needs_drawing
def test_no_path_is_both_accepted_and_blocked(result):
    accepted = {
        pid for cid in result.selection.pipe_clusters for pid in result.styles.get(cid).path_ids
    }
    blocked = {b.path_id for b in result.selection.blocked}
    assert not (accepted & blocked)
