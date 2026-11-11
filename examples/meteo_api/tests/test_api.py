"""Смоук-тести Meteo API v2 на фікстурі з однією справжньою телеграмою (урок 25: pytest)."""
import time

import pytest
from fastapi.testclient import TestClient

from meteo_api.app import create_app
from meteo_api.storage import DATA_DIR, MeteoRepository

OBS_URL = "/api/v1/stations/34504/observations"


@pytest.fixture
def client():
    repo = MeteoRepository.from_files(DATA_DIR / "stations_sample.csv", DATA_DIR / "synop_sample.csv")
    return TestClient(create_app(repo))


def test_station_and_404(client):
    assert client.get("/api/v1/stations/34504").json()["name"] == "Дніпро"
    response = client.get("/api/v1/stations/99999")
    assert response.status_code == 404
    assert "99999" in response.json()["detail"]


def test_decoded_observation(client):
    obs = client.get(f"{OBS_URL}/2024-09-02T18:00Z").json()
    assert (obs["temperature"], obs["pressure"], obs["sea_level_pressure"]) == (25.1, 998.9, 1015.1)
    assert obs["relative_humidity"] == 47


def test_fields_and_bad_fields(client):
    items = client.get(OBS_URL, params={"fields": "time,temperature"}).json()["items"]
    assert items == [{"time": "2024-09-02T18:00Z", "temperature": 25.1}]
    assert client.get(OBS_URL, params={"fields": "colour"}).status_code == 400


def test_create_conflict_validation(client):
    body = {"time": "2024-09-02T21:00Z", "temperature": 21.4}
    created = client.post(OBS_URL, json=body)
    assert created.status_code == 201
    assert created.headers["Location"] == f"{OBS_URL}/2024-09-02T21:00Z"
    assert client.post(OBS_URL, json=body).status_code == 409
    assert client.post(OBS_URL, json={"time": "2024-09-03T00:00Z", "temperature": 99}).status_code == 422


def test_pagination(client):
    for hour in range(0, 24, 3):
        client.post(OBS_URL, json={"time": f"2024-09-03T{hour:02d}:00Z", "temperature": 15 + hour / 3})
    first = client.get(OBS_URL, params={"limit": 4}).json()
    assert first["total"] == 9 and len(first["items"]) == 4 and first["next"].endswith("offset=4&limit=4")
    last = client.get(OBS_URL, params={"limit": 4, "offset": 8}).json()
    assert len(last["items"]) == 1 and last["next"] is None


def test_patch_and_delete(client):
    url = f"{OBS_URL}/2024-09-02T18:00Z"
    patched = client.patch(url, json={"temperature": 25.3}).json()
    assert patched["temperature"] == 25.3 and patched["pressure"] == 998.9
    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 404


def test_import_accepted(client):
    csv_line = "34504,2024,09,02,18,00,AAXX 02181 34504 32975 51106 10251 20129 39989 40151 52027 80001 333 10330="
    response = client.post("/api/v1/imports", json={"csv": csv_line})
    assert response.status_code == 202
    job = client.get(response.headers["Location"]).json()
    assert job["status"] == "done" and job["added"] == 1
