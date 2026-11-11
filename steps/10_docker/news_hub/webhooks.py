"""Підписані вхідні webhook: зовнішній планувальник (cron, GitHub Actions) запускає збір новин. Урок 46.

Webhook — це запит **до нас** від іншої системи. Адреса публічна, тож відрізнити справжній запит від
підробленого можна лише за секретом, який знають обидві сторони.

Основа — `backend/api/webhook.py` зі стартового `production_bot` (Telegram): секрет у шляху
`/webhook/{SECRET}` + заголовок `X-Telegram-Bot-Api-Secret-Token`, порівняний через `!=`.
Рефакторинг уроку 46 (схема як у GitHub і Stripe):
- секрет не передається зовсім: відправник надсилає **підпис** HMAC-SHA256(секрет, час + "." + тіло);
  перехоплений запит не розкриває секрету, а змінене тіло не пройде перевірку;
- підпис рахується від **сирих байтів** тіла — до розбору JSON (інший порядок ключів — інший підпис);
- час у підписі: запит старший за 5 хвилин — відмова; той самий підпис удруге — відмова (Redis SET NX):
  перехоплений запит не можна повторити;
- `hmac.compare_digest` — час порівняння не залежить від того, скільки перших символів збіглося;
- секрет не в URL: шлях потрапляє в журнали проксі й сервера.
Telegram (урок 47) підпису не дає — лише секретний заголовок; для нього — `verify_secret_token`.
"""
import hashlib
import hmac
import os
import time
from collections.abc import Mapping

from redis.asyncio import Redis

SIGNATURE_HEADER = "X-Webhook-Signature"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"
TOLERANCE_SECONDS = 300
MIN_SECRET_LENGTH = 32


class WebhookRejected(Exception):
    """Запит не від того, за кого себе видає (401), або повтор (409)."""

    def __init__(self, reason: str, status_code: int = 401) -> None:
        super().__init__(reason)
        self.status_code = status_code


def load_webhook_secret(env: Mapping[str, str] = os.environ) -> bytes | None:
    """None — webhook вимкнено (503). Короткий секрет — помилка при старті."""
    secret = env.get("WEBHOOK_SECRET", "")
    if not secret:
        return None
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(f"WEBHOOK_SECRET має бути не коротшим за {MIN_SECRET_LENGTH} символи")
    return secret.encode()


def sign(secret: bytes, timestamp: int, body: bytes) -> str:
    """Те, що рахує відправник: sha256=<hex>."""
    digest = hmac.new(secret, str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: bytes, headers: Mapping[str, str], body: bytes, now: float | None = None) -> str:
    """Перевіряє час і підпис; повертає підпис (для захисту від повтору). WebhookRejected — ні."""
    signature, timestamp = headers.get(SIGNATURE_HEADER, ""), headers.get(TIMESTAMP_HEADER, "")
    if not signature or not timestamp.isdigit():
        raise WebhookRejected(f"потрібні заголовки {SIGNATURE_HEADER} і {TIMESTAMP_HEADER}")
    now = time.time() if now is None else now
    if abs(now - int(timestamp)) > TOLERANCE_SECONDS:
        raise WebhookRejected(f"запит старший за {TOLERANCE_SECONDS} с (або годинник відправника не той)")
    if not hmac.compare_digest(signature.encode(), sign(secret, int(timestamp), body).encode()):
        raise WebhookRejected("підпис не збігається")
    return signature


async def remember_delivery(redis: Redis, signature: str) -> None:
    """Той самий підпис удруге за вікно — повтор. Ключ живе вдвічі довше за вікно часу."""
    fresh = await redis.set(f"webhook:seen:{signature}", "1", nx=True, ex=2 * TOLERANCE_SECONDS)
    if not fresh:
        raise WebhookRejected("цей запит уже отримано (повтор)", status_code=409)


def verify_secret_token(expected: bytes, received: str | None) -> bool:
    """Для Telegram (урок 47): заголовок X-Telegram-Bot-Api-Secret-Token, порівняння без витоку часу."""
    return received is not None and hmac.compare_digest(received.encode(), expected)
