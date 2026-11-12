"""Ендпоінти без бази: get_uow підмінено FakeUnitOfWork."""
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from news_app.api import app, get_uow
from news_app.uow import FakeUnitOfWork


@pytest.fixture
def client() -> Iterator[TestClient]:
    fake = FakeUnitOfWork()
    app.dependency_overrides[get_uow] = lambda: fake
    yield TestClient(app)                 # без `with`: lifespan (create_all у справжній базі) не запускається
    app.dependency_overrides.clear()


def test_create_and_list(client: TestClient) -> None:
    created = client.post("/news", json={"url": "https://example.com/1", "title": "Гривня зміцнилася"})
    assert created.status_code == 201
    assert created.json() == {"id": 1, "url": "https://example.com/1", "title": "Гривня зміцнилася", "views": 0}
    assert [n["id"] for n in client.get("/news").json()] == [1]


def test_duplicate_is_409(client: TestClient) -> None:
    body = {"url": "https://example.com/1", "title": "Гривня зміцнилася"}
    assert client.post("/news", json=body).status_code == 201
    assert client.post("/news", json=body).status_code == 409


def test_rejected_is_422_and_not_saved(client: TestClient) -> None:
    response = client.post("/news", json={"url": "https://example.com/2", "title": "Найкраще казино"})
    assert response.status_code == 422
    assert client.get("/news").json() == []
