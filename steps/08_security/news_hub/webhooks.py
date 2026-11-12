"""Підписані вхідні webhook: зовнішній планувальник (cron, GitHub Actions) запускає збір новин. Крок 8.

Webhook — це запит **до нас** від іншої системи. Адреса публічна, тож відрізнити справжній запит від
підробленого можна лише за секретом, який знають обидві сторони.

Основа — `backend/api/webhook.py` стартового шаблону бекенду (Telegram): секрет у шляху
`/webhook/{SECRET}` + заголовок `X-Telegram-Bot-Api-Secret-Token`, порівняний через `!=`.
Рефакторинг кроку 8 (схема як у GitHub і Stripe):
- секрет не передається зовсім: відправник надсилає **підпис** HMAC-SHA256(секрет, час + "." + id + "." + тіло);
  перехоплений запит не розкриває секрету, а змінене тіло не пройде перевірку;
- підпис рахується від **сирих байтів** тіла — до розбору JSON (інший порядок ключів — інший підпис);
- час у підписі: запит старший за 5 хвилин — відмова;
- id доставки (`X-Webhook-Delivery`, як `X-GitHub-Delivery`) — теж у підписі: одна подія = один id.
  Повтор — і перехоплений чужий, і власний повтор відправника з новим часом і новим підписом — має той
  самий id, і збір не запускається вдруге. Раніше ключем повтору був підпис: відправник, що повторював
  доставку з новим часом, отримував новий підпис і запускав збір ще раз. Повтор відповідає 200 тим самим
  завданням, а не 409: відправник, що не дочекався відповіді, бачить успіх і не повторює по колу;
- `hmac.compare_digest` — час порівняння не залежить від того, скільки перших символів збіглося;
- секрет не в URL: шлях потрапляє в журнали проксі й сервера.
Telegram (крок 9) підпису не дає — лише секретний заголовок; для нього — `verify_secret_token`.
"""
import hashlib
import hmac
import os
import re
import time
from collections.abc import Mapping

from redis.asyncio import Redis

SIGNATURE_HEADER = "X-Webhook-Signature"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"
DELIVERY_HEADER = "X-Webhook-Delivery"
DELIVERY_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")       # uuid4().hex, secrets.token_urlsafe(16), …
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


def sign(secret: bytes, timestamp: int, delivery: str, body: bytes) -> str:
    """Те, що рахує відправник: sha256=<hex>."""
    message = f"{timestamp}.{delivery}.".encode() + body
    return "sha256=" + hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_signature(secret: bytes, headers: Mapping[str, str], body: bytes, now: float | None = None) -> str:
    """Перевіряє час, id і підпис; повертає id доставки (для захисту від повтору). WebhookRejected — ні."""
    signature, timestamp = headers.get(SIGNATURE_HEADER, ""), headers.get(TIMESTAMP_HEADER, "")
    delivery = headers.get(DELIVERY_HEADER, "")
    if not signature or not (timestamp.isascii() and timestamp.isdigit()):   # "²".isdigit() — True, int("²") — ValueError
        raise WebhookRejected(f"потрібні заголовки {SIGNATURE_HEADER}, {TIMESTAMP_HEADER} і {DELIVERY_HEADER}")
    if not DELIVERY_ID.fullmatch(delivery):
        raise WebhookRejected(f"{DELIVERY_HEADER}: 8–64 символи A-Z a-z 0-9 _ -")
    now = time.time() if now is None else now
    if abs(now - int(timestamp)) > TOLERANCE_SECONDS:
        raise WebhookRejected(f"запит старший за {TOLERANCE_SECONDS} с (або годинник відправника не той)")
    if not hmac.compare_digest(signature.encode(), sign(secret, int(timestamp), delivery, body).encode()):
        raise WebhookRejected("підпис не збігається")
    return delivery


async def claim_delivery(redis: Redis, delivery: str, job_id: str) -> str | None:
    """None — доставка нова, тепер вона за job_id. Інакше — job_id, з яким її вже прийняли.

    SET NX — атомарно: з двох одночасних однакових доставок збір запустить лише одна. Ключ живе вдвічі
    довше за вікно часу: пізніший повтор відкине вже перевірка часу.
    """
    key = f"webhook:delivery:{delivery}"
    if await redis.set(key, job_id, nx=True, ex=2 * TOLERANCE_SECONDS):
        return None
    existing = await redis.get(key)
    return str(existing) if existing is not None else None      # ключ щойно зник — вважаємо доставку новою


def verify_secret_token(expected: bytes, received: str | None) -> bool:
    """Для Telegram (крок 9): заголовок X-Telegram-Bot-Api-Secret-Token, порівняння без витоку часу."""
    return received is not None and hmac.compare_digest(received.encode(), expected)
