"""Налаштування бота зі змінних середовища (урок 47). Без BOT_TOKEN бот вимкнено — API працює як раніше."""
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

# Telegram приймає secret_token лише з цих символів, 1–256 (https://core.telegram.org/bots/api#setwebhook)
SECRET_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


@dataclass(frozen=True)
class BotSettings:
    token: str
    api_url: str | None = None            # двійник або локальний Bot API server; None — api.telegram.org
    webhook_url: str | None = None        # задано — webhook; ні — polling (python -m news_hub.bot)
    webhook_secret: str | None = None
    admin_ids: frozenset[int] = frozenset()


def load_bot_settings(env: Mapping[str, str] = os.environ) -> BotSettings | None:
    token = env.get("BOT_TOKEN", "")
    if not token:
        return None
    webhook_url = env.get("TELEGRAM_WEBHOOK_URL") or None
    secret = env.get("TELEGRAM_WEBHOOK_SECRET") or None
    if webhook_url:
        if not webhook_url.startswith("https://") and not env.get("TELEGRAM_API_URL"):
            raise RuntimeError("TELEGRAM_WEBHOOK_URL: Telegram надсилає webhook лише на https://")
        if secret is None or not SECRET_TOKEN.fullmatch(secret):
            raise RuntimeError("TELEGRAM_WEBHOOK_SECRET: 32–256 символів A-Z a-z 0-9 _ - "
                               "(згенеруй: python -c 'import secrets; print(secrets.token_urlsafe(48))')")
    admin_ids = frozenset(int(item) for item in env.get("BOT_ADMIN_IDS", "").replace(" ", "").split(",") if item)
    return BotSettings(token=token, api_url=env.get("TELEGRAM_API_URL") or None, webhook_url=webhook_url,
                       webhook_secret=secret, admin_ids=admin_ids)
