"""Урок 39: кеш, middleware, rate limit і фоновий збір (Redis — fakeredis або TEST_REDIS_URL)."""
from fastapi.testclient import TestClient

from news_hub.api import app, get_scrapers
from news_hub.middleware import RATE_LIMIT_REQUESTS
from news_hub.scraper import ScrapeOutcome

NEW = {"title": "Гривня зміцнилася до долара на міжбанку", "url": "https://www.rbc.ua/ukr/news/hryvnia-777.html"}


def test_cache_miss_then_hit(client: TestClient) -> None:
    client.post("/api/scrape", json={"source": "snapshot"})
    first = client.get("/api/news", params={"lang": "uk", "limit": 3})
    second = client.get("/api/news", params={"lang": "uk", "limit": 3})
    assert (first.headers["X-Cache"], second.headers["X-Cache"]) == ("MISS", "HIT")
    assert first.json() == second.json() and len(first.json()) == 3
    assert client.get("/api/news", params={"lang": "ru", "limit": 3}).headers["X-Cache"] == "MISS"   # інші параметри


def test_write_invalidates_cache(client: TestClient) -> None:
    client.post("/api/scrape", json={"source": "snapshot"})
    client.get("/api/news/stats")
    assert client.get("/api/news/stats").headers["X-Cache"] == "HIT"
    client.post("/api/news", json=NEW)
    after = client.get("/api/news/stats")
    assert (after.headers["X-Cache"], after.json()["total"]) == ("MISS", 169)


def test_failed_write_keeps_cache(client: TestClient) -> None:
    client.post("/api/news", json=NEW)
    client.get("/api/news/stats")
    assert client.post("/api/news", json=NEW).status_code == 409          # запис не відбувся
    assert client.get("/api/news/stats").headers["X-Cache"] == "HIT"


def test_request_id_and_timing_headers(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"
    assert response.headers["X-Process-Time"].endswith("ms")
    assert len(client.get("/health").headers["X-Request-ID"]) == 8          # згенерований


def test_rate_limit_429_with_retry_after(client: TestClient) -> None:
    statuses = [client.post("/api/scrape", json={"source": "snapshot"}).status_code
                for _ in range(RATE_LIMIT_REQUESTS + 2)]
    assert statuses == [200] * RATE_LIMIT_REQUESTS + [429, 429]
    blocked = client.post("/api/scrape", json={"source": "snapshot"})
    assert 0 < int(blocked.headers["Retry-After"]) <= 60
    assert blocked.headers["X-RateLimit-Remaining"] == "0"
    assert client.get("/api/news/count").status_code == 200                # GET не обмежується


def test_rate_limit_key_without_ttl_heals(client: TestClient) -> None:
    """Старий код ставив TTL лише при count == 1: ключ без TTL блокував назавжди. EXPIRE NX його лікує."""
    redis = app.state.redis
    client.portal.call(redis.set, "rate:scrape:testclient", 99)             # «залишок» після збою, без TTL
    assert client.post("/api/scrape", json={"source": "snapshot"}).status_code == 429
    assert 0 < client.portal.call(redis.ttl, "rate:scrape:testclient") <= 60


def test_background_job_done(client: TestClient) -> None:
    started = client.post("/api/scrape/jobs", json={"source": "snapshot"})
    assert started.status_code == 202 and started.json()["status"] == "queued"
    job = client.get(f"/api/scrape/jobs/{started.json()['job_id']}").json()   # TestClient виконує задачу до повернення
    assert (job["status"], job["news_found"], job["news_saved"]) == ("done", 168, 168)
    assert job["finished_at"] and client.get("/api/news/count").json() == {"count": 168}


def test_background_job_failure_is_recorded(client: TestClient) -> None:
    async def broken(pages: list[str] | None) -> ScrapeOutcome:
        raise ConnectionError("rbc.ua не відповідає")

    app.dependency_overrides[get_scrapers] = lambda: {"async": broken, "sequential": broken}
    job_id = client.post("/api/scrape/jobs", json={}).json()["job_id"]
    job = client.get(f"/api/scrape/jobs/{job_id}").json()
    assert (job["status"], job["error"]) == ("failed", "ConnectionError: rbc.ua не відповідає")


def test_job_invalidates_cache_and_unknown_job_404(client: TestClient) -> None:
    client.get("/api/news/count")
    client.get("/api/news/stats")
    client.post("/api/scrape/jobs", json={"source": "snapshot"})
    assert client.get("/api/news/stats").json()["total"] == 168             # не застарілий 0 з кешу
    assert client.get("/api/scrape/jobs/nope").status_code == 404
