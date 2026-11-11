"""Урок 46: POST /api/webhooks/scrape — зовнішній планувальник запускає збір, підписуючи запит HMAC."""
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from news_hub.api import app
from news_hub.webhooks import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

SECRET = os.environ["WEBHOOK_SECRET"].encode()      # з conftest.py
BODY = json.dumps({"source": "snapshot"}).encode()


def signed(body: bytes = BODY, secret: bytes = SECRET, timestamp: int | None = None) -> dict[str, str]:
    timestamp = int(time.time()) if timestamp is None else timestamp
    return {SIGNATURE_HEADER: sign(secret, timestamp, body), TIMESTAMP_HEADER: str(timestamp),
            "Content-Type": "application/json"}


def test_signed_request_starts_job_without_jwt(anon: TestClient) -> None:
    response = anon.post("/api/webhooks/scrape", content=BODY, headers=signed())
    assert response.status_code == 202, response.text
    assert (response.json()["kind"], response.json()["source"]) == ("scrape", "snapshot")
    assert anon.get("/api/news/count").json() == {"count": 168}          # фоновий збір знімка відбувся


@pytest.mark.parametrize(("case", "body", "headers"), [
    ("без підпису", BODY, {"Content-Type": "application/json"}),
    ("чужий секрет", BODY, signed(secret=b"z" * 40)),
    ("тіло змінено після підпису", b'{"source": "live"}', signed()),
    ("запит годинної давнини", BODY, signed(timestamp=int(time.time()) - 3600)),
])
def test_rejected_is_401(anon: TestClient, case: str, body: bytes, headers: dict[str, str]) -> None:
    response = anon.post("/api/webhooks/scrape", content=body, headers=headers)
    assert response.status_code == 401, case
    assert anon.get("/api/news/count").json() == {"count": 0}


def test_replay_is_409(anon: TestClient) -> None:
    headers = signed()
    assert anon.post("/api/webhooks/scrape", content=BODY, headers=headers).status_code == 202
    again = anon.post("/api/webhooks/scrape", content=BODY, headers=headers)
    assert (again.status_code, again.json()["detail"]) == (409, "цей запит уже отримано (повтор)")


def test_signature_is_checked_before_json(anon: TestClient) -> None:
    """Непідписане сміття — 401, а не 422: чужий запит не доходить навіть до розбору JSON."""
    assert anon.post("/api/webhooks/scrape", content=b"{not json").status_code == 401
    garbage = b"{not json"
    assert anon.post("/api/webhooks/scrape", content=garbage, headers=signed(garbage)).status_code == 422


def test_disabled_without_secret(anon: TestClient) -> None:
    saved, app.state.webhook_secret = app.state.webhook_secret, None
    try:
        assert anon.post("/api/webhooks/scrape", content=BODY, headers=signed()).status_code == 503
    finally:
        app.state.webhook_secret = saved
