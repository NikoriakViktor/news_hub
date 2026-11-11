"""HTTP API агрегатора: FastAPI поверх парсера й моделі з уроку 36.

Урок 37: ядро `app/main.py` прототипу `news_dashboard` (`/api/news`, `/stats`, `POST /api/scrape`),
сховище `NewsStore` через `Depends`.
Урок 38 — рефакторинг сховища:
- `NewsStore` у пам'яті → `NewsRepository` над SQLAlchemy (PostgreSQL або SQLite); сесія на запит — `get_db`;
- у відповіді з'явились `id` і `scraped_at` — їх дає база (`NewsOut`);
- повний CRUD окремої новини: `GET/PATCH/DELETE /api/news/{news_id}`, `POST /api/news`;
- той самий url удруге → `409 Conflict` (унікальність гарантує база);
- `Depends(get_db, scope="function")` — COMMIT до відповіді, а не після (див. SessionDep).
Урок 39 — Redis і middleware:
- кеш `GET /api/news` і `/api/news/stats` (cache-aside, заголовок X-Cache: HIT/MISS);
- middleware: X-Request-ID і X-Process-Time; rate limit на POST /api/scrape*; інвалідація кешу після COMMIT;
- фоновий збір: `POST /api/scrape/jobs` → 202 + job_id, статус — `GET /api/scrape/jobs/{job_id}`.
Урок 41 — тести: `pages` з `https://fakerbc.ua/` проходили перевірку (endswith) — сервер завантажив би
чужий сайт на прохання будь-кого; тепер `is_rbc_host` (models.py).

Запуск: alembic upgrade head && uvicorn news_hub.api:app --reload  →  http://127.0.0.1:8000/docs
(Redis: docker compose up -d redis; адреса — REDIS_URL)
"""
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, ValidationError, field_validator
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .cache import NewsCache, get_redis, make_redis
from .db import SessionFactory, engine, get_db
from .jobs import JobStatus, JobStore, run_scrape_job
from .middleware import invalidate_cache, rate_limit, request_context
from .models import NewsItem, is_rbc_host, validate_news
from .repository import NewsRepository
from .scraper import PageResult, ScrapeOutcome, scrape_all_async, scrape_sequential
from .snapshot import load_snapshot
from .tables import NewsRow

Scraper = Callable[[list[str] | None], Awaitable[ScrapeOutcome]]


def setup_logging() -> None:
    """uvicorn налаштовує лише свої логери; без цього рядки журналу news_hub нікуди не потрапили б."""
    logger = logging.getLogger("news_hub")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    app.state.redis = make_redis()       # таблиці створює міграція: alembic upgrade head
    yield
    await app.state.redis.aclose()       # після зупинки — закрити з'єднання з Redis
    await engine.dispose()               # і пул з'єднань з базою


app = FastAPI(
    title="news_hub API",
    description="Новинний агрегатор курсу: парсинг rbc.ua → перевірені `NewsItem` → база → кеш → API. Урок 41.",
    version="0.41.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "news", "description": "Новини в базі"},
        {"name": "scrape", "description": "Зібрати новини з сайту або знімка"},
        {"name": "system", "description": "Службові ендпоінти"},
    ],
)


# Middleware: останній зареєстрований — зовнішній. Запит іде request_context → rate_limit → invalidate_cache
# → ендпоінт, відповідь — у зворотному порядку.
app.middleware("http")(invalidate_cache)
app.middleware("http")(rate_limit)
app.middleware("http")(request_context)


# ---------------------------------------------------------------------------
# Залежності
# ---------------------------------------------------------------------------

# scope="function": COMMIT у get_db виконується ДО відправлення відповіді. Без цього (FastAPI ≥ 0.118)
# код після yield іде вже після відповіді — клієнт отримав би 200, навіть якщо COMMIT не вдався.
SessionDep = Annotated[AsyncSession, Depends(get_db, scope="function")]


def get_repo(session: SessionDep) -> NewsRepository:
    return NewsRepository(session)


def get_scrapers() -> dict[str, Scraper]:
    return {"async": scrape_all_async, "sequential": scrape_sequential}


RepoDep = Annotated[NewsRepository, Depends(get_repo)]
RedisDep = Annotated[Redis, Depends(get_redis)]


def get_cache(redis: RedisDep) -> NewsCache:
    return NewsCache(redis)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Для фонових задач: у них своя сесія (тести підміняють на тестову базу)."""
    return SessionFactory


CacheDep = Annotated[NewsCache, Depends(get_cache)]


async def get_news_or_404(news_id: int, repo: RepoDep) -> NewsRow:
    row = await repo.get(news_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"новини {news_id} немає")
    return row


RowDep = Annotated[NewsRow, Depends(get_news_or_404)]


# ---------------------------------------------------------------------------
# Моделі запитів і відповідей
# ---------------------------------------------------------------------------

class NewsOut(NewsItem):
    """NewsItem + те, що дає база. from_attributes — будується з об'єкта NewsRow."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    scraped_at: datetime


class NewsCreate(BaseModel):
    """Тіло POST /api/news — як сирий рядок парсера; перевіряє NewsItem."""
    title: str
    url: str
    published_time: str = ""


class NewsPatch(BaseModel):
    """PATCH: лише ті поля, які передали."""
    title: str | None = Field(None, min_length=10, max_length=300)
    category: str | None = Field(None, min_length=2, max_length=100)


class ScrapeRequest(BaseModel):
    source: Literal["live", "snapshot"] = Field("live", description="live — сайт; snapshot — збережений знімок")
    mode: Literal["async", "sequential"] = Field("async", description="сторінки одночасно чи по черзі")
    pages: list[HttpUrl] | None = Field(None, max_length=20, description="порожньо — стандартний список сторінок")

    @field_validator("pages")
    @classmethod
    def only_rbc(cls, pages: list[HttpUrl] | None) -> list[HttpUrl] | None:
        for url in pages or []:
            if not is_rbc_host(url.host):
                raise ValueError(f"сервер завантажує лише сторінки rbc.ua, а не {url.host}")
        return pages


class ScrapeReport(BaseModel):
    source: str
    mode: str
    total_time: float
    pages: list[PageResult]
    news_found: int = Field(description="усього новин на сторінках (без дублікатів)")
    news_valid: int = Field(description="пройшли перевірку NewsItem")
    news_saved: int = Field(description="нових у базі")
    news_total: int = Field(description="у базі після збору")
    rejected: list[str] = Field(description="перші 5 причин відхилення")


class Stats(BaseModel):
    total: int
    category: dict[str, int]
    lang: dict[str, int]
    source: dict[str, int]


# ---------------------------------------------------------------------------
# Ендпоінти: список, статистика, збір
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


NEWS_LIST = TypeAdapter(list[NewsOut])


def cached_json(payload: str | bytes, state: str) -> Response:
    return Response(content=payload, media_type="application/json", headers={"X-Cache": state})


@app.get("/api/news", response_model=list[NewsOut], tags=["news"], summary="Список новин")
async def list_news(
    repo: RepoDep,
    cache: CacheDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    category: str = Query("", description="Новини, Економіка, …"),
    source: str = Query("", description="rbc.ua, auto.rbc.ua, …"),
    lang: Literal["uk", "ru"] | None = Query(None),
) -> Response:
    """Новини з фільтрами й пагінацією: `?lang=uk&limit=5`. Відповідь кешується в Redis на 60 с."""
    key = await cache.key("list", {"skip": skip, "limit": limit, "category": category,
                                   "source": source, "lang": lang or ""})
    if (cached := await cache.get(key)) is not None:
        return cached_json(cached, "HIT")                       # база не потрібна
    rows = await repo.find(skip=skip, limit=limit, category=category, source=source, lang=lang or "")
    payload = NEWS_LIST.dump_json([NewsOut.model_validate(row) for row in rows]).decode()
    await cache.set(key, payload)
    return cached_json(payload, "MISS")


@app.get("/api/news/search", response_model=list[NewsOut], tags=["news"], summary="Пошук у заголовках")
async def search_news(
    repo: RepoDep,
    q: str = Query(min_length=2, max_length=60, description="слово або частина слова"),
    limit: int = Query(20, ge=1, le=100),
) -> list[NewsRow]:
    """Оголошено ДО `/api/news/{news_id}`: інакше «search» потрапив би в news_id і отримав 422."""
    return await repo.search(q, limit)


@app.get("/api/news/count", tags=["news"])
async def news_count(repo: RepoDep) -> dict[str, int]:
    return {"count": await repo.count()}


@app.get("/api/news/stats", response_model=Stats, tags=["news"])
async def news_stats(repo: RepoDep, cache: CacheDep) -> Response:
    """Скільки новин у кожній категорії, мові й джерелі — GROUP BY у базі; кеш 60 с."""
    key = await cache.key("stats", {})
    if (cached := await cache.get(key)) is not None:
        return cached_json(cached, "HIT")
    payload = Stats(total=await repo.count(), **await repo.stats()).model_dump_json()
    await cache.set(key, payload)
    return cached_json(payload, "MISS")


ScrapersDep = Annotated[dict[str, Scraper], Depends(get_scrapers)]


async def collect(request: ScrapeRequest, scrapers: dict[str, Scraper]) -> ScrapeOutcome:
    """Знімок або сторінки сайту → сирі новини (спільне для POST /api/scrape і фонового збору)."""
    if request.source == "snapshot":
        return ScrapeOutcome(pages=[], news=load_snapshot(), total_time=0.0)
    pages = [str(url) for url in request.pages] if request.pages else None
    return await scrapers[request.mode](pages)


@app.post("/api/scrape", response_model=ScrapeReport, tags=["scrape"], summary="Зібрати новини")
async def scrape(request: ScrapeRequest, repo: RepoDep, scrapers: ScrapersDep) -> ScrapeReport:
    """Завантажує сторінки (або знімок), перевіряє кожну новину моделлю `NewsItem`, зберігає нові."""
    outcome = await collect(request, scrapers)
    valid, rejected = validate_news(outcome.news)
    saved = await repo.add_many(valid)
    return ScrapeReport(
        source=request.source, mode=request.mode, total_time=outcome.total_time, pages=outcome.pages,
        news_found=len(outcome.news), news_valid=len(valid), news_saved=saved, news_total=await repo.count(),
        rejected=[f"{r.raw['url']}: {'; '.join(r.errors)}" for r in rejected[:5]],
    )


@app.post("/api/scrape/jobs", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED, tags=["scrape"],
          summary="Зібрати новини у фоні")
async def start_scrape_job(request: ScrapeRequest, background: BackgroundTasks, redis: RedisDep,
                           scrapers: ScrapersDep,
                           session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
                           ) -> JobStatus:
    """Відповідає одразу `202` з job_id; збір іде після відповіді. Статус — GET /api/scrape/jobs/{job_id}."""
    job = await JobStore(redis).create(request.source, request.mode)
    background.add_task(run_scrape_job, job.job_id, lambda: collect(request, scrapers), redis, session_factory)
    return job


@app.get("/api/scrape/jobs/{job_id}", response_model=JobStatus, tags=["scrape"],
         responses={404: {"description": "такої задачі немає (або минула доба)"}})
async def get_scrape_job(job_id: str, redis: RedisDep) -> JobStatus:
    job = await JobStore(redis).get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"задачі {job_id} немає")
    return job


@app.delete("/api/news", tags=["news"])
async def delete_all_news(repo: RepoDep) -> dict[str, int]:
    return {"deleted": await repo.clear()}


# ---------------------------------------------------------------------------
# CRUD окремої новини
# ---------------------------------------------------------------------------

@app.post("/api/news", response_model=NewsOut, status_code=status.HTTP_201_CREATED, tags=["news"],
          responses={409: {"description": "новина з таким url уже є"}})
async def create_news(body: NewsCreate, repo: RepoDep) -> NewsRow:
    """Додати новину вручну. Перевірка — та сама модель NewsItem, що й для парсера."""
    try:
        item = NewsItem.from_raw({"title": body.title, "url": body.url, "category": "",
                                  "description": "", "datetime": body.published_time})
    except ValidationError as error:
        raise HTTPException(422,
                            detail=error.errors(include_url=False, include_context=False)) from error
    try:
        return await repo.create(item)
    except IntegrityError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"новина з url {item.url} уже є") from error


@app.get("/api/news/{news_id}", response_model=NewsOut, tags=["news"],
         responses={404: {"description": "такої новини немає"}})
async def get_news(row: RowDep) -> NewsRow:
    return row


@app.patch("/api/news/{news_id}", response_model=NewsOut, tags=["news"],
           responses={404: {"description": "такої новини немає"}})
async def update_news(body: NewsPatch, row: RowDep) -> NewsRow:
    """Змінити заголовок і/або категорію; поля, яких немає в тілі, не чіпаємо."""
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    return row


@app.delete("/api/news/{news_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["news"],
            responses={404: {"description": "такої новини немає"}})
async def delete_news(row: RowDep, repo: RepoDep) -> Response:
    await repo.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
