"""aiogram 3 без Telegram: Router і фільтри, middleware, FSM, inline-кнопки, HTML, помилки Bot API, webhook у FastAPI.

    pip install -r requirements.txt
    python telegram_demo.py

`FakeTelegram` — сесія aiogram, яка замість HTTP-запиту до api.telegram.org записує виклик і повертає
JSON у форматі Bot API ({"ok": true, "result": …} або {"ok": false, "error_code": …}). Помилки з цього JSON
перетворює на винятки сам aiogram (`BaseSession.check_response`). Тексти помилок задає фейк — це не Telegram.
"""
import asyncio
import hmac
import html
import itertools
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject, Update
from aiogram.utils.formatting import Bold, Text
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

TOKEN = "123456:TEST-TOKEN"


class FakeTelegram(BaseSession):
    """Сесія aiogram без мережі: `calls` — що бот «надіслав у Telegram», `errors` — відповіді-помилки по черзі."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[dict[str, Any]] = []
        self._ids = itertools.count(100)

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None) -> Any:
        name = method.__api_method__
        # як справжня сесія: Default(parse_mode) → значення з DefaultBotProperties, None — не надсилається
        params = self.prepare_value(method.model_dump(warnings=False), bot=bot, files={}, _dumps_json=False)
        self.calls.append((name, params))
        if self.errors:
            body = {"ok": False, **self.errors.pop(0)}
            return self.check_response(bot, method, body["error_code"], json.dumps(body)).result
        result: Any = True
        if name == "sendMessage":
            result = {"message_id": next(self._ids), "date": int(time.time()), "text": params["text"],
                      "chat": {"id": params["chat_id"], "type": "private"}}
        return self.check_response(bot, method, 200, json.dumps({"ok": True, "result": result})).result

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def close(self) -> None:
        pass


_update_ids = itertools.count(1)


def message_update(text: str, chat_id: int = 1001, first_name: str = "Олена") -> dict[str, Any]:
    """Update так, як його надсилає Telegram: update_id + message з chat, from, text і entities для команди."""
    uid = next(_update_ids)
    message: dict[str, Any] = {"message_id": uid, "date": int(time.time()), "text": text,
                               "chat": {"id": chat_id, "type": "private"},
                               "from": {"id": chat_id, "is_bot": False, "first_name": first_name}}
    if text.startswith("/"):
        message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    return {"update_id": uid, "message": message}


def callback_update(data: str, chat_id: int = 1001) -> dict[str, Any]:
    uid = next(_update_ids)
    return {"update_id": uid, "callback_query": {
        "id": f"cb{uid}", "chat_instance": "ci", "data": data,
        "from": {"id": chat_id, "is_bot": False, "first_name": "Олена"},
        "message": {"message_id": 100, "date": int(time.time()), "text": "…", "chat": {"id": chat_id, "type": "private"}}}}


# --- роутер ----------------------------------------------------------------------------------------

TRACE: list[str] = []
SUBSCRIPTIONS: dict[int, set[str]] = {}


class Subscribe(StatesGroup):
    waiting_word = State()


class Unsubscribe(CallbackData, prefix="unsub"):
    word: str


def build_router() -> Router:
    """Новий Router на кожен виклик: один Router можна підключити лише до одного Dispatcher."""
    router = Router(name="demo")

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        TRACE.append("handler start")
        name = message.from_user.first_name if message.from_user else "друже"
        await message.answer(f"Привіт, <b>{html.escape(name, quote=False)}</b>!")

    @router.message(Command("hello"))
    async def hello(message: Message) -> None:
        TRACE.append("handler hello")
        name = message.from_user.first_name if message.from_user else "друже"
        await message.answer(**Text("Привіт, ", Bold(name), "!").as_kwargs())

    @router.message(Command("subscribe"))
    async def subscribe(message: Message, command: CommandObject, state: FSMContext) -> None:
        TRACE.append("handler subscribe")
        if command.args:
            await save(message, command.args.strip())
            return
        await state.set_state(Subscribe.waiting_word)
        await message.answer("Яке слово відстежувати?")

    @router.message(Subscribe.waiting_word, F.text)
    async def got_word(message: Message, state: FSMContext) -> None:
        TRACE.append("handler got_word")
        await state.clear()
        await save(message, message.text or "")

    @router.callback_query(Unsubscribe.filter())
    async def unsubscribe(query: CallbackQuery, callback_data: Unsubscribe) -> None:
        TRACE.append("handler unsubscribe")
        SUBSCRIPTIONS.get(query.from_user.id, set()).discard(callback_data.word)
        await query.answer(f"Відписано від «{callback_data.word}»")

    @router.message(F.text.startswith("/"))
    async def unknown_command(message: Message) -> None:
        TRACE.append("handler unknown_command")
        await message.answer("Невідома команда. /subscribe &lt;слово&gt;")

    return router


async def save(message: Message, word: str) -> None:
    SUBSCRIPTIONS.setdefault(message.chat.id, set()).add(word.casefold())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Відписатися", callback_data=Unsubscribe(word=word.casefold()).pack())]])
    await message.answer(f"Стежу за «{html.escape(word, quote=False)}»", reply_markup=keyboard)


class Trace(BaseMiddleware):
    def __init__(self, label: str) -> None:
        self.label = label

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        TRACE.append(self.label)
        return await handler(event, data)


def build() -> tuple[Bot, Dispatcher, FakeTelegram]:
    session = FakeTelegram()
    bot = Bot(TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()                                   # FSM за замовчуванням — MemoryStorage
    dp.message.outer_middleware(Trace("outer"))
    dp.message.middleware(Trace("inner"))
    dp.include_router(build_router())
    return bot, dp, session


def show(label: str, value: object) -> None:
    print(f"   {label:<34} {value}")


async def feed(dp: Dispatcher, bot: Bot, raw: dict[str, Any]) -> None:
    TRACE.clear()
    await dp.feed_update(bot, Update.model_validate(raw, context={"bot": bot}))


async def bot_demo() -> None:
    bot, dp, session = build()

    print("--- 1. ім'я з < і &: html.escape або aiogram.utils.formatting")
    await feed(dp, bot, message_update("/start", first_name="<Олена & Co>"))
    name, params = session.calls[-1]
    show(name, f"{params['text']!r} parse_mode={getattr(params.get('parse_mode'), 'value', None)}")
    await feed(dp, bot, message_update("/hello", first_name="<Олена & Co>"))
    name, params = session.calls[-1]
    show(name, f"{params['text']!r} entities={[(e['type'], e['offset'], e['length']) for e in params['entities']]}")

    print("--- 2. порядок: outer middleware → фільтри → inner middleware → handler")
    for text in ["просто текст", "/weather", "/subscribe", "просто текст"]:
        await feed(dp, bot, message_update(text, chat_id=2002))
        show(repr(text), TRACE or "—")
    show("відповіді чату 2002", [p["text"] for n, p in session.calls if p.get("chat_id") == 2002])

    print("--- 3. FSM: /subscribe без слова → стан → наступне повідомлення")
    await feed(dp, bot, message_update("/subscribe", chat_id=3003))
    state = dp.fsm.get_context(bot, chat_id=3003, user_id=3003)
    show("стан після /subscribe", await state.get_state())
    await feed(dp, bot, message_update("Бюджет", chat_id=3003))
    show("стан після «Бюджет»", await state.get_state())
    show("підписки 3003", SUBSCRIPTIONS[3003])
    _, params = session.calls[-1]
    show("callback_data кнопки", params["reply_markup"]["inline_keyboard"][0][0]["callback_data"])

    print("--- 4. натискання inline-кнопки → callback_query")
    await feed(dp, bot, callback_update("unsub:бюджет", chat_id=3003))
    show("handler", TRACE)
    show("виклик Bot API", session.calls[-1])
    show("підписки 3003", SUBSCRIPTIONS[3003])
    try:
        Unsubscribe(word="б" * 40).pack()
    except ValueError as error:
        show("callback_data > 64 байтів", str(error)[:40] + "…")

    print("--- 5. помилки Bot API → винятки aiogram")
    session.errors = [
        {"error_code": 429, "description": "Too Many Requests: retry after 3", "parameters": {"retry_after": 3}},
        {"error_code": 403, "description": "Forbidden: bot was blocked by the user"},
        {"error_code": 400, "description": "Bad Request: can't parse entities"},
    ]
    for _ in range(3):
        try:
            await bot.send_message(1001, "Новина <b>дня</b>")
        except TelegramRetryAfter as error:
            show("429", f"{type(error).__name__}, retry_after={error.retry_after}")
        except TelegramForbiddenError as error:
            show("403", f"{type(error).__name__}: {error.message}")
        except TelegramBadRequest as error:
            show("400", f"{type(error).__name__}: {error.message}")
    await bot.session.close()


# --- webhook у FastAPI ---------------------------------------------------------------------------

SECRET = "s3cr3t-token-" + "x" * 32
SEEN: set[int] = set()


def make_app(bot: Bot, dp: Dispatcher) -> FastAPI:
    app = FastAPI()

    @app.post("/telegram/webhook")
    async def webhook(request: Request, background: BackgroundTasks) -> dict[str, bool]:
        got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(got.encode(), SECRET.encode()):        # порівняння за сталий час
            raise HTTPException(401, "неправильний секрет")
        try:
            update = Update.model_validate(await request.json(), context={"bot": bot})
        except ValueError as error:
            raise HTTPException(400, "це не update") from error
        if update.update_id in SEEN:                                     # Telegram повторює доставку
            return {"ok": True}
        SEEN.add(update.update_id)
        background.add_task(dp.feed_update, bot, update)                 # 200 одразу, обробка — після
        return {"ok": True}

    return app


def webhook_demo() -> None:
    print("--- 6. webhook: секрет, повтор того самого update, обробка після відповіді")
    bot, dp, session = build()
    client = TestClient(make_app(bot, dp))
    update = message_update("/start", chat_id=4004)
    header = "X-Telegram-Bot-Api-Secret-Token"
    for label, headers, body in [("без секрету", {}, update), ("чужий секрет", {header: "guess"}, update),
                                 ("правильний", {header: SECRET}, update), ("той самий update_id", {header: SECRET}, update),
                                 ("не update", {header: SECRET}, {"hello": 1})]:
        response = client.post("/telegram/webhook", json=body, headers=headers)
        show(label, f"{response.status_code} {response.json()}")
    show("sendMessage у чат 4004", sum(1 for n, p in session.calls if n == "sendMessage" and p["chat_id"] == 4004))


if __name__ == "__main__":
    asyncio.run(bot_demo())
    webhook_demo()
