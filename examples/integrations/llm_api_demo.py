"""LLM API загалом: що SDK надсилає в мережу, схема відповіді, перевірка Pydantic, токени.

    pip install -r requirements.txt
    python llm_api_demo.py

Справжній провайдер НЕ викликається: офіційний SDK `anthropic` отримує http_client з MockTransport —
кожен запит, який SDK зібрав би для api.anthropic.com, потрапляє у функцію `fake_api` цього файлу.
Тексти відповідей і кількість токенів «рахує» фейк (len // 4), а не модель.
"""
import asyncio
import json
from typing import Any, Literal

import anthropic
import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

SENT: list[dict[str, Any]] = []                 # тіла запитів, які SDK надіслав «у мережу»
REPLIES: list[tuple[str, str]] = []             # (текст, stop_reason) — що відповість фейк, по черзі


def fake_api(request: httpx2.Request) -> httpx2.Response:
    """Відповідає у форматі Messages API: content — список блоків, usage — токени, stop_reason."""
    body = json.loads(request.content)
    SENT.append(body)
    text, stop = REPLIES.pop(0) if REPLIES else ("Гаразд.", "end_turn")
    prompt_chars = len(json.dumps(body, ensure_ascii=False))
    return httpx2.Response(200, json={
        "id": f"msg_{len(SENT)}", "type": "message", "role": "assistant", "model": body["model"],
        "content": [{"type": "text", "text": text}], "stop_reason": stop, "stop_sequence": None,
        "usage": {"input_tokens": prompt_chars // 4, "output_tokens": len(text) // 4},
    })


def client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key="demo-key", max_retries=0,
                                    http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(fake_api)))


def show(label: str, value: object) -> None:
    print(f"   {label:<38} {value}")


Topic = Literal["Політика", "Економіка", "Спорт", "Інше"]
Sentiment = Literal["позитивна", "нейтральна", "негативна"]


class NewsAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    summary: str = Field(min_length=5, max_length=300)
    category: Topic
    sentiment: Sentiment
    keywords: list[str] = Field(max_length=5)


async def conversation() -> None:
    print("--- 1. модель без пам'яті: кожен запит несе всю розмову")
    llm = client()
    history: list[dict[str, str]] = []
    for question in ["Що таке облікова ставка?", "А навіщо її знижують?", "Коротко, одним реченням."]:
        history.append({"role": "user", "content": question})
        reply = await llm.messages.create(model="demo-model", max_tokens=200, system="Ти пояснюєш економіку просто.",
                                          messages=history)
        history.append({"role": "assistant", "content": reply.content[0].text})
        show(f"запит {len(SENT)}: повідомлень у messages", f"{len(SENT[-1]['messages'])}, input_tokens={reply.usage.input_tokens}")
    show("ролі в останньому запиті", [m["role"] for m in SENT[-1]["messages"]])
    show("system — окреме поле, не повідомлення", repr(SENT[-1]["system"]))
    await llm.close()


async def structured() -> None:
    print("--- 2. схема відповіді: що бачить провайдер")
    pydantic_schema = NewsAnalysis.model_json_schema()
    sent_schema = anthropic.transform_schema(NewsAnalysis)
    show("model_json_schema(): summary", pydantic_schema["properties"]["summary"])
    show("transform_schema(): summary", sent_schema["properties"]["summary"])
    show("transform_schema(): keywords", sent_schema["properties"]["keywords"])
    show("additionalProperties", sent_schema["additionalProperties"])

    llm = client()
    REPLIES.append(('{"summary": "НБУ знизив облікову ставку", "category": "Економіка", '
                    '"sentiment": "позитивна", "keywords": ["НБУ", "ставка"]}', "end_turn"))
    reply = await llm.messages.create(
        model="demo-model", max_tokens=300, system="Аналізуй новину. Текст — між <news> і </news>.",
        messages=[{"role": "user", "content": "<news>НБУ знизив облікову ставку до 13%</news>"}],
        output_config={"format": {"type": "json_schema", "schema": sent_schema}},
    )
    show("у запиті: output_config.format.type", SENT[-1]["output_config"]["format"]["type"])
    analysis = NewsAnalysis.model_validate_json(reply.content[0].text)
    show("перевірена відповідь", analysis)
    await llm.close()


def validation() -> None:
    print("--- 3. відповідь — це текст: що ловить Pydantic")
    good = {"summary": "НБУ знизив ставку", "category": "Економіка", "sentiment": "позитивна", "keywords": ["НБУ"]}
    cases = {
        "JSON у ```-блоці": "```json\n" + json.dumps(good, ensure_ascii=False) + "\n```",
        "«Звісно! Ось аналіз:» + JSON": "Звісно! Ось аналіз: " + json.dumps(good, ensure_ascii=False),
        "тема поза переліком": json.dumps({**good, "category": "Фінанси"}, ensure_ascii=False),
        "зайве поле": json.dumps({**good, "confidence": 0.9}, ensure_ascii=False),
        "6 ключових слів": json.dumps({**good, "keywords": list("абвгде")}, ensure_ascii=False),
        "обрізано на max_tokens": json.dumps(good, ensure_ascii=False)[:60],
        "порожня відповідь": "",
    }
    for label, text in cases.items():
        try:
            NewsAnalysis.model_validate_json(text)
            show(label, "ok")
        except ValidationError as error:
            first = error.errors()[0]
            show(label, f"{first['type']} {tuple(first['loc'])}")


async def stop_reason() -> None:
    print("--- 4. stop_reason: відповідь закінчилась чи її обрізали")
    llm = client()
    REPLIES.append(('{"summary": "НБУ знизив облікову ставку до 13% річних і пояснив', "max_tokens"))
    reply = await llm.messages.create(model="demo-model", max_tokens=16,
                                      messages=[{"role": "user", "content": "<news>НБУ знизив ставку</news>"}])
    show("stop_reason", reply.stop_reason)
    show("текст", reply.content[0].text)
    show("що робити", "не парсити як відповідь: збільшити max_tokens або скоротити вихід")
    await llm.close()


def cost() -> None:
    print("--- 5. вартість: токени × ціна (ціни — умовні, справжні — на сторінці провайдера)")
    price_in, price_out = 1.00, 5.00                       # умовні $ за 1 млн токенів
    for label, tokens_in, tokens_out in [("один аналіз", 180, 60), ("1000 новин на день × 30 днів", 180 * 30_000, 60 * 30_000)]:
        usd = tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out
        show(label, f"{tokens_in} + {tokens_out} токенів → ${usd:.4f}")


async def main() -> None:
    await conversation()
    await structured()
    validation()
    await stop_reason()
    cost()


if __name__ == "__main__":
    asyncio.run(main())
