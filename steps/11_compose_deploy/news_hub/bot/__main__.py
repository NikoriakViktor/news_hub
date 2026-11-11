"""Бот у режимі polling — для розробки: python -m news_hub.bot

Бот сам питає Telegram «є нові повідомлення?» (getUpdates). Webhook на цей час вимикається: Telegram не
віддає оновлення обома способами одночасно. На сервері — webhook у FastAPI (TELEGRAM_WEBHOOK_URL).
"""
import asyncio
import logging

from ..cache import make_redis
from ..db import SessionFactory
from ..llm import make_llm
from .factory import create_bot, create_dispatcher, set_commands
from .settings import load_bot_settings


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_bot_settings()
    if settings is None:
        raise SystemExit("Задай BOT_TOKEN (від @BotFather); для двійника — ще TELEGRAM_API_URL")
    redis, llm = make_redis(), make_llm()
    bot = create_bot(settings.token, settings.api_url)
    dp = create_dispatcher(SessionFactory, redis, llm, settings.admin_ids)
    try:
        await bot.delete_webhook()
        await set_commands(bot)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        if llm is not None:
            await llm.aclose()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
