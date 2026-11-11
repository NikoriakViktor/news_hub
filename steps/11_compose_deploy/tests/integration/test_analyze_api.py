"""Урок 43: аналіз LLM через API — база, кеш, breaker, rate limit і фонова задача. LLM — FakeLLM."""
import json
from typing import Any

from fastapi.testclient import TestClient

from news_hub.api import app
from news_hub.llm import FakeLLM, LLMUnavailable
from news_hub.middleware import ANALYZE_RATE_LIMIT

NEWS = {"title": "Нацбанк знизив облікову ставку до 13%", "url": "https://www.rbc.ua/ukr/news/nbu-rate-1.html"}


def answer(**overrides: Any) -> str:
    data = {"summary": "НБУ знизив облікову ставку.", "category": "Економіка", "sentiment": "позитивна",
            "keywords": ["НБУ", "облікова ставка"]} | overrides
    return json.dumps(data, ensure_ascii=False)


def create(client: TestClient, **overrides: str) -> int:
    news_id: int = client.post("/api/news", json=NEWS | overrides).json()["id"]
    return news_id


def test_analyze_saves_result(client: TestClient, fake_llm: FakeLLM) -> None:
    news_id = create(client)
    fake_llm.replies.append(answer())
    response = client.post(f"/api/news/{news_id}/analyze")
    assert response.status_code == 200
    body = response.json()
    assert (body["source"], body["model"], body["analysis"]["sentiment"]) == ("llm", "fake", "позитивна")
    assert body["input_tokens"] > 0
    stored = client.get(f"/api/news/{news_id}").json()
    assert (stored["ai_category"], stored["keywords"]) == ("Економіка", ["НБУ", "облікова ставка"])
    assert stored["category"] == "Новини"                         # розділ сайту лишився як був
    assert stored["analyzed_at"] is not None


def test_second_analyze_comes_from_db(client: TestClient, fake_llm: FakeLLM) -> None:
    news_id = create(client)
    fake_llm.replies.append(answer())
    client.post(f"/api/news/{news_id}/analyze")
    again = client.post(f"/api/news/{news_id}/analyze").json()
    assert (again["source"], again["model"]) == ("db", None)
    assert again["analysis"]["category"] == "Економіка"
    assert len(fake_llm.calls) == 1                               # модель удруге не викликали


def test_force_reanalyzes(client: TestClient, fake_llm: FakeLLM) -> None:
    news_id = create(client)
    fake_llm.replies.extend([answer(), answer(sentiment="нейтральна")])
    client.post(f"/api/news/{news_id}/analyze")
    forced = client.post(f"/api/news/{news_id}/analyze", params={"force": True}).json()
    assert (forced["source"], forced["analysis"]["sentiment"]) == ("llm", "нейтральна")
    assert len(fake_llm.calls) == 2


def test_same_title_after_rescrape_comes_from_cache(client: TestClient, fake_llm: FakeLLM) -> None:
    """DELETE /api/news і новий збір: рядки нові (нові id), а заголовки ті самі — платити вдруге не треба."""
    fake_llm.replies.append(answer())
    client.post(f"/api/news/{create(client)}/analyze")
    client.delete("/api/news")
    again = client.post(f"/api/news/{create(client)}/analyze").json()
    assert (again["source"], again["model"]) == ("cache", None)
    assert len(fake_llm.calls) == 1


def test_analyze_unknown_news_404(client: TestClient, fake_llm: FakeLLM) -> None:
    assert client.post("/api/news/999/analyze").status_code == 404
    assert fake_llm.calls == []


def test_provider_down_502(client: TestClient, fake_llm: FakeLLM) -> None:
    news_id = create(client)
    fake_llm.replies.append(LLMUnavailable("усі моделі Gemini недоступні: gemini-2.5-flash: 503"))
    response = client.post(f"/api/news/{news_id}/analyze")
    assert response.status_code == 502
    assert "503" in response.json()["detail"]
    assert client.get(f"/api/news/{news_id}").json()["analyzed_at"] is None     # нічого не записано


def test_invalid_output_twice_502(client: TestClient, fake_llm: FakeLLM) -> None:
    news_id = create(client)
    fake_llm.replies.extend(["не json", answer(category="Новини")])
    response = client.post(f"/api/news/{news_id}/analyze")
    assert response.status_code == 502
    assert "невалідна відповідь" in response.json()["detail"]


def test_breaker_opens_503_with_retry_after(client: TestClient, fake_llm: FakeLLM) -> None:
    news_id = create(client)
    fake_llm.replies.extend([LLMUnavailable("503")] * 5)
    statuses = [client.post(f"/api/news/{news_id}/analyze").status_code for _ in range(6)]
    assert statuses == [502] * 5 + [503]
    blocked = client.post(f"/api/news/{news_id}/analyze")
    assert 0 < int(blocked.headers["Retry-After"]) <= 300
    assert len(fake_llm.calls) == 5                               # після відкриття провайдера не чіпаємо


def test_llm_not_configured_503(client: TestClient) -> None:
    news_id = create(client)
    app.state.llm = None                                          # як без GEMINI_API_KEY
    response = client.post(f"/api/news/{news_id}/analyze")
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_analyze_invalidates_list_cache(client: TestClient, fake_llm: FakeLLM) -> None:
    news_id = create(client)
    client.get("/api/news")
    assert client.get("/api/news").headers["X-Cache"] == "HIT"
    client.post(f"/api/news/{news_id}/analyze")
    fresh = client.get("/api/news")
    assert fresh.headers["X-Cache"] == "MISS" and fresh.json()[0]["analyzed_at"] is not None


def test_filters_and_stats(client: TestClient, fake_llm: FakeLLM) -> None:
    first = create(client)
    second = create(client, title="Збірна України виграла у Франції", url="https://www.rbc.ua/ukr/news/sport-2.html")
    create(client, title="Новина, яку ще не аналізували", url="https://www.rbc.ua/ukr/news/other-3.html")
    fake_llm.replies.extend([answer(), answer(category="Спорт", summary="Збірна виграла матч.")])
    client.post(f"/api/news/{first}/analyze")
    client.post(f"/api/news/{second}/analyze")
    sport = client.get("/api/news", params={"ai_category": "Спорт"}).json()
    assert [item["id"] for item in sport] == [second]
    assert len(client.get("/api/news", params={"sentiment": "позитивна"}).json()) == 2
    assert client.get("/api/news", params={"sentiment": "дуже погана"}).status_code == 422
    stats = client.get("/api/news/stats").json()
    assert stats["ai_category"] == {"Економіка": 1, "Спорт": 1}   # неаналізована (NULL) — не рахується
    assert (stats["sentiment"], stats["total"]) == ({"позитивна": 2}, 3)


def test_analyze_rate_limit(client: TestClient, fake_llm: FakeLLM) -> None:
    news_id = create(client)
    statuses = [client.post(f"/api/news/{news_id}/analyze").status_code for _ in range(ANALYZE_RATE_LIMIT + 1)]
    assert statuses == [200] * ANALYZE_RATE_LIMIT + [429]
    assert client.post("/api/scrape", json={"source": "snapshot"}).status_code == 200   # свій лічильник


# --- пакетний аналіз у фоні --------------------------------------------------------

def test_analyze_job(client: TestClient, fake_llm: FakeLLM) -> None:
    client.post("/api/scrape", json={"source": "snapshot"})
    started = client.post("/api/analyze/jobs", json={"limit": 3})
    assert started.status_code == 202
    job = started.json()
    assert (job["kind"], job["status"], job["mode"]) == ("analyze", "queued", "fake")
    done = client.get(f"/api/analyze/jobs/{job['job_id']}").json()   # TestClient виконує фонову задачу до повернення
    assert (done["status"], done["news_found"], done["news_analyzed"], done["news_failed"]) == ("done", 3, 3, 0)
    assert sum(client.get("/api/news/stats").json()["sentiment"].values()) == 3
    second = client.post("/api/analyze/jobs", json={"limit": 3}).json()
    assert client.get(f"/api/analyze/jobs/{second['job_id']}").json()["news_analyzed"] == 3
    assert sum(client.get("/api/news/stats").json()["sentiment"].values()) == 6   # наступні 3, не ті самі


def test_analyze_job_skips_failed_news(client: TestClient, fake_llm: FakeLLM) -> None:
    client.post("/api/scrape", json={"source": "snapshot"})
    fake_llm.replies.extend([answer(), LLMUnavailable("503"), answer()])
    job = client.post("/api/analyze/jobs", json={"limit": 3}).json()
    done = client.get(f"/api/analyze/jobs/{job['job_id']}").json()
    assert (done["status"], done["news_analyzed"], done["news_failed"]) == ("done", 2, 1)


def test_analyze_job_stops_when_breaker_opens(client: TestClient, fake_llm: FakeLLM) -> None:
    client.post("/api/scrape", json={"source": "snapshot"})
    fake_llm.replies.extend([LLMUnavailable("503")] * 5)
    job = client.post("/api/analyze/jobs", json={"limit": 20}).json()
    done = client.get(f"/api/analyze/jobs/{job['job_id']}").json()
    assert (done["status"], done["news_failed"]) == ("failed", 5)
    assert done["error"].startswith("CircuitOpen")
    assert len(fake_llm.calls) == 5                               # 15 новин, що лишились, модель не бачила


def test_scrape_job_is_not_an_analyze_job(client: TestClient) -> None:
    job = client.post("/api/scrape/jobs", json={"source": "snapshot"}).json()
    assert client.get(f"/api/analyze/jobs/{job['job_id']}").status_code == 404
    assert client.post("/api/analyze/jobs", json={"limit": 0}).status_code == 422
