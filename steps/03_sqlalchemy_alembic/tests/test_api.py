"""API через TestClient: запити йдуть у застосунок без мережі й без uvicorn.

Фікстура `client` (conftest.py) дає порожню тестову базу і скрапер-заглушку.
"""
import pytest
from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_empty_store(client: TestClient) -> None:
    assert client.get("/api/news").json() == []
    assert client.get("/api/news/count").json() == {"count": 0}


def test_scrape_snapshot_then_filter(client: TestClient) -> None:
    report = client.post("/api/scrape", json={"source": "snapshot"}).json()
    assert (report["news_found"], report["news_valid"], report["news_saved"]) == (168, 168, 168)

    uk = client.get("/api/news", params={"lang": "uk", "limit": 1000}).json()
    assert len(uk) == 30 and all(n["lang"] == "uk" for n in uk)
    assert client.get("/api/news/stats").json()["lang"] == {"ru": 138, "uk": 30}


def test_scrape_twice_saves_nothing_new(client: TestClient) -> None:
    client.post("/api/scrape", json={"source": "snapshot"})
    again = client.post("/api/scrape", json={"source": "snapshot"}).json()
    assert (again["news_saved"], again["news_total"]) == (0, 168)


def test_live_scrape_uses_scraper_and_rejects_bad_items(client: TestClient) -> None:
    report = client.post("/api/scrape", json={"mode": "sequential"}).json()
    assert (report["news_found"], report["news_valid"], report["news_saved"]) == (2, 1, 1)
    assert report["rejected"][0].startswith("https://www.rbc.ua/ukr/news/short-2.html: title:")


@pytest.mark.parametrize(("method", "url", "kwargs", "field"), [
    ("get", "/api/news", {"params": {"limit": 0}}, "limit"),
    ("get", "/api/news", {"params": {"lang": "en"}}, "lang"),
    ("post", "/api/scrape", {"json": {"mode": "fast"}}, "mode"),
    ("post", "/api/scrape", {"json": {"pages": ["https://example.com/"]}}, "pages"),
])
def test_bad_input_is_422(client: TestClient, method: str, url: str, kwargs: dict, field: str) -> None:
    response = getattr(client, method)(url, **kwargs)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == field


def test_delete_all(client: TestClient) -> None:
    client.post("/api/scrape", json={"source": "snapshot"})
    assert client.delete("/api/news").json() == {"deleted": 168}
    assert client.get("/api/news/count").json() == {"count": 0}


def test_openapi_lists_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {"/health", "/api/news", "/api/news/count", "/api/news/stats", "/api/scrape",
                          "/api/news/{news_id}", "/api/news/search"}
    assert set(paths["/api/news/{news_id}"]) == {"get", "patch", "delete"}
    assert set(paths["/api/news"]) == {"get", "post", "delete"}
