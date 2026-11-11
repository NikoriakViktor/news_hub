"""Клієнти LLM за одним інтерфейсом: Gemini (основний), Anthropic (другий), FakeLLM (тести й ноутбук).

Основа — `app/services/ai_service.py` зі стартового `ai_bot`:
пул моделей Gemini з переходом на наступну при збої й circuit breaker у Redis.
Рефакторинг уроку 43:
- один інтерфейс `LLMClient` — решта коду (analysis.py, api.py) не знає, який провайдер відповідає;
- `client.aio.models.generate_content` — асинхронний клієнт google-genai: запит не блокує цикл подій,
  тож `asyncio.to_thread` і новий `genai.Client` на кожен виклик не потрібні;
- помилку провайдера видно за кодом (`APIError.code`), а не за словами в тексті винятку;
  400/401/403 — наша помилка (запит, ключ): інша модель тут не допоможе, пул не перебираємо;
- збій — це виняток (`LLMUnavailable`), а не рядок «AI недоступний», який легко сплутати з відповіддю;
- breaker окремо від провайдера (`GuardedLLM` обгортає будь-який `LLMClient`), лічильник — атомарний.

Налаштування — змінні середовища (ключі — лише там, ніколи в коді):
    LLM_PROVIDER=gemini|anthropic|fake   GEMINI_API_KEY   GEMINI_MODELS=модель1,модель2
    ANTHROPIC_API_KEY   ANTHROPIC_MODEL   LLM_TIMEOUT=30   LLM_MAX_TOKENS=2048
"""
import asyncio
import json
import logging
import os
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

import aiohttp
import anthropic
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger("news_hub")

# Від кращої моделі до легшої: у кожної своя квота, тож коли перша вичерпала ліміт (429),
# наступна ще може відповісти. Список моделей змінюється — перевизначення: GEMINI_MODELS.
MODEL_POOL: list[str] = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))            # секунд на один запит до моделі
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))      # стеля відповіді: платимо за фактичні токени

# Коди, після яких варто спробувати іншу модель: 404 — модель прибрали, 429 — квота, 5xx — перевантаження
RETRY_NEXT_MODEL = {404, 408, 429, 500, 502, 503, 504}
# Мережеві збої: SDK ходить через aiohttp, якщо він встановлений (у нас — так), інакше через httpx.
# Тайм-аут aiohttp — TimeoutError (у 3.10 — asyncio.TimeoutError, окремий клас).
NETWORK_ERRORS = (TimeoutError, asyncio.TimeoutError, aiohttp.ClientError, httpx.TransportError)


class LLMError(Exception):
    """Базова помилка шару LLM."""


class LLMUnavailable(LLMError):
    """Провайдер не відповів (усі моделі пулу або помилка запиту) → API повертає 502."""


class CircuitOpen(LLMError):
    """Breaker відкритий: провайдера не викликаємо, поки не мине retry_after секунд → 503."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"LLM тимчасово вимкнено після серії збоїв; спробуй через {retry_after} с")
        self.retry_after = retry_after


@dataclass(frozen=True)
class LLMReply:
    """Відповідь моделі + те, що потрібно для журналу й рахунку: яка модель, скільки токенів."""
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(Protocol):
    """Будь-який провайдер: промпт + системна інструкція + схема відповіді → JSON-текст."""

    name: str

    async def generate(self, prompt: str, *, system: str, schema: type[BaseModel]) -> LLMReply: ...

    async def aclose(self) -> None:
        """Закрити HTTP-з'єднання клієнта (lifespan при зупинці застосунку)."""


# ---------------------------------------------------------------------------
# Gemini — основний провайдер курсу (безкоштовний ключ: aistudio.google.com)
# ---------------------------------------------------------------------------

class GeminiClient:
    name = "gemini"

    def __init__(self, api_key: str, models: Iterable[str] = MODEL_POOL, timeout: float = LLM_TIMEOUT,
                 max_tokens: int = LLM_MAX_TOKENS) -> None:
        self.models = list(models)
        self.max_tokens = max_tokens
        # Один клієнт на весь застосунок: він тримає пул HTTP-з'єднань
        self._client = genai.Client(api_key=api_key,
                                    http_options=genai_types.HttpOptions(timeout=int(timeout * 1000)))

    async def generate(self, prompt: str, *, system: str, schema: type[BaseModel]) -> LLMReply:
        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",   # лише JSON…
            # …і саме такої структури. response_json_schema — повна JSON Schema; старіше поле response_schema
            # приймає лише підмножину OpenAPI і відхиляє схему з additionalProperties (extra="forbid") — 400
            response_json_schema=schema.model_json_schema(),
            temperature=0.2,                         # класифікація, а не творчість: менше випадковості
            max_output_tokens=self.max_tokens,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),  # інструментів немає
        )
        failures: list[str] = []
        for model in self.models:
            start = time.perf_counter()
            try:
                response = await self._client.aio.models.generate_content(model=model, contents=prompt,
                                                                          config=config)
            except genai_errors.APIError as error:
                failures.append(f"{model}: {error.code}")
                logger.warning("gemini %s → %s за %.1f с", model, error.code, time.perf_counter() - start)
                if error.code not in RETRY_NEXT_MODEL:
                    raise LLMUnavailable(f"gemini відхилив запит ({error.code}): {error.message}") from error
                continue
            except NETWORK_ERRORS as error:                 # тайм-аут, обрив з'єднання
                failures.append(f"{model}: {type(error).__name__}")
                logger.warning("gemini %s → %s", model, type(error).__name__)
                continue
            usage = response.usage_metadata
            reply = LLMReply(
                text=response.text or "", model=model,
                input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                # «думки» моделі (thinking) оплачуються як вихідні токени
                output_tokens=((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
                if usage else 0,
            )
            logger.info("gemini %s: %s+%s токенів за %.1f с", model, reply.input_tokens, reply.output_tokens,
                        time.perf_counter() - start)
            return reply
        raise LLMUnavailable("усі моделі Gemini недоступні: " + ", ".join(failures))

    async def aclose(self) -> None:
        await self._client.aio.aclose()


# ---------------------------------------------------------------------------
# Anthropic — та сама роль, інший провайдер. Модель — лише зі змінної ANTHROPIC_MODEL.
# ---------------------------------------------------------------------------

class AnthropicClient:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float = LLM_TIMEOUT,
                 max_tokens: int = LLM_MAX_TOKENS) -> None:
        self.model = model
        self.max_tokens = max_tokens
        # SDK сам повторює запит при 429/5xx (max_retries), тож пулу моделей тут немає
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)

    async def generate(self, prompt: str, *, system: str, schema: type[BaseModel]) -> LLMReply:
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                # structured outputs: відповідь — JSON за схемою (transform_schema пристосовує схему Pydantic)
                output_config={"format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)}},
            )
        except anthropic.APIError as error:
            raise LLMUnavailable(f"anthropic: {type(error).__name__}: {error}") from error
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMReply(text=text, model=response.model, input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens)

    async def aclose(self) -> None:
        await self._client.close()


# ---------------------------------------------------------------------------
# FakeLLM — без мережі й ключа: тести, ноутбук, LLM_PROVIDER=fake
# ---------------------------------------------------------------------------

def demo_reply(prompt: str) -> str:
    """Правдоподібна відповідь без моделі: нейтральна, категорія «Інше», ключові слова — довгі слова заголовка."""
    title = prompt.split("<news>")[-1].split("</news>")[0].strip() if "<news>" in prompt else prompt
    words = [word.strip(".,:;!?«»\"'()") for word in title.split()]
    keywords = list(dict.fromkeys(word.lower() for word in words if len(word) > 4))[:5]
    return json.dumps({"summary": title[:300], "category": "Інше", "sentiment": "нейтральна",
                       "keywords": keywords}, ensure_ascii=False)


class FakeLLM:
    """Відповідає за сценарієм: FakeLLM(['{…}', LLMUnavailable('…')]) — по черзі; черга порожня → demo_reply.

    `calls` — усі промпти, які отримав клієнт: тест перевіряє, що саме пішло б у модель і скільки разів.
    """

    name = "fake"

    def __init__(self, replies: Iterable[str | Exception] = (),
                 fallback: Callable[[str], str] = demo_reply) -> None:
        self.replies: deque[str | Exception] = deque(replies)
        self.fallback = fallback
        self.calls: list[str] = []
        self.systems: list[str] = []

    async def generate(self, prompt: str, *, system: str, schema: type[BaseModel]) -> LLMReply:
        self.calls.append(prompt)
        self.systems.append(system)
        reply = self.replies.popleft() if self.replies else self.fallback(prompt)
        if isinstance(reply, Exception):
            raise reply
        return LLMReply(text=reply, model="fake", input_tokens=len(prompt) // 4, output_tokens=len(reply) // 4)

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Circuit breaker у Redis: спільний для всіх процесів застосунку й переживає перезапуск
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """N збоїв поспіль (за `window` секунд) → «відкрито» на `cooldown` секунд: провайдера не викликаємо.

    Закрито ─N збоїв→ Відкрито ─минув TTL→ Закрито (ключ зник сам). Успіх обнуляє лічильник.
    Лічильник — INCR (атомарно): при одночасних збоях жоден не губиться.
    """

    def __init__(self, redis: Redis, name: str = "llm", threshold: int = 5, window: int = 300,
                 cooldown: int = 300) -> None:
        self._redis = redis
        self.threshold, self.window, self.cooldown = threshold, window, cooldown
        self.failures_key, self.open_key = f"cb:{name}:failures", f"cb:{name}:open"

    async def retry_after(self) -> int:
        """0 — закрито (можна викликати); >0 — відкрито, стільки секунд лишилось."""
        try:
            ttl: int = await self._redis.ttl(self.open_key)
        except RedisError:
            logger.warning("breaker: Redis недоступний — вважаємо закритим")
            return 0                              # Redis упав — не вимикаємо через це LLM
        return max(ttl, 0)

    async def record_failure(self) -> None:
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(self.failures_key)
                pipe.expire(self.failures_key, self.window, nx=True)     # вікно — від першого збою
                failures, _ = await pipe.execute()
            if failures >= self.threshold:
                await self._redis.set(self.open_key, 1, ex=self.cooldown)
                await self._redis.delete(self.failures_key)             # після паузи — рахуємо заново
                logger.error("breaker: відкрито після %s збоїв на %s с", failures, self.cooldown)
        except RedisError:
            logger.warning("breaker: Redis недоступний — збій не записано")

    async def record_success(self) -> None:
        try:
            await self._redis.delete(self.failures_key)
        except RedisError:
            pass


class GuardedLLM:
    """Будь-який LLMClient + breaker: той самий інтерфейс, тож код, що викликає, не змінюється."""

    def __init__(self, inner: LLMClient, breaker: CircuitBreaker) -> None:
        self.inner, self.breaker = inner, breaker
        self.name = inner.name

    async def generate(self, prompt: str, *, system: str, schema: type[BaseModel]) -> LLMReply:
        if wait := await self.breaker.retry_after():
            raise CircuitOpen(wait)
        try:
            reply = await self.inner.generate(prompt, system=system, schema=schema)
        except LLMUnavailable:
            await self.breaker.record_failure()
            raise
        await self.breaker.record_success()
        return reply

    async def aclose(self) -> None:
        await self.inner.aclose()


def make_llm(provider: str | None = None) -> LLMClient | None:
    """Клієнт за змінними середовища; None — ключа немає (API відповідатиме 503 «LLM не налаштовано»)."""
    provider = provider or os.getenv("LLM_PROVIDER", "gemini")
    if provider == "fake":
        return FakeLLM()
    if provider == "gemini":
        if not (key := os.getenv("GEMINI_API_KEY")):
            return None
        models = [m.strip() for m in os.getenv("GEMINI_MODELS", "").split(",") if m.strip()] or MODEL_POOL
        return GeminiClient(key, models)
    if provider == "anthropic":
        key, model = os.getenv("ANTHROPIC_API_KEY"), os.getenv("ANTHROPIC_MODEL")
        return AnthropicClient(key, model) if key and model else None
    raise ValueError(f"невідомий LLM_PROVIDER: {provider!r} (gemini, anthropic або fake)")
