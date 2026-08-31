import os
import pytest

DRAWING = "data/W501A0011-single.pdf"


def _have(path):
    return os.path.exists(path)


needs_drawing = pytest.mark.skipif(
    not _have(DRAWING), reason="ritningen ligger i data/ som ar gitignorerad"
)


@pytest.fixture(scope="session")
def sheet():
    from takeoff import extract

    return extract.load(DRAWING)


@pytest.fixture(scope="session")
def result():
    from takeoff import pipeline

    return pipeline.run(DRAWING)
