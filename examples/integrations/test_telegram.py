"""Тести бота без Telegram: update — словник, відповідь бота — запис у FakeTelegram.calls.

    pytest -q test_telegram.py
"""
import pytest
from aiogram.exceptions import TelegramForbiddenError
from fastapi.testclient import TestClient

from telegram_demo import SECRET, build, feed, make_app, message_update


@pytest.mark.asyncio
async def test_user_name_is_escaped() -> None:
    bot, dp, session = build()
    await feed(dp, bot, message_update("/start", first_name="<script>"))
    assert session.calls[-1][1]["text"] == "Привіт, <b>&lt;script&gt;</b>!"


@pytest.mark.asyncio
async def test_fsm_state_is_per_chat() -> None:
    bot, dp, session = build()
    await feed(dp, bot, message_update("/subscribe", chat_id=11))
    await feed(dp, bot, message_update("ціни", chat_id=22))           # інший чат — стану немає
    assert [p["chat_id"] for n, p in session.calls if n == "sendMessage"] == [11]
    assert await dp.fsm.get_context(bot, chat_id=11, user_id=11).get_state() == "Subscribe:waiting_word"


@pytest.mark.asyncio
async def test_forbidden_is_an_exception_not_a_silent_failure() -> None:
    bot, _, session = build()
    session.errors = [{"error_code": 403, "description": "Forbidden: bot was blocked by the user"}]
    with pytest.raises(TelegramForbiddenError):
        await bot.send_message(1, "x")


def test_webhook_rejects_wrong_secret_and_duplicates() -> None:
    bot, dp, session = build()
    client = TestClient(make_app(bot, dp))
    update = message_update("/start", chat_id=33)
    assert client.post("/telegram/webhook", json=update).status_code == 401
    headers = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
    assert client.post("/telegram/webhook", json=update, headers=headers).status_code == 200
    assert client.post("/telegram/webhook", json=update, headers=headers).status_code == 200
    assert sum(1 for n, p in session.calls if n == "sendMessage" and p["chat_id"] == 33) == 1
