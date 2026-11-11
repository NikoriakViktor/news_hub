"""Фоновий збір: POST відповідає одразу `202 Accepted`, збір іде після відповіді.

Основа — `POST /api/scrape/archive` + `GET /api/scrape/archive/{job_id}` з `app/main.py`
прототипу `news_dashboard`: `BackgroundTasks`, uuid задачі, статус у колекції MongoDB `scrape_jobs`.
Рефакторинг уроку 39:
- статус задачі — hash у Redis `job:<id>` з TTL (добу), а не документ у базі новин;
- фонова задача відкриває **власну** сесію бази: сесія запиту (get_db) закривається разом із запитом,
  а старий код передавав у задачу `db` запиту;
- помилка всередині задачі не губиться: статус `failed` і текст помилки.
"""
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .cache import NewsCache
from .models import validate_news
from .repository import NewsRepository
from .scraper import ScrapeOutcome

logger = logging.getLogger("news_hub")

JOB_TTL = 24 * 3600


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    source: str
    mode: str
    news_found: int = 0
    news_saved: int = 0
    error: str | None = None
    created_at: str
    finished_at: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def create(self, source: str, mode: str) -> JobStatus:
        job = JobStatus(job_id=uuid.uuid4().hex[:12], status="queued", source=source, mode=mode, created_at=_now())
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
                         session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Виконується ПІСЛЯ відповіді клієнту (BackgroundTasks)."""
    jobs = JobStore(redis)
    await jobs.update(job_id, status="running")
    try:
        outcome = await collect()
        valid, _ = validate_news(outcome.news)
        async with session_factory() as session:          # своя сесія: сесія запиту вже закрита
            saved = await NewsRepository(session).add_many(valid)
            await session.commit()
        await NewsCache(redis).invalidate()                # після COMMIT
        await jobs.update(job_id, status="done", news_found=len(outcome.news), news_saved=saved,
                          finished_at=_now())
    except Exception as error:                             # задачу ніхто не чекає — фіксуємо помилку в статусі
        logger.exception("scrape job %s failed", job_id)
        await jobs.update(job_id, status="failed", error=f"{type(error).__name__}: {error}", finished_at=_now())
