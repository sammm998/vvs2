"""R8 - transformen ar den enda platsen som ror koordinatsystemet."""

import math

import pymupdf
import pytest

from takeoff.normalize import page_transform


def _page(rotate: int, w: float = 400.0, h: float = 200.0):
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    if rotate:
        page.set_rotation(rotate)
    return doc, page


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
def test_transform_maps_page_into_first_quadrant(rotate):
    doc, page = _page(rotate)
    tf = page_transform(page)
    corners = [(0, 0), (400, 0), (400, 200), (0, 200)]
    mapped = [tf.apply(c) for c in corners]
    xs = [p[0] for p in mapped]
    ys = [p[1] for p in mapped]
    assert min(xs) == pytest.approx(0, abs=1e-6)
    assert min(ys) == pytest.approx(0, abs=1e-6)
    assert max(xs) == pytest.approx(tf.width, abs=1e-6)
    assert max(ys) == pytest.approx(tf.height, abs=1e-6)
    doc.close()


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
def test_transform_preserves_lengths(rotate):
    """Rotation far aldrig andra en langd. Skalan skulle folja med."""
    doc, page = _page(rotate)
    tf = page_transform(page)
    a, b = (10.0, 20.0), (110.0, 20.0)
    assert math.dist(tf.apply(a), tf.apply(b)) == pytest.approx(math.dist(a, b))
    doc.close()


@pytest.mark.parametrize("rotate", [90, 270])
def test_rotation_swaps_page_extent(rotate):
    doc, page = _page(rotate)
    tf = page_transform(page)
    assert (tf.width, tf.height) == pytest.approx((200.0, 400.0))
    doc.close()


def test_diagonal_is_relative_reference():
    doc, page = _page(0, 300.0, 400.0)
    tf = page_transform(page)
    assert tf.diagonal == pytest.approx(500.0)
    doc.close()
