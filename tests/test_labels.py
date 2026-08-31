"""Beteckningsgrammatik SYSTEM-TYP[-DIMENSION]."""

from takeoff.groundtruth import parse_label


def test_full_label():
    assert parse_label("S3-R8-110") == ("S3", "R8", "110")
    assert parse_label("KV2-X31-16") == ("KV2", "X31", "16")


def test_label_without_dimension_is_valid():
    """Rader utan dimension ar GILTIGA. dimension = None, inte kasserad."""
    system, material, dim = parse_label("KV2-X31")
    assert (system, material) == ("KV2", "X31")
    assert dim is None


def test_unparseable_label_is_not_invented():
    assert parse_label("Markera") == (None, None, None)
