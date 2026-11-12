"""Тести прикладу: так їх запускає workflow з ../workflows/ci.yml (без REDIS_URL — без Redis)."""
import os

from fastapi.testclient import TestClient

from main import app


def test_health() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_whoami_uses_forwarded_scheme_only_from_trusted_proxy() -> None:
    with TestClient(app) as client:
        body = client.get("/whoami", headers={"X-Forwarded-Proto": "https"}).json()
    assert body["scheme"] == "http"          # TestClient — не uvicorn: заголовки проксі ніхто не розбирає


def test_visits() -> None:
    with TestClient(app) as client:
        first = client.get("/visits").json()["visits"]
        second = client.get("/visits").json()["visits"]
    if os.getenv("REDIS_URL"):
        assert second == first + 1           # у CI — справжній Redis із services
    else:
        assert first is None and second is None
