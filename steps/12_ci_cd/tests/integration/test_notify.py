"""Урок 47: після збору нові новини йдуть підписникам — через API, як це буде в роботі.

Збір — `POST /api/scrape` (знімок rbc.ua, 168 новин), розсилка — фонова задача після відповіді.
"""
import httpx
import pytest

from news_hub.api import app
from news_hub.repository import SubscriptionRepository

from tests.telegram_twin import TelegramTwin

pytestmark = pytest.mark.asyncio


async def subscribe(chat_id: int, *keywords: str) -> None:
    from news_hub.api import get_session_factory
    factory = app.dependency_overrides[get_session_factory]()
    async with factory() as session:
        for keyword in keywords:
            await SubscriptionRepository(session).subscribe(chat_id, keyword)
        await session.commit()


async def subscriptions_of(chat_id: int) -> list[str]:
    from news_hub.api import get_session_factory
    async with app.dependency_overrides[get_session_factory]()() as session:
        return await SubscriptionRepository(session).for_chat(chat_id)


async def test_new_news_reach_subscribers_once(bot_api: httpx.AsyncClient, twin: TelegramTwin) -> None:
    await subscribe(1001, "зеленськ")
    await subscribe(2002, "погода")                                     # у знімку такого немає
    first = await bot_api.post("/api/scrape", json={"source": "snapshot"})
    assert first.status_code == 200
    [notice] = twin.sent(1001)
    assert notice.startswith("🔔 Нові новини за підписками (зеленськ):")
    assert notice.count("<a href=") >= 1 and twin.sent(2002) == []
    await bot_api.post("/api/scrape", json={"source": "snapshot"})     # ті самі новини — не нові
    assert len(twin.sent(1001)) == 1


async def test_blocked_chat_loses_subscriptions(bot_api: httpx.AsyncClient, twin: TelegramTwin) -> None:
    await subscribe(1001, "зеленськ")
    await subscribe(3003, "зеленськ", "україн")
    twin.blocked.add(3003)
    await bot_api.post("/api/scrape", json={"source": "snapshot"})
    assert len(twin.sent(1001)) == 1                                    # решта отримали
    assert await subscriptions_of(3003) == []                           # заблокований — більше не турбуємо
    assert await subscriptions_of(1001) == ["зеленськ"]


async def test_retry_after_429(bot_api: httpx.AsyncClient, twin: TelegramTwin) -> None:
    await subscribe(1001, "зеленськ")
    twin.retry_after = 1                                                # перший sendMessage → 429, retry_after=1
    await bot_api.post("/api/scrape", json={"source": "snapshot"})
    sends = [params for method, params in twin.calls if method == "sendMessage"]
    assert [p.get("error", "ok")[:17] for p in sends] == ["Too Many Requests", "ok"]
    assert len(twin.sent(1001)) == 1


async def test_many_matches_split_into_valid_messages(bot_api: httpx.AsyncClient, twin: TelegramTwin) -> None:
    """Слово з багатьма збігами: кілька повідомлень, кожне ≤ 4096 і з валідним HTML (двійник прийняв усі)."""
    from news_hub import notify
    notify.MAX_NEWS_PER_CHAT, saved = 200, notify.MAX_NEWS_PER_CHAT
    try:
        await subscribe(1001, "в", "у", "на", "і")
        await bot_api.post("/api/scrape", json={"source": "snapshot"})
    finally:
        notify.MAX_NEWS_PER_CHAT = saved
    messages = twin.sent(1001)
    assert len(messages) >= 2 and all(len(text) <= 4096 for text in messages)
    assert not [p for m, p in twin.calls if m == "sendMessage" and "error" in p]


async def test_background_job_notifies_too(bot_api: httpx.AsyncClient, twin: TelegramTwin) -> None:
    await subscribe(1001, "зеленськ")
    job = (await bot_api.post("/api/scrape/jobs", json={"source": "snapshot"})).json()
    status = (await bot_api.get(f"/api/scrape/jobs/{job['job_id']}")).json()
    assert status["status"] == "done" and len(twin.sent(1001)) == 1


async def test_without_bot_nothing_breaks(aclient: httpx.AsyncClient) -> None:
    """Без BOT_TOKEN бота немає: збір працює, як в уроці 46."""
    assert app.state.bot is None
    assert (await aclient.post("/api/scrape", json={"source": "snapshot"})).json()["news_saved"] > 0
