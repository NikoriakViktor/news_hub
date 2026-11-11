"""Урок 46: підпис webhook — HMAC від часу й сирого тіла, вікно часу, повтор."""
import fakeredis
import pytest

from news_hub.webhooks import (SIGNATURE_HEADER, TIMESTAMP_HEADER, WebhookRejected, remember_delivery, sign,
                               verify_secret_token, verify_signature)

SECRET = b"w" * 40
NOW = 1_790_000_000
BODY = b'{"source": "snapshot"}'


def headers(timestamp: int = NOW, body: bytes = BODY, secret: bytes = SECRET) -> dict[str, str]:
    return {SIGNATURE_HEADER: sign(secret, timestamp, body), TIMESTAMP_HEADER: str(timestamp)}


def test_valid_signature() -> None:
    assert verify_signature(SECRET, headers(), BODY, now=NOW + 10).startswith("sha256=")


@pytest.mark.parametrize(("case", "request_headers", "body"), [
    ("змінене тіло", headers(), b'{"source": "live"}'),
    ("той самий JSON, інший порядок байтів", headers(), b'{"source":"snapshot"}'),
    ("чужий секрет", headers(secret=b"x" * 40), BODY),
    ("старий запит", headers(timestamp=NOW - 301), BODY),
    ("час з майбутнього", headers(timestamp=NOW + 301), BODY),
    ("час змінено, підпис старий", {**headers(), TIMESTAMP_HEADER: str(NOW + 1)}, BODY),
    ("немає заголовків", {}, BODY),
    ("час не число", {**headers(), TIMESTAMP_HEADER: "вчора"}, BODY),
])
def test_rejected(case: str, request_headers: dict[str, str], body: bytes) -> None:
    with pytest.raises(WebhookRejected) as error:
        verify_signature(SECRET, request_headers, body, now=NOW)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_replay_is_409() -> None:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    signature = verify_signature(SECRET, headers(), BODY, now=NOW)
    await remember_delivery(redis, signature)
    with pytest.raises(WebhookRejected) as error:
        await remember_delivery(redis, signature)
    assert error.value.status_code == 409
    assert 0 < await redis.ttl(f"webhook:seen:{signature}") <= 600


def test_telegram_secret_token() -> None:
    assert verify_secret_token(SECRET, SECRET.decode())
    assert not verify_secret_token(SECRET, None) and not verify_secret_token(SECRET, "w" * 39)
