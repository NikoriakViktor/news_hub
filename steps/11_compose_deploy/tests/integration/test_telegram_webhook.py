"""Урок 47: webhook Telegram у FastAPI — секретний заголовок, обробка після відповіді, lifespan.

Урок 49: Telegram недоступний при старті — API однаково стартує, реєстрація повторюється у фоні.
"""
import asyncio
import socket

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
        assert await app.state.bot_setup is True                        # урок 49: реєстрація — фонова задача
        assert (twin.webhook_url, twin.webhook_secret) == ("https://news.example/api/telegram/webhook", WEBHOOK_SECRET)
        assert [method for method, _ in twin.calls] == ["setWebhook", "setMyCommands"]
    assert twin.webhook_url                                              # після зупинки webhook на місці
    app.state.bot = app.state.dispatcher = app.state.telegram = None


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


async def test_api_starts_while_telegram_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Урок 49: у Compose API стартує раніше, ніж мережа до Telegram (чи сам Telegram) доступна.

    Раніше setWebhook у lifespan кидав TelegramNetworkError → «Application startup failed» → контейнер по колу.
    """
    port = free_port()                                                   # тут поки ніхто не слухає
    monkeypatch.setattr("news_hub.api.TELEGRAM_RETRY_DELAYS", (0.05,), raising=False)
    twin = TelegramTwin()
    monkeypatch.setenv("BOT_TOKEN", twin.token)
    monkeypatch.setenv("TELEGRAM_API_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://news.example/api/telegram/webhook")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", WEBHOOK_SECRET)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.2)                                         # кілька невдалих спроб
        assert not app.state.bot_setup.done()                            # API працює, реєстрація ще триває
        await twin.start(port=port)                                      # «Telegram» з'явився
        try:
            assert await asyncio.wait_for(app.state.bot_setup, 5) is True
            assert twin.webhook_url == "https://news.example/api/telegram/webhook"
        finally:
            await twin.stop()
    app.state.bot = app.state.dispatcher = app.state.telegram = None


async def test_wrong_token_does_not_stop_api(twin: TelegramTwin, monkeypatch: pytest.MonkeyPatch) -> None:
    """401 повтором не виправити: бот вимкнено записом у журнал, API працює далі."""
    monkeypatch.setenv("BOT_TOKEN", "999:WRONG")
    monkeypatch.setenv("TELEGRAM_API_URL", twin.url)
    async with app.router.lifespan_context(app):
        assert await asyncio.wait_for(app.state.bot_setup, 5) is False
    assert twin.webhook_url == ""
    app.state.bot = app.state.dispatcher = app.state.telegram = None
