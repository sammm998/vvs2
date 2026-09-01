"""Webbtjansten far inte tumma pa nagon regel motorn foljer."""

import pytest

from tests.conftest import DRAWING, needs_drawing

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from takeoff.web import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_lists_calibrated_projects(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert isinstance(r.json()["kalibrerade_projekt"], list)


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Mät ritningen" in r.text


def test_non_pdf_is_rejected(client):
    r = client.post("/mata", files={"fil": ("x.txt", b"inte en pdf", "text/plain")})
    assert r.status_code == 400


def test_path_traversal_is_blocked(client):
    r = client.get("/hamta/abc/....//etc/passwd")
    assert r.status_code in (400, 404)
    r = client.get("/hamta/not-alnum!/fil.xlsx")
    assert r.status_code in (400, 404)


def test_missing_download_is_not_a_server_error(client):
    r = client.get("/hamta/deadbeef/finnsinte.xlsx")
    assert r.status_code == 404


@needs_drawing
def test_measuring_a_drawing_reports_every_flag(client):
    """Spar, skala och urvalsmetod maste synas i svaret - aldrig bara siffran."""
    with open(DRAWING, "rb") as fh:
        r = client.post("/mata", files={"fil": ("W501A0011-single.pdf", fh.read(), "application/pdf")})
    assert r.status_code == 200
    for expected in ("Spår", "Skala", "Täckning", "Urvalsmetod", "Flaggor"):
        assert expected in r.text
    # Dimensionen far aldrig presenteras som last nar den inte ar det (R10).
    assert "Dimensionen är inte ifylld" in r.text
    assert "/hamta/" in r.text


def test_profiles_are_found_from_any_working_directory(tmp_path, monkeypatch):
    """Profilkatalogen far inte bero pa arbetskatalogen.

    En relativ sokvag fungerar vid utveckling men tappar projektprofilen sa
    snart tjansten startas nagon annanstans - och da faller ritningen tyst
    tillbaka pa okalibrerat lage.
    """
    import os

    from takeoff import layergrammar, profile

    assert os.path.isabs(layergrammar.PROJECT_DIR)
    assert os.path.isabs(profile.PROFILE_DIR)

    monkeypatch.chdir(tmp_path)
    from takeoff import paths

    assert paths.resolve("profiles/_projects") == layergrammar.PROJECT_DIR


def test_profile_dir_can_be_redirected_in_production(monkeypatch, tmp_path):
    from takeoff import paths

    monkeypatch.setenv("TAKEOFF_PROJECT_DIR", str(tmp_path))
    assert paths.resolve("profiles/_projects", env="TAKEOFF_PROJECT_DIR") == str(tmp_path)
