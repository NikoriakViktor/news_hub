"""Урок 43: клієнти LLM без мережі — справжні GeminiClient / AnthropicClient, але їхній HTTP-виклик підмінено.

Перевіряємо НАШ код навколо SDK: які моделі пробуємо і в якому порядку, що вважаємо збоєм,
що передаємо в запит (схема, системна інструкція). Сам SDK і модель тут не тестуємо.
"""
import asyncio
from types import SimpleNamespace
from typing import Any

import aiohttp
import anthropic
import fakeredis
import httpx
import httpx2
import pytest
from google.genai import errors as genai_errors
from redis.asyncio import Redis

from news_hub.analysis import NewsAnalysis
from news_hub.llm import (MODEL_POOL, AnthropicClient, CircuitBreaker, CircuitOpen, FakeLLM, GeminiClient,
                          GuardedLLM, LLMUnavailable, make_llm)

OK_JSON = '{"summary": "Уряд ухвалив бюджет", "category": "Економіка", "sentiment": "нейтральна", "keywords": []}'


def gemini_error(code: int) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"code": code, "message": "test", "status": "TEST"}})


def gemini_ok(text: str = OK_JSON) -> SimpleNamespace:
    usage = SimpleNamespace(prompt_token_count=120, candidates_token_count=40, thoughts_token_count=15)
    return SimpleNamespace(text=text, usage_metadata=usage)


class FakeGeminiModels:
    """Замість client.aio.models: відповіді по черзі (виняток або відповідь), запам'ятовує виклики."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def gemini_with(*outcomes: Any) -> tuple[GeminiClient, FakeGeminiModels]:
    client = GeminiClient(api_key="test-key")                  # без мережі: Client лише зберігає ключ
    fake = FakeGeminiModels(*outcomes)
    client._client = SimpleNamespace(aio=SimpleNamespace(models=fake))  # type: ignore[assignment]
    return client, fake


async def generate(llm: Any) -> Any:
    return await llm.generate("<news>Уряд ухвалив бюджет</news>", system="система", schema=NewsAnalysis)


# --- Gemini: пул моделей -------------------------------------------------------

@pytest.mark.asyncio
async def test_gemini_first_model_answers() -> None:
    client, fake = gemini_with(gemini_ok())
    reply = await generate(client)
    assert (reply.text, reply.model) == (OK_JSON, MODEL_POOL[0])
    assert (reply.input_tokens, reply.output_tokens) == (120, 55)      # «думки» — теж вихідні токени
    config = fake.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == NewsAnalysis.model_json_schema()
    assert config.response_schema is None                             # старе поле не приймає additionalProperties
    assert config.system_instruction == "система"
    assert fake.calls[0]["contents"] == "<news>Уряд ухвалив бюджет</news>"


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [404, 429, 500, 503])
async def test_gemini_falls_back_to_next_model(code: int) -> None:
    client, fake = gemini_with(gemini_error(code), gemini_ok())
    reply = await generate(client)
    assert reply.model == MODEL_POOL[1]
    assert [call["model"] for call in fake.calls] == MODEL_POOL[:2]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    TimeoutError(),                                   # тайм-аут через aiohttp (Python 3.11+)
    asyncio.TimeoutError(),                           # те саме в Python 3.10
    aiohttp.ServerDisconnectedError(),                # обрив з'єднання
    httpx.ReadTimeout("timeout"),                     # якщо SDK працює через httpx (aiohttp не встановлено)
], ids=["TimeoutError", "asyncio.TimeoutError", "aiohttp", "httpx"])
async def test_gemini_network_error_falls_back(error: Exception) -> None:
    client, fake = gemini_with(error, gemini_ok())
    assert (await generate(client)).model == MODEL_POOL[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [400, 401, 403])
async def test_gemini_client_error_stops_at_once(code: int) -> None:
    """Невалідний запит чи ключ — інша модель не допоможе: жодних спроб по пулу."""
    client, fake = gemini_with(gemini_error(code), gemini_ok())
    with pytest.raises(LLMUnavailable, match=str(code)):
        await generate(client)
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_gemini_all_models_fail() -> None:
    client, fake = gemini_with(*[gemini_error(429)] * len(MODEL_POOL))
    with pytest.raises(LLMUnavailable, match="усі моделі") as error:
        await generate(client)
    assert all(f"{model}: 429" in str(error.value) for model in MODEL_POOL)
    assert len(fake.calls) == len(MODEL_POOL)


@pytest.mark.asyncio
async def test_gemini_empty_text_is_empty_string() -> None:
    """Заблокована чи обрізана відповідь: text=None → "" (перевірка NewsAnalysis її відхилить)."""
    client, _ = gemini_with(SimpleNamespace(text=None, usage_metadata=None))
    reply = await generate(client)
    assert (reply.text, reply.input_tokens) == ("", 0)


# --- Anthropic ----------------------------------------------------------------

class FakeMessages:
    def __init__(self, outcome: Any) -> None:
        self.outcome, self.kwargs = outcome, {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def anthropic_with(outcome: Any) -> tuple[AnthropicClient, FakeMessages]:
    client = AnthropicClient(api_key="test-key", model="test-model")
    fake = FakeMessages(outcome)
    client._client = SimpleNamespace(messages=fake)  # type: ignore[assignment]
    return client, fake


@pytest.mark.asyncio
async def test_anthropic_json_schema_request() -> None:
    message = SimpleNamespace(content=[SimpleNamespace(type="text", text=OK_JSON)], model="test-model",
                              usage=SimpleNamespace(input_tokens=90, output_tokens=30))
    client, fake = anthropic_with(message)
    reply = await generate(client)
    assert (reply.text, reply.model, reply.input_tokens, reply.output_tokens) == (OK_JSON, "test-model", 90, 30)
    assert fake.kwargs["model"] == "test-model" and fake.kwargs["system"] == "система"
    output_format = fake.kwargs["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["schema"]["additionalProperties"] is False
    assert output_format["schema"]["properties"]["sentiment"]["enum"] == ["позитивна", "нейтральна", "негативна"]


@pytest.mark.asyncio
async def test_anthropic_error_is_llm_unavailable() -> None:
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    client, _ = anthropic_with(error)
    with pytest.raises(LLMUnavailable, match="APIConnectionError"):
        await generate(client)


# --- FakeLLM і make_llm ---------------------------------------------------------

@pytest.mark.asyncio
async def test_fake_llm_script_then_demo() -> None:
    fake = FakeLLM(["перша", LLMUnavailable("збій")])
    assert (await generate(fake)).text == "перша"
    with pytest.raises(LLMUnavailable):
        await generate(fake)
    NewsAnalysis.model_validate_json((await generate(fake)).text)       # черга порожня → demo_reply
    assert len(fake.calls) == 3


def test_make_llm_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODELS", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert make_llm() is None                                           # ключа немає → None, а не виняток
    assert isinstance(make_llm("fake"), FakeLLM)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODELS", "model-a, model-b")
    gemini = make_llm()
    assert isinstance(gemini, GeminiClient) and gemini.models == ["model-a", "model-b"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert make_llm("anthropic") is None                                # без ANTHROPIC_MODEL
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")
    assert isinstance(make_llm("anthropic"), AnthropicClient)
    with pytest.raises(ValueError, match="openai"):
        make_llm("openai")


# --- Circuit breaker ----------------------------------------------------------

@pytest.fixture
def redis() -> Redis:
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold(redis: Redis) -> None:
    breaker = CircuitBreaker(redis, threshold=3, cooldown=60)
    for _ in range(2):
        await breaker.record_failure()
    assert await breaker.retry_after() == 0                             # ще закрито
    await breaker.record_failure()
    assert 0 < await breaker.retry_after() <= 60
    assert await redis.get(breaker.failures_key) is None                # лічильник — з нуля після паузи


@pytest.mark.asyncio
async def test_breaker_closes_by_itself(redis: Redis) -> None:
    breaker = CircuitBreaker(redis, threshold=1, cooldown=1)
    await breaker.record_failure()
    assert await breaker.retry_after() == 1
    await asyncio.sleep(1.1)                                            # TTL минув — ключ зник
    assert await breaker.retry_after() == 0


@pytest.mark.asyncio
async def test_breaker_success_resets_counter(redis: Redis) -> None:
    breaker = CircuitBreaker(redis, threshold=3)
    await breaker.record_failure()
    await breaker.record_failure()
    await breaker.record_success()
    await breaker.record_failure()
    assert await breaker.retry_after() == 0                             # 1 збій, а не 3


@pytest.mark.asyncio
async def test_breaker_counts_concurrent_failures(redis: Redis) -> None:
    """20 одночасних збоїв — лічильник 20: INCR атомарний, жоден збій не губиться."""
    breaker = CircuitBreaker(redis, threshold=100)
    await asyncio.gather(*(breaker.record_failure() for _ in range(20)))
    assert await redis.get(breaker.failures_key) == "20"
    assert 0 < await redis.ttl(breaker.failures_key) <= breaker.window


@pytest.mark.asyncio
async def test_breaker_without_redis_lets_calls_through() -> None:
    """Redis недоступний — breaker не вимикає LLM (кеш і breaker — допомога, а не умова роботи)."""
    down = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    breaker = CircuitBreaker(down, threshold=1)
    await breaker.record_failure()
    assert await breaker.retry_after() == 0
    await down.aclose()


@pytest.mark.asyncio
async def test_guarded_llm_blocks_when_open(redis: Redis) -> None:
    fake = FakeLLM([LLMUnavailable("503")] * 2)
    guarded = GuardedLLM(fake, CircuitBreaker(redis, threshold=2, cooldown=60))
    for _ in range(2):
        with pytest.raises(LLMUnavailable):
            await generate(guarded)
    with pytest.raises(CircuitOpen) as error:
        await generate(guarded)
    assert 0 < error.value.retry_after <= 60
    assert len(fake.calls) == 2                                         # третій запит до провайдера не дійшов


@pytest.mark.asyncio
async def test_clients_close_http_sessions() -> None:
    """aclose() закриває HTTP-сесію SDK; lifespan викликає його при зупинці застосунку."""
    gemini = GeminiClient(api_key="test-key")
    await gemini.aclose()
    claude = AnthropicClient(api_key="test-key", model="test-model")
    await claude.aclose()
    assert claude._client.is_closed()
    await GuardedLLM(FakeLLM(), CircuitBreaker(fakeredis.FakeAsyncRedis())).aclose()
