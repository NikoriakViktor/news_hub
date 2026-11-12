"""Крок 8: підпис webhook — HMAC від часу, id доставки й сирого тіла; вікно часу; повтор за id доставки."""
import fakeredis
import pytest

from news_hub.webhooks import (DELIVERY_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER, WebhookRejected,
                               claim_delivery, sign, verify_secret_token, verify_signature)

SECRET = b"w" * 40
NOW = 1_790_000_000
BODY = b'{"source": "snapshot"}'
DELIVERY = "d3b07384d113edec"


def headers(timestamp: int = NOW, body: bytes = BODY, secret: bytes = SECRET,
            delivery: str = DELIVERY) -> dict[str, str]:
    return {SIGNATURE_HEADER: sign(secret, timestamp, delivery, body), TIMESTAMP_HEADER: str(timestamp),
            DELIVERY_HEADER: delivery}


def test_valid_signature_returns_delivery_id() -> None:
    assert verify_signature(SECRET, headers(), BODY, now=NOW + 10) == DELIVERY


@pytest.mark.parametrize(("case", "request_headers", "body"), [
    ("змінене тіло", headers(), b'{"source": "live"}'),
    ("той самий JSON, інший порядок байтів", headers(), b'{"source":"snapshot"}'),
    ("чужий секрет", headers(secret=b"x" * 40), BODY),
    ("старий запит", headers(timestamp=NOW - 301), BODY),
    ("час з майбутнього", headers(timestamp=NOW + 301), BODY),
    ("час змінено, підпис старий", {**headers(), TIMESTAMP_HEADER: str(NOW + 1)}, BODY),
    ("id доставки змінено, підпис старий", {**headers(), DELIVERY_HEADER: "aaaaaaaaaaaaaaaa"}, BODY),
    ("немає id доставки", {k: v for k, v in headers().items() if k != DELIVERY_HEADER}, BODY),
    ("id доставки з недозволеними символами", headers(delivery="../../etc/passwd"), BODY),
    ("немає заголовків", {}, BODY),
    ("час не число: isdigit() каже «так», int() падає", {**headers(), TIMESTAMP_HEADER: "²"}, BODY),
])
def test_rejected(case: str, request_headers: dict[str, str], body: bytes) -> None:
    with pytest.raises(WebhookRejected) as error:
        verify_signature(SECRET, request_headers, body, now=NOW)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_same_delivery_is_claimed_once() -> None:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    assert await claim_delivery(redis, DELIVERY, "job1") is None          # нова: тепер за job1
    assert await claim_delivery(redis, DELIVERY, "job2") == "job1"        # повтор: той самий job1
    assert await claim_delivery(redis, "another-delivery", "job3") is None
    assert 0 < await redis.ttl(f"webhook:delivery:{DELIVERY}") <= 600


def test_resent_with_new_timestamp_keeps_delivery_id() -> None:
    """Відправник повторює доставку пізніше: новий час, новий підпис — але той самий id, тож це повтор."""
    first = verify_signature(SECRET, headers(timestamp=NOW), BODY, now=NOW)
    again = verify_signature(SECRET, headers(timestamp=NOW + 60), BODY, now=NOW + 60)
    assert headers(timestamp=NOW)[SIGNATURE_HEADER] != headers(timestamp=NOW + 60)[SIGNATURE_HEADER]
    assert first == again == DELIVERY


def test_telegram_secret_token() -> None:
    assert verify_secret_token(SECRET, SECRET.decode())
    assert not verify_secret_token(SECRET, None) and not verify_secret_token(SECRET, "w" * 39)
