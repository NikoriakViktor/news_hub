"""Урок 47: webhook Telegram у FastAPI — секретний заголовок, обробка після відповіді, lifespan."""
import httpx
import pytest

from news_hub.api import app

from tests.telegram_twin import TelegramTwin

from .conftest import WEBHOOK_SECRET

pytestmark = pytest.mark.asyncio
URL = "/api/telegram/webhook"


async def test_update_with_secret_is_answered(bot_api: httpx.AsyncClient, twin: TelegramTwin) -> None:
    response = await bot_api.post(URL, json=twin.make_update("/help"),
                                  headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET})
    assert response.json() == {"ok": True}
    assert twin.sent(1001)[0].startswith("<b>Команди</b>")


@pytest.mark.parametrize("headers", [{}, {"X-Telegram-Bot-Api-Secret-Token": "guess"},
                                     {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET[:-1]}])
async def test_wrong_secret_is_401(bot_api: httpx.AsyncClient, twin: TelegramTwin, headers: dict[str, str]) -> None:
    """JWT адміна в клієнті webhook не допомагає: Telegram не має токена — лише секретний заголовок."""
    response = await bot_api.post(URL, json=twin.make_update("/scrape snapshot"), headers=headers)
    assert response.status_code == 401
    assert twin.sent() == []                                             # update не дійшов до бота


async def test_not_an_update_is_400(bot_api: httpx.AsyncClient) -> None:
    response = await bot_api.post(URL, json={"hello": "world"},
                                  headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET})
    assert response.status_code == 400


async def test_without_bot_503(aclient: httpx.AsyncClient) -> None:
    response = await aclient.post(URL, json={}, headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET})
    assert response.status_code == 503


async def test_lifespan_sets_webhook_and_keeps_it(twin: TelegramTwin, monkeypatch: pytest.MonkeyPatch) -> None:
    """З BOT_TOKEN + TELEGRAM_WEBHOOK_URL застосунок сам реєструє webhook із секретом — і не видаляє його при
    зупинці: під час перезапуску новий процес уже поставив свій webhook."""
    monkeypatch.setenv("BOT_TOKEN", twin.token)
    monkeypatch.setenv("TELEGRAM_API_URL", twin.url)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://news.example/api/telegram/webhook")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", WEBHOOK_SECRET)
    async with app.router.lifespan_context(app):
        assert (twin.webhook_url, twin.webhook_secret) == ("https://news.example/api/telegram/webhook", WEBHOOK_SECRET)
        assert [method for method, _ in twin.calls] == ["setWebhook", "setMyCommands"]
    assert twin.webhook_url                                              # після зупинки webhook на місці
    app.state.bot = app.state.dispatcher = app.state.telegram = None
