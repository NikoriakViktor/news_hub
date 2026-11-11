"""Урок 47: команди бота — aiogram по-справжньому, «Telegram» — двійник (tests/telegram_twin.py).

Кожен тест надсилає update через `dp.feed_update` (як це робить webhook чи polling) і дивиться, що бот
надіслав у «Telegram». Двійник перевіряє HTML за правилами Bot API: невалідна розмітка = бот мовчить.
"""
import pytest

from news_hub.models import NewsItem
from news_hub.repository import NewsRepository, SubscriptionRepository
from news_hub.snapshot import load_snapshot
from news_hub.models import validate_news

from .conftest import BotHarness

pytestmark = pytest.mark.asyncio


async def add_news(telegram: BotHarness, *titles: str) -> None:
    async with telegram.factory() as session:
        repo = NewsRepository(session)
        for number, title in enumerate(titles, 1):
            await repo.create(NewsItem.model_validate(
                {"title": title, "url": f"https://www.rbc.ua/ukr/news/test-{number}.html"}))
        await session.commit()


async def test_start_escapes_user_name(telegram: BotHarness) -> None:
    """Ім'я в Telegram може містити будь-що — у HTML-повідомлення воно йде екранованим."""
    [reply] = await telegram.say("/start", first_name="<Олена & Ко>")
    assert "<b>&lt;Олена &amp; Ко&gt;</b>" in reply
    assert "/subscribe &lt;слово&gt;" in reply


async def test_news_newest_first(telegram: BotHarness) -> None:
    assert await telegram.say("/news") == ["Новин поки немає."]
    await add_news(telegram, "Перша новина про бюджет", "Друга новина про <теги> & знаки", "Третя новина дня")
    [reply] = await telegram.say("/news 2")
    assert reply.index("Третя") < reply.index("Друга") and "Перша" not in reply
    assert "про &lt;теги&gt; &amp; знаки" in reply                      # двійник прийняв — HTML валідний
    assert '<a href="https://www.rbc.ua/ukr/news/test-3.html">' in reply
    assert await telegram.say("/news багато") == ["Використання: /news [1–10]"]


async def test_subscriptions(telegram: BotHarness) -> None:
    assert await telegram.say("/subscribe Бюджет") == ["✅ Підписка на «бюджет»"]
    assert await telegram.say("/subscribe бюджет") == ["Підписка на «бюджет» уже є"]
    for bad in ("/subscribe", "/subscribe а", "/subscribe <b>", "/subscribe два слова"):
        assert (await telegram.say(bad))[0].startswith("Використання: /subscribe")
    assert await telegram.say("/subscriptions") == ["Твої підписки: «бюджет»"]
    assert await telegram.say("/subscriptions", chat_id=2002) == ["Підписок немає. Додай: /subscribe &lt;слово&gt;"]
    assert await telegram.say("/unsubscribe бюджет") == ["Підписку на «бюджет» скасовано"]
    assert await telegram.say("/unsubscribe бюджет") == ["Такої підписки немає"]


async def test_subscription_limit(telegram: BotHarness) -> None:
    for number in range(10):
        await telegram.say(f"/subscribe слово{number}")
    assert (await telegram.say("/subscribe одинадцяте"))[0].startswith("Не більше 10 підписок")
    async with telegram.factory() as session:
        assert len(await SubscriptionRepository(session).for_chat(1001)) == 10


async def test_digest_uses_llm_and_stores_analysis(telegram: BotHarness) -> None:
    await add_news(telegram, "НБУ знизив облікову ставку до 13%", "Синоптики прогнозують заморозки")
    [reply] = await telegram.say("/digest")
    assert reply.startswith("🧭 <b>Дайджест</b>: 2 з 2 останніх новин")
    async with telegram.factory() as session:
        assert len(await NewsRepository(session).find_unanalyzed(10)) == 0          # аналіз збережено в базі


async def test_digest_without_llm(telegram: BotHarness) -> None:
    from news_hub.bot.factory import create_dispatcher
    telegram.dp = create_dispatcher(telegram.factory, telegram.redis, None)  # type: ignore[arg-type]
    await add_news(telegram, "Новина без аналізу моделлю")
    assert await telegram.say("/digest") == ["LLM не налаштовано — у дайджесті лише вже проаналізовані новини."]


async def test_rate_limit_answers_once(telegram: BotHarness) -> None:
    replies = [await telegram.say("/help") for _ in range(22)]
    assert all(len(r) == 1 and r[0].startswith("<b>Команди</b>") for r in replies[:20])
    assert replies[20] == ["⏳ Забагато запитів: 20 за 60 с. Спробуй через 60 с."]
    assert replies[21] == []                                                    # далі — мовчки
    assert (await telegram.say("/help", chat_id=2002))[0].startswith("<b>Команди</b>")   # інших не зачепило


async def test_scrape_is_admin_only(telegram: BotHarness) -> None:
    await telegram.say("/subscribe зеленський", chat_id=2002)
    assert await telegram.say("/scrape snapshot", chat_id=2002) == ["Ця команда — лише для адміністратора."]
    [reply] = await telegram.say("/scrape snapshot")                           # 1001 — адмін
    valid, rejected = validate_news(load_snapshot())
    assert reply == f"Зібрано: 168, нових: {len(valid)}, відхилено: {len(rejected)}; сповіщено чатів: 1"
    [notice] = telegram.twin.sent(2002)[-1:]
    assert notice.startswith("🔔 Нові новини за підписками (зеленський):")


async def test_unknown_text(telegram: BotHarness) -> None:
    assert await telegram.say("привіт") == ["Не знаю такої команди. /help — що я вмію"]


async def test_group_chat_id_fits(telegram: BotHarness) -> None:
    """Групи в Telegram мають id на кшталт -1001234567890 — більше за 32 біти (у PostgreSQL це BIGINT)."""
    group = -1001234567890
    assert await telegram.say("/subscribe бюджет", chat_id=group) == ["✅ Підписка на «бюджет»"]
    async with telegram.factory() as session:
        assert await SubscriptionRepository(session).by_chat() == {group: ["бюджет"]}
