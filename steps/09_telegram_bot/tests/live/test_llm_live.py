"""Урок 43: справжні виклики моделі — лише на вимогу й з ключем. Кожен запуск витрачає квоту/гроші.

    GEMINI_API_KEY=… pytest -m llm                       # Gemini
    LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=… ANTHROPIC_MODEL=… pytest -m llm

Без ключа тести пропускаються; звичайний `pytest` їх не запускає (addopts у pytest.ini: -m "not llm").
Модель відповідає щоразу трохи інакше, тому перевіряємо не текст, а контракт: відповідь проходить NewsAnalysis.

FakeLLM перевіряє НАШ код, але не те, чи приймає провайдер наш запит. test_gemini_accepts_request_shape
працює й без ключа (потрібна лише мережа): Google перевіряє структуру запиту раніше за ключ — якщо схема
чи параметри не ті, відповідь 400 про запит, а не «API key not valid».
"""
import os

import pytest

from news_hub.analysis import SYSTEM_PROMPT, NewsAnalysis, analyze_news, build_prompt
from news_hub.llm import GeminiClient, LLMUnavailable, make_llm
from news_hub.snapshot import load_snapshot

pytestmark = pytest.mark.llm

PROVIDER = os.getenv("LLM_PROVIDER", "gemini")


@pytest.fixture(scope="module")
def titles() -> list[str]:
    return [raw["title"] for raw in load_snapshot()[:3]]


@pytest.mark.asyncio
async def test_real_model_answers_valid_analysis(titles: list[str]) -> None:
    llm = make_llm(PROVIDER)
    if llm is None or llm.name == "fake":
        pytest.skip(f"немає ключа для {PROVIDER}")
    try:
        for title in titles:
            result = await analyze_news(title, llm)              # без кешу: щоразу справжній виклик
            print(f"{result.model} {result.input_tokens}+{result.output_tokens}: {title!r} → "
                  f"{result.analysis.model_dump_json()}")
            assert result.model != "fake" and not result.cached
            assert result.input_tokens > 0 and result.output_tokens > 0
    finally:
        await llm.aclose()


@pytest.mark.asyncio
async def test_gemini_accepts_request_shape() -> None:
    """Невалідний ключ → запит дійшов до перевірки ключа, тобто схема й параметри Google прийняв."""
    client = GeminiClient(api_key="invalid-key-for-contract-test", models=["gemini-2.5-flash"])
    with pytest.raises(LLMUnavailable) as error:
        try:
            await client.generate(build_prompt("Нацбанк знизив облікову ставку"), system=SYSTEM_PROMPT,
                                  schema=NewsAnalysis)
        finally:
            await client.aclose()                                # інакше aiohttp-сесія переживе цикл подій
    assert "API key not valid" in str(error.value)
