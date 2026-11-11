"""Локальний двійник Telegram Bot API — для тестів, ноутбука й запуску без мережі. Урок 47.

Справжній Telegram — https://api.telegram.org/bot<TOKEN>/<method>. aiogram уміє ходити на інший сервер
(`TelegramAPIServer.from_base(...)`) — так працює й офіційний локальний Bot API server. Двійник відповідає
в тому самому форматі (`{"ok": true, "result": ...}` або `{"ok": false, "error_code": ..., "description": ...}`)
і записує кожен виклик: тест бачить, що саме бот «надіслав у Telegram».

Це НЕ Telegram. Двійник відтворює лише задокументовані правила, які потрібні урокові:
- неправильний токен → 401 Unauthorized;
- чат, що заблокував бота → 403 «Forbidden: bot was blocked by the user»;
- забагато запитів → 429 з `parameters.retry_after`;
- parse_mode=HTML: дозволені лише теги з документації; «<», «>», «&» поза тегом — помилка 400
  «can't parse entities» (https://core.telegram.org/bots/api#html-style);
- текст довший за 4096 символів → 400 «message is too long»;
- webhook: setWebhook запам'ятовує url і secret_token; `deliver()` надсилає update туди з заголовком
  X-Telegram-Bot-Api-Secret-Token — як це робить Telegram.

Запуск окремо: python -m tests.telegram_twin --port 8081 --token 123:TEST
Для бота в контейнері (урок 48): --host 0.0.0.0 — на 127.0.0.1 двійника бачить лише сам комп'ютер
Керування ззовні (лише двійник, у Telegram такого немає):
    POST /_twin/say  {"text": "/news", "chat_id": 1001, "first_name": "Олена"}  → update боту
                     (webhook — одразу на його адресу; інакше — у чергу getUpdates)
    GET  /_twin/sent?chat_id=1001                                              → що бот надіслав
"""
import argparse
import asyncio
import itertools
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from aiohttp import web

MAX_TEXT = 4096
ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "span", "tg-spoiler", "a",
                "tg-emoji", "code", "pre", "blockquote"}
TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^<>]*)?)>")
ENTITY = re.compile(r"&(lt|gt|amp|quot|#\d+|#x[0-9a-fA-F]+);")


def html_error(text: str) -> str | None:
    """None — розмітка коректна; інакше — опис помилки, як у Telegram."""
    stack: list[str] = []
    position = 0
    while position < len(text):
        char = text[position]
        if char == "<":
            match = TAG.match(text, position)
            if match is None:
                return f"Bad Request: can't parse entities: unexpected character at byte offset {position}"
            closing, name = match.group(1), match.group(2).lower()
            if name not in ALLOWED_TAGS:
                return f'Bad Request: can\'t parse entities: unsupported start tag "{name}" at byte offset {position}'
            if closing:
                if not stack or stack.pop() != name:
                    return f'Bad Request: can\'t parse entities: can\'t find end tag corresponding to start tag "{name}"'
            else:
                stack.append(name)
            position = match.end()
        elif char == "&":
            match = ENTITY.match(text, position)
            if match is None:
                return f"Bad Request: can't parse entities: unsupported entity at byte offset {position}"
            position = match.end()
        elif char == ">":
            return f"Bad Request: can't parse entities: unexpected end tag at byte offset {position}"
        else:
            position += 1
    if stack:
        return f'Bad Request: can\'t parse entities: can\'t find end tag corresponding to start tag "{stack[-1]}"'
    return None


@dataclass
class TelegramTwin:
    token: str = "123456:TEST-TOKEN"
    bot_username: str = "news_hub_bot"
    blocked: set[int] = field(default_factory=set)        # чати, що заблокували бота
    retry_after: int = 0                                  # наступні N викликів sendMessage → 429
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    webhook_url: str = ""
    webhook_secret: str = ""
    url: str = ""                                         # адреса двійника після start()
    server: Any = None
    _ids: Any = field(default_factory=lambda: itertools.count(1))

    # --- що бот надіслав ---------------------------------------------------
    def sent(self, chat_id: int | None = None) -> list[str]:
        """Тексти успішних sendMessage (для chat_id — лише цьому чату)."""
        return [params["text"] for method, params in self.calls
                if method == "sendMessage" and "error" not in params
                and (chat_id is None or int(params["chat_id"]) == chat_id)]

    # --- update від «користувача» -------------------------------------------
    def make_update(self, text: str, chat_id: int = 1001, first_name: str = "Олена",
                    username: str | None = "olena") -> dict[str, Any]:
        update_id = next(self._ids)
        user = {"id": chat_id, "is_bot": False, "first_name": first_name}
        if username:
            user["username"] = username
        message: dict[str, Any] = {"message_id": update_id, "date": int(time.time()), "text": text,
                                   "chat": {"id": chat_id, "type": "private", "first_name": first_name},
                                   "from": user}
        if text.startswith("/"):
            command = text.split()[0]
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(command)}]
        return {"update_id": update_id, "message": message}

    def push(self, text: str, **user: Any) -> dict[str, Any]:
        """Поставити update в чергу getUpdates (polling)."""
        update = self.make_update(text, **user)
        self.updates.append(update)
        return update

    async def deliver(self, text: str, **user: Any) -> int:
        """Як Telegram у режимі webhook: POST update на збережений url з секретним заголовком."""
        update = self.make_update(text, **user)
        headers = {"X-Telegram-Bot-Api-Secret-Token": self.webhook_secret} if self.webhook_secret else {}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=update, headers=headers) as response:
                return response.status

    # --- сервер -------------------------------------------------------------
    def app(self) -> web.Application:
        application = web.Application()
        application.router.add_post("/bot{token}/{method}", self.handle)
        application.router.add_get("/bot{token}/{method}", self.handle)
        application.router.add_post("/_twin/say", self.control_say)
        application.router.add_get("/_twin/sent", self.control_sent)
        return application

    async def control_say(self, request: web.Request) -> web.Response:
        body = await request.json()
        user = {key: body[key] for key in ("chat_id", "first_name", "username") if key in body}
        if self.webhook_url:
            try:
                return web.json_response({"mode": "webhook", "status": await self.deliver(body["text"], **user)})
            except aiohttp.ClientError as error:           # як Telegram: webhook недоступний — update чекає
                return web.json_response({"mode": "webhook", "error": f"{type(error).__name__}: {error}"},
                                         status=502)
        self.push(body["text"], **user)
        return web.json_response({"mode": "polling", "queued": len(self.updates)})

    async def control_sent(self, request: web.Request) -> web.Response:
        chat_id = request.query.get("chat_id")
        return web.json_response(self.sent(int(chat_id) if chat_id else None))

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> str:
        runner = web.AppRunner(self.app())
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        self.server = runner
        self.url = f"http://{host}:{runner.addresses[0][1]}"
        return self.url

    async def stop(self) -> None:
        if self.server is not None:
            await self.server.cleanup()

    @staticmethod
    def ok(result: Any) -> web.Response:
        return web.json_response({"ok": True, "result": result})

    @staticmethod
    def fail(code: int, description: str, **parameters: Any) -> web.Response:
        body: dict[str, Any] = {"ok": False, "error_code": code, "description": description}
        if parameters:
            body["parameters"] = parameters
        return web.json_response(body, status=code)

    async def handle(self, request: web.Request) -> web.Response:
        if request.match_info["token"] != self.token:
            return self.fail(401, "Unauthorized")
        method = request.match_info["method"]
        params: dict[str, Any] = dict(await request.post()) if request.can_read_body else {}
        params = {key: value if isinstance(value, str) else str(value) for key, value in params.items()}
        self.calls.append((method, params))
        handler = getattr(self, f"m_{method}", None)
        if handler is None:
            return self.fail(404, "Not Found: method not found")
        response: web.Response = await handler(params)
        return response

    async def m_getMe(self, params: dict[str, Any]) -> web.Response:
        return self.ok({"id": int(self.token.split(":")[0]), "is_bot": True, "first_name": "news_hub",
                        "username": self.bot_username})

    async def m_sendMessage(self, params: dict[str, Any]) -> web.Response:
        chat_id, text = int(params["chat_id"]), params.get("text", "")
        error: web.Response | None = None
        if self.retry_after:
            self.retry_after -= 1
            error = self.fail(429, "Too Many Requests: retry after 1", retry_after=1)
        elif chat_id in self.blocked:
            error = self.fail(403, "Forbidden: bot was blocked by the user")
        elif len(text) > MAX_TEXT:
            error = self.fail(400, "Bad Request: message is too long")
        elif params.get("parse_mode") == "HTML" and (problem := html_error(text)):
            error = self.fail(400, problem)
        if error is not None:
            params["error"] = json.loads(error.text or "{}")["description"]
            return error
        return self.ok({"message_id": next(self._ids), "date": int(time.time()), "text": text,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": int(self.token.split(":")[0]), "is_bot": True, "first_name": "news_hub"}})

    async def m_setMyCommands(self, params: dict[str, Any]) -> web.Response:
        return self.ok(True)

    async def m_setWebhook(self, params: dict[str, Any]) -> web.Response:
        self.webhook_url, self.webhook_secret = params.get("url", ""), params.get("secret_token", "")
        return self.ok(True)

    async def m_deleteWebhook(self, params: dict[str, Any]) -> web.Response:
        self.webhook_url = self.webhook_secret = ""
        return self.ok(True)

    async def m_getWebhookInfo(self, params: dict[str, Any]) -> web.Response:
        return self.ok({"url": self.webhook_url, "has_custom_certificate": False, "pending_update_count": 0})

    async def m_getUpdates(self, params: dict[str, Any]) -> web.Response:
        if self.webhook_url:
            return self.fail(409, "Conflict: can't use getUpdates method while webhook is active")
        offset = int(params.get("offset", 0) or 0)
        self.updates = [update for update in self.updates if update["update_id"] >= offset]
        if not self.updates:
            await asyncio.sleep(min(float(params.get("timeout", 0) or 0), 0.5))
        return self.ok(self.updates[:100])


async def _serve(host: str, port: int, token: str) -> None:
    twin = TelegramTwin(token=token)
    url = await twin.start(host=host, port=port)
    print(f"Двійник Telegram Bot API: {url}  (TELEGRAM_API_URL={url}, BOT_TOKEN={token})", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 — щоб дістався бот у контейнері")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--token", default="123456:TEST-TOKEN")
    args = parser.parse_args()
    asyncio.run(_serve(args.host, args.port, args.token))
