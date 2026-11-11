"""CRUD окремої новини: 201 / 409 / 404 / PATCH / 204 — і що це справді записано в базу."""
from fastapi.testclient import TestClient

NEW = {"title": "Гривня зміцнилася до долара на міжбанку", "url": "https://www.rbc.ua/ukr/news/hryvnia-777.html",
       "published_time": "09:05"}


def test_create_returns_201_with_id_and_derived_fields(client: TestClient) -> None:
    response = client.post("/api/news", json=NEW)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1 and body["scraped_at"]
    assert (body["lang"], body["category"], body["source"], body["published_time"]) == ("uk", "Новини", "rbc.ua", "09:05:00")


def test_same_url_twice_is_409(client: TestClient) -> None:
    client.post("/api/news", json=NEW)
    response = client.post("/api/news", json=NEW)
    assert response.status_code == 409
    assert client.get("/api/news/count").json() == {"count": 1}


def test_invalid_news_is_422(client: TestClient) -> None:
    response = client.post("/api/news", json={"title": "Коротко", "url": "https://example.com/ukr/news/x.html"})
    assert response.status_code == 422
    assert {error["loc"][0] for error in response.json()["detail"]} == {"title", "url"}


def test_get_and_404(client: TestClient) -> None:
    created = client.post("/api/news", json=NEW).json()
    assert client.get(f"/api/news/{created['id']}").json() == created
    missing = client.get("/api/news/999")
    assert (missing.status_code, missing.json()) == (404, {"detail": "новини 999 немає"})


def test_patch_changes_only_given_fields_and_persists(client: TestClient) -> None:
    created = client.post("/api/news", json=NEW).json()
    patched = client.patch(f"/api/news/{created['id']}", json={"category": "Економіка"}).json()
    assert (patched["category"], patched["title"]) == ("Економіка", NEW["title"])
    assert client.get(f"/api/news/{created['id']}").json()["category"] == "Економіка"   # новий запит — нова сесія
    assert client.patch(f"/api/news/{created['id']}", json={"title": "Коротко"}).status_code == 422


def test_delete_one(client: TestClient) -> None:
    created = client.post("/api/news", json=NEW).json()
    response = client.delete(f"/api/news/{created['id']}")
    assert (response.status_code, response.content) == (204, b"")
    assert client.get(f"/api/news/{created['id']}").status_code == 404
    assert client.delete(f"/api/news/{created['id']}").status_code == 404


def test_stats_come_from_group_by(client: TestClient) -> None:
    client.post("/api/scrape", json={"source": "snapshot"})
    client.patch("/api/news/1", json={"category": "Економіка"})
    stats = client.get("/api/news/stats").json()
    assert stats["category"] == {"Новини": 167, "Економіка": 1}
    assert stats["source"] == {"rbc.ua": 167, "auto.rbc.ua": 1}


def test_failed_commit_is_500_not_200(client: TestClient) -> None:
    """COMMIT у get_db має статися ДО відповіді: якщо він падає — клієнт бачить помилку, а не «201 Created»."""
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

    from news_hub.api import app
    from news_hub.db import get_db

    working_db = app.dependency_overrides[get_db]

    async def broken_commit_db() -> AsyncIterator[AsyncSession]:
        async for session in working_db():
            yield session
            raise RuntimeError("COMMIT не вдався")    # як обрив з'єднання з базою під час COMMIT

    app.dependency_overrides[get_db] = broken_commit_db
    quiet = TestClient(app, raise_server_exceptions=False, headers=client.headers)   # урок 46: запис — з токеном
    assert quiet.post("/api/news", json=NEW).status_code == 500
    app.dependency_overrides[get_db] = working_db


def test_search_is_case_insensitive_and_literal(client: TestClient) -> None:
    client.post("/api/scrape", json={"source": "snapshot"})
    found = client.get("/api/news/search", params={"q": "ЗЕЛЕНСЬК"}).json()
    assert found and all("зеленськ" in news["title"].lower() for news in found)
    assert client.get("/api/news/search", params={"q": "%%"}).json() == []      # % — символ, а не «будь-що»
    assert client.get("/api/news/search", params={"q": "а"}).status_code == 422
