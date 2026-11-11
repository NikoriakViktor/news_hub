"""Фоновий збір: POST відповідає одразу `202 Accepted`, збір іде після відповіді.

Основа — `POST /api/scrape/archive` + `GET /api/scrape/archive/{job_id}` з `app/main.py`
прототипу `news_dashboard`: `BackgroundTasks`, uuid задачі, статус у колекції MongoDB `scrape_jobs`.
Рефакторинг уроку 39:
- статус задачі — hash у Redis `job:<id>` з TTL (добу), а не документ у базі новин;
- фонова задача відкриває **власну** сесію бази: сесія запиту (get_db) закривається разом із запитом,
  а старий код передавав у задачу `db` запиту;
- помилка всередині задачі не губиться: статус `failed` і текст помилки.
Урок 43: друга фонова задача — аналіз LLM новин, яких ще не аналізували (`run_analyze_job`).
Урок 47: після збору — сповіщення підписників Telegram про нові новини (`notify`, якщо бот увімкнено).
"""
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .analysis import AnalysisCache, analyze_news
from .cache import NewsCache
from .llm import CircuitOpen, LLMClient, LLMError
from .models import validate_news
from .repository import NewNews, NewsRepository
from .scraper import ScrapeOutcome

logger = logging.getLogger("news_hub")

JOB_TTL = 24 * 3600


class JobStatus(BaseModel):
    job_id: str
    kind: Literal["scrape", "analyze"] = "scrape"
    status: Literal["queued", "running", "done", "failed"]
    source: str
    mode: str
    news_found: int = 0
    news_saved: int = 0
    news_analyzed: int = 0
    news_failed: int = 0
    error: str | None = None
    created_at: str
    finished_at: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def create(self, source: str, mode: str, kind: Literal["scrape", "analyze"] = "scrape") -> JobStatus:
        job = JobStatus(job_id=uuid.uuid4().hex[:12], kind=kind, status="queued", source=source, mode=mode,
                        created_at=_now())
        await self._save(job.job_id, job.model_dump(exclude_none=True))
        return job

    async def update(self, job_id: str, **fields: str | int) -> None:
        await self._save(job_id, fields)

    async def get(self, job_id: str) -> JobStatus | None:
        data = await self._redis.hgetall(f"job:{job_id}")
        return JobStatus.model_validate(data) if data else None

    async def _save(self, job_id: str, fields: Mapping[str, object]) -> None:
        key = f"job:{job_id}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping={name: str(value) for name, value in fields.items()})
            pipe.expire(key, JOB_TTL)
            await pipe.execute()


async def run_scrape_job(job_id: str, collect: Callable[[], Awaitable[ScrapeOutcome]], redis: Redis,
                         session_factory: async_sessionmaker[AsyncSession],
                         notify: Callable[[list[NewNews]], Awaitable[object]] | None = None) -> None:
    """Виконується ПІСЛЯ відповіді клієнту (BackgroundTasks)."""
    jobs = JobStore(redis)
    await jobs.update(job_id, status="running")
    try:
        outcome = await collect()
        valid, _ = validate_news(outcome.news)
        async with session_factory() as session:          # своя сесія: сесія запиту вже закрита
            new = await NewsRepository(session).insert_new(valid)
            await session.commit()
        await NewsCache(redis).invalidate()                # після COMMIT
        await jobs.update(job_id, status="done", news_found=len(outcome.news), news_saved=len(new),
                          finished_at=_now())
        if notify is not None and new:
            try:
                await notify(new)
            except Exception:                              # новини вже в базі: збій розсилки — не збій збору
                logger.exception("scrape job %s: сповіщення не надіслано", job_id)
    except Exception as error:                             # задачу ніхто не чекає — фіксуємо помилку в статусі
        logger.exception("scrape job %s failed", job_id)
        await jobs.update(job_id, status="failed", error=f"{type(error).__name__}: {error}", finished_at=_now())


async def run_analyze_job(job_id: str, llm: LLMClient, limit: int, redis: Redis,
                          session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Аналізує до `limit` новин без аналізу — по одній (безкоштовна квота Gemini — кілька запитів за хвилину).

    Кожна новина комітиться окремо: збій на 30-й не скасовує 29 уже оплачених аналізів.
    Відкритий breaker зупиняє задачу — решта новин однаково отримала б 503.
    """
    jobs, cache = JobStore(redis), AnalysisCache(redis)
    await jobs.update(job_id, status="running")
    analyzed = failed = 0
    try:
        async with session_factory() as session:
            repo = NewsRepository(session)
            rows = await repo.find_unanalyzed(limit)
            await jobs.update(job_id, news_found=len(rows))
            for row in rows:
                try:
                    result = await analyze_news(row.title, llm, cache)
                except CircuitOpen:
                    raise
                except LLMError as error:                  # одна новина не вдалась — ідемо далі
                    failed += 1
                    logger.warning("analyze job %s: новина %s — %s", job_id, row.id, error)
                    continue
                await repo.save_analysis(row, result.analysis)
                await session.commit()
                analyzed += 1
                await jobs.update(job_id, news_analyzed=analyzed, news_failed=failed)
        await jobs.update(job_id, status="done", news_analyzed=analyzed, news_failed=failed, finished_at=_now())
    except Exception as error:
        logger.exception("analyze job %s failed", job_id)
        await jobs.update(job_id, status="failed", news_analyzed=analyzed, news_failed=failed,
                          error=f"{type(error).__name__}: {error}", finished_at=_now())
    finally:
        if analyzed:
            await NewsCache(redis).invalidate()            # стрічка й статистика тепер з аналізом
