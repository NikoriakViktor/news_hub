"""API через httpx.AsyncClient + ASGITransport (урок 41).

Те саме, що TestClient, але тест — корутина в тому ж циклі подій, що й застосунок:
- Redis і базу можна викликати напряму через `await`, без `client.portal.call(...)`;
- `asyncio.gather` шле запити **одночасно** — TestClient так не вміє (він синхронний, запит за запитом).
"""
import asyncio

import httpx
import pytest

from news_hub.api import app
from news_hub.middleware import RATE_LIMIT_REQUESTS

pytestmark = pytest.mark.asyncio


async def test_same_api_async(aclient: httpx.AsyncClient) -> None:
    assert (await aclient.get("/health")).json() == {"status": "ok"}
    created = await aclient.post("/api/news", json={"title": "Уряд затвердив новий бюджет на рік",
                                                    "url": "https://www.rbc.ua/ukr/news/budget-1.html"})
    assert created.status_code == 201
    assert (await aclient.get("/api/news/count")).json() == {"count": 1}


async def test_cache_state_is_awaited_directly(aclient: httpx.AsyncClient) -> None:
    """Без portal: той самий Redis-клієнт, що в застосунку, — просто await."""
    assert (await aclient.get("/api/news")).headers["X-Cache"] == "MISS"
    assert (await aclient.get("/api/news")).headers["X-Cache"] == "HIT"
    assert await app.state.redis.get("news:version") is None                  # записів ще не було
    await aclient.post("/api/scrape", json={"source": "snapshot"})
    assert await app.state.redis.get("news:version") == "1"


async def test_concurrent_requests_hit_rate_limit_exactly(aclient: httpx.AsyncClient) -> None:
    """10 запитів одночасно: рівно RATE_LIMIT_REQUESTS пройшли, решта — 429.

    Якби INCR і перевірка були окремими командами (прочитати → порівняти → записати), одночасні
    запити читали б те саме значення лічильника і проскакували б понад ліміт. MULTI/EXEC робить
    «+1 і дізнатися результат» однією дією. Тіло навмисно неправильне (422): ліміт рахує запит
    ще до перевірки тіла — інакше помилковими запитами можна було б засипати сервер без обмежень.

    Межа фейку: fakeredis виконує команду одразу, не віддаючи керування циклу подій, тож гонки на ньому
    не буває — «наївний» лічильник (GET, потім SET) тут теж пройде. Ловить його лише справжній Redis:
    TEST_REDIS_URL=redis://localhost:6379/15 pytest  →  [422]*10 замість [422]*5 + [429]*5.
    """
    total = RATE_LIMIT_REQUESTS * 2
    responses = await asyncio.gather(*(aclient.post("/api/scrape", json={"source": "ftp"}) for _ in range(total)))
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [422] * RATE_LIMIT_REQUESTS + [429] * RATE_LIMIT_REQUESTS
    assert await app.state.redis.get("rate:scrape:127.0.0.1") == str(total)
