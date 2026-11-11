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
Урок 43 — аналіз LLM (llm.py, analysis.py):
- `POST /api/news/{news_id}/analyze` — підсумок, тема, тональність, ключові слова; результат — у рядку новини;
- `POST /api/analyze/jobs` — пакетний аналіз у фоні; статус — `GET /api/analyze/jobs/{job_id}`;
- клієнт LLM — через `Depends(get_llm_client)`: тести підміняють його на FakeLLM, без мережі й ключа;
- збій провайдера → 502, відкритий breaker або немає ключа → 503; фільтри `?ai_category=&sentiment=`.
Урок 46 — безпека (security.py, safe_fetch.py, webhooks.py):
- `POST /api/admin/token` — пароль адміна → JWT; кожен ендпоінт запису, збору й аналізу — лише з токеном
  (`dependencies=[AdminDep]`); читання новин лишається публічним;
- RSS-джерела адміна: `POST/GET/DELETE /api/sources`, `POST /api/sources/{id}/fetch` — завантаження лише
  через `safe_fetch` (без SSRF);
- `POST /api/webhooks/scrape` — збір за підписаним запитом зовнішнього планувальника (HMAC + час + повтор).

Запуск: alembic upgrade head && uvicorn news_hub.api:app --reload  →  http://127.0.0.1:8000/docs
(Redis: docker compose up -d redis; адреса — REDIS_URL)
"""
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, ValidationError, field_validator
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .analysis import AnalysisCache, InvalidLLMOutput, NewsAnalysis, Sentiment, Topic, analyze_news
from .cache import NewsCache, get_redis, make_redis
from .db import SessionFactory, engine, get_db
from .jobs import JobStatus, JobStore, run_analyze_job, run_scrape_job
from .llm import CircuitBreaker, CircuitOpen, GuardedLLM, LLMClient, LLMError, make_llm
from .middleware import invalidate_cache, rate_limit, request_context
from .models import NewsItem, is_rbc_host, validate_news
from .repository import NewsRepository, SourceRepository
from .rss import parse_pravda_rss
from .safe_fetch import DEFAULT_POLICY, FetchError, FetchPolicy, UnsafeURL, check_url, safe_fetch
from .scraper import PageResult, ScrapeOutcome, scrape_all_async, scrape_sequential
from .security import AdminDep, AdminSettingsDep, authenticate, create_access_token, load_admin_settings
from .snapshot import load_snapshot
from .tables import NewsRow, SourceRow
from .webhooks import WebhookRejected, load_webhook_secret, remember_delivery, verify_signature

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
    app.state.admin = load_admin_settings()      # урок 46: None — адмінку не налаштовано (запис → 503)
    app.state.webhook_secret = load_webhook_secret()
    app.state.redis = make_redis()       # таблиці створює міграція: alembic upgrade head
    app.state.llm = make_llm()           # None — немає ключа: аналіз відповідатиме 503
    yield
    if app.state.llm is not None:
        await app.state.llm.aclose()     # HTTP-сесія клієнта LLM
    await app.state.redis.aclose()       # після зупинки — закрити з'єднання з Redis
    await engine.dispose()               # і пул з'єднань з базою


app = FastAPI(
    title="news_hub API",
    description="Новинний агрегатор курсу: парсинг rbc.ua → перевірені `NewsItem` → база → кеш → API → "
                "аналіз LLM; запис — лише адміну з JWT. Урок 46.",
    version="0.46.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "news", "description": "Новини в базі"},
        {"name": "scrape", "description": "Зібрати новини з сайту або знімка"},
        {"name": "analyze", "description": "Аналіз новин моделлю (Gemini або Anthropic)"},
        {"name": "admin", "description": "Вхід адміна і RSS-джерела"},
        {"name": "webhooks", "description": "Запити від інших систем, підписані HMAC"},
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


def get_llm_client(request: Request) -> LLMClient:
    """Клієнт провайдера з lifespan. Тести підміняють саме цю залежність (FakeLLM)."""
    llm: LLMClient | None = request.app.state.llm
    if llm is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="LLM не налаштовано: задай GEMINI_API_KEY (або LLM_PROVIDER=anthropic + "
                                   "ANTHROPIC_API_KEY і ANTHROPIC_MODEL)")
    return llm


def get_llm(client: Annotated[LLMClient, Depends(get_llm_client)], redis: RedisDep) -> LLMClient:
    """Будь-який клієнт — лише через breaker."""
    return GuardedLLM(client, CircuitBreaker(redis))


LLMDep = Annotated[LLMClient, Depends(get_llm)]


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, error: Exception) -> JSONResponse:
    """Помилки LLM → HTTP: відкритий breaker — 503 з Retry-After; збій провайдера чи невалідна відповідь — 502."""
    if isinstance(error, CircuitOpen):
        return JSONResponse(status_code=503, headers={"Retry-After": str(error.retry_after)},
                            content={"detail": str(error)})
    reason = "невалідна відповідь моделі" if isinstance(error, InvalidLLMOutput) else "провайдер LLM недоступний"
    return JSONResponse(status_code=502, content={"detail": f"{reason}: {error}"})


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
    # аналіз LLM (урок 43); None — ще не аналізували
    summary: str | None = None
    ai_category: str | None = None
    sentiment: str | None = None
    keywords: list[str] | None = None
    analyzed_at: datetime | None = None


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
    ai_category: dict[str, int] = Field(description="тема за аналізом LLM (лише проаналізовані)")
    sentiment: dict[str, int]


class AnalyzeOut(BaseModel):
    news_id: int
    source: Literal["db", "cache", "llm"] = Field(description="db — уже був у базі; cache — з Redis; llm — новий виклик")
    model: str | None = Field(description="яка модель відповіла (None — без виклику)")
    input_tokens: int = 0
    output_tokens: int = 0
    analyzed_at: datetime
    analysis: NewsAnalysis


class AnalyzeJobRequest(BaseModel):
    limit: int = Field(20, ge=1, le=200, description="скільки неаналізованих новин обробити")


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
    ai_category: Topic | None = Query(None, description="тема за аналізом LLM"),
    sentiment: Sentiment | None = Query(None),
) -> Response:
    """Новини з фільтрами й пагінацією: `?lang=uk&limit=5`. Відповідь кешується в Redis на 60 с."""
    key = await cache.key("list", {"skip": skip, "limit": limit, "category": category, "source": source,
                                   "lang": lang or "", "ai_category": ai_category or "",
                                   "sentiment": sentiment or ""})
    if (cached := await cache.get(key)) is not None:
        return cached_json(cached, "HIT")                       # база не потрібна
    rows = await repo.find(skip=skip, limit=limit, category=category, source=source, lang=lang or "",
                           ai_category=ai_category or "", sentiment=sentiment or "")
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
    """Скільки новин у кожній категорії, мові, джерелі, темі й тональності — GROUP BY у базі; кеш 60 с."""
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


@app.post("/api/scrape", response_model=ScrapeReport, tags=["scrape"], summary="Зібрати новини",
          dependencies=[AdminDep])
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
          summary="Зібрати новини у фоні", dependencies=[AdminDep])
async def start_scrape_job(request: ScrapeRequest, background: BackgroundTasks, redis: RedisDep,
                           scrapers: ScrapersDep,
                           session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
                           ) -> JobStatus:
    """Відповідає одразу `202` з job_id; збір іде після відповіді. Статус — GET /api/scrape/jobs/{job_id}."""
    job = await JobStore(redis).create(request.source, request.mode)
    background.add_task(run_scrape_job, job.job_id, lambda: collect(request, scrapers), redis, session_factory)
    return job


@app.get("/api/scrape/jobs/{job_id}", response_model=JobStatus, tags=["scrape"], dependencies=[AdminDep],
         responses={404: {"description": "такої задачі немає (або минула доба)"}})
async def get_scrape_job(job_id: str, redis: RedisDep) -> JobStatus:
    job = await JobStore(redis).get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"задачі {job_id} немає")
    return job


@app.delete("/api/news", tags=["news"], dependencies=[AdminDep])
async def delete_all_news(repo: RepoDep) -> dict[str, int]:
    return {"deleted": await repo.clear()}


# ---------------------------------------------------------------------------
# CRUD окремої новини
# ---------------------------------------------------------------------------

@app.post("/api/news", response_model=NewsOut, status_code=status.HTTP_201_CREATED, tags=["news"],
          dependencies=[AdminDep], responses={409: {"description": "новина з таким url уже є"}})
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


@app.patch("/api/news/{news_id}", response_model=NewsOut, tags=["news"], dependencies=[AdminDep],
           responses={404: {"description": "такої новини немає"}})
async def update_news(body: NewsPatch, row: RowDep) -> NewsRow:
    """Змінити заголовок і/або категорію; поля, яких немає в тілі, не чіпаємо."""
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    return row


@app.delete("/api/news/{news_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["news"],
            dependencies=[AdminDep], responses={404: {"description": "такої новини немає"}})
async def delete_news(row: RowDep, repo: RepoDep) -> Response:
    await repo.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Аналіз LLM (урок 43)
# ---------------------------------------------------------------------------

@app.post("/api/news/{news_id}/analyze", response_model=AnalyzeOut, tags=["analyze"], summary="Аналіз новини LLM",
          dependencies=[AdminDep], responses={404: {"description": "такої новини немає"},
                     502: {"description": "провайдер не відповів або відповідь не пройшла перевірку"},
                     503: {"description": "LLM не налаштовано або breaker відкритий"}})
async def analyze(row: RowDep, repo: RepoDep, llm: LLMDep, redis: RedisDep,
                  force: bool = Query(False, description="аналізувати заново, навіть якщо результат уже є")
                  ) -> AnalyzeOut:
    """Підсумок, тема, тональність і ключові слова заголовка. Уже проаналізовану новину модель не бачить удруге."""
    if row.analyzed_at is not None and not force:
        stored = NewsAnalysis.model_validate({"summary": row.summary, "category": row.ai_category,
                                              "sentiment": row.sentiment, "keywords": row.keywords or []})
        return AnalyzeOut(news_id=row.id, source="db", model=None, analyzed_at=row.analyzed_at, analysis=stored)
    result = await analyze_news(row.title, llm, AnalysisCache(redis), refresh=force)
    analyzed_at = await repo.save_analysis(row, result.analysis)
    return AnalyzeOut(news_id=row.id, source="cache" if result.cached else "llm",
                      model=None if result.cached else result.model, input_tokens=result.input_tokens,
                      output_tokens=result.output_tokens, analyzed_at=analyzed_at, analysis=result.analysis)


@app.post("/api/analyze/jobs", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED, tags=["analyze"],
          summary="Проаналізувати новини у фоні", dependencies=[AdminDep])
async def start_analyze_job(request: AnalyzeJobRequest, background: BackgroundTasks, redis: RedisDep, llm: LLMDep,
                            session_factory: Annotated[async_sessionmaker[AsyncSession],
                                                       Depends(get_session_factory)],
                            ) -> JobStatus:
    """`202` з job_id одразу; новини без аналізу обробляються після відповіді, по одній."""
    job = await JobStore(redis).create("db", llm.name, kind="analyze")
    background.add_task(run_analyze_job, job.job_id, llm, request.limit, redis, session_factory)
    return job


@app.get("/api/analyze/jobs/{job_id}", response_model=JobStatus, tags=["analyze"], dependencies=[AdminDep],
         responses={404: {"description": "такої задачі немає (або минула доба)"}})
async def get_analyze_job(job_id: str, redis: RedisDep) -> JobStatus:
    job = await JobStore(redis).get(job_id)
    if job is None or job.kind != "analyze":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"задачі аналізу {job_id} немає")
    return job


# ---------------------------------------------------------------------------
# Адмін: вхід (урок 46)
# ---------------------------------------------------------------------------

class TokenRequest(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=1000)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="секунд")


@app.post("/api/admin/token", response_model=TokenResponse, tags=["admin"], summary="Вхід адміна → JWT",
          responses={401: {"description": "неправильне ім'я або пароль"},
                     429: {"description": "забагато спроб входу"}})
async def admin_token(body: TokenRequest, settings: AdminSettingsDep) -> TokenResponse:
    """Одна відповідь на «немає такого імені» і «не той пароль» — не підказуємо, що саме не так."""
    if not authenticate(settings, body.username, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="неправильне ім'я або пароль")
    return TokenResponse(access_token=create_access_token(settings, body.username),
                         expires_in=settings.expire_minutes * 60)


# ---------------------------------------------------------------------------
# RSS-джерела адміна: чужі URL — лише через safe_fetch (урок 46)
# ---------------------------------------------------------------------------

def get_fetch_policy() -> FetchPolicy:
    """Що дозволено завантажувати. Тести підміняють: локальний сервер — лише там, де це явно потрібно."""
    return DEFAULT_POLICY


FetchPolicyDep = Annotated[FetchPolicy, Depends(get_fetch_policy)]


def get_sources(session: SessionDep) -> SourceRepository:
    return SourceRepository(session)


SourcesDep = Annotated[SourceRepository, Depends(get_sources)]


class SourceCreate(BaseModel):
    url: str = Field(max_length=500, examples=["https://www.pravda.com.ua/rss/view_news/"])
    name: str = Field(min_length=2, max_length=100)


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    name: str
    created_at: datetime


class SourceFetchReport(BaseModel):
    source_id: int
    final_url: str = Field(description="адреса після перенаправлень")
    redirects: int
    news_found: int
    news_valid: int
    news_saved: int
    rejected: list[str]


def unsafe(error: UnsafeURL) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"заборонена адреса: {error}")


async def get_source_or_404(source_id: int, sources: SourcesDep) -> SourceRow:
    row = await sources.get(source_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"джерела {source_id} немає")
    return row


SourceDep = Annotated[SourceRow, Depends(get_source_or_404)]


@app.post("/api/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED, tags=["admin"],
          summary="Додати RSS-джерело", dependencies=[AdminDep],
          responses={400: {"description": "адреса заборонена (схема, порт, логін у URL, не публічна IP)"},
                     409: {"description": "таке джерело вже є"}})
async def create_source(body: SourceCreate, sources: SourcesDep, policy: FetchPolicyDep) -> SourceRow:
    """Перевірка без мережі (схема, порт, IP в адресі); DNS і з'єднання перевіряються при кожному збиранні."""
    try:
        url = str(check_url(body.url, policy))
    except UnsafeURL as error:
        raise unsafe(error) from error
    try:
        return await sources.create(url, body.name)
    except IntegrityError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"джерело {url} уже є") from error


@app.get("/api/sources", response_model=list[SourceOut], tags=["admin"], dependencies=[AdminDep])
async def list_sources(sources: SourcesDep) -> list[SourceRow]:
    return await sources.all()


@app.delete("/api/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["admin"],
            dependencies=[AdminDep])
async def delete_source(row: SourceDep, sources: SourcesDep) -> Response:
    await sources.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/sources/{source_id}/fetch", response_model=SourceFetchReport, tags=["admin"],
          summary="Зібрати новини з RSS-джерела", dependencies=[AdminDep],
          responses={400: {"description": "адреса (чи перенаправлення) веде туди, куди серверу не можна"},
                     502: {"description": "джерело не відповіло, завелике або не RSS"}})
async def fetch_source(row: SourceDep, repo: RepoDep, policy: FetchPolicyDep) -> SourceFetchReport:
    """RSS → `parse_pravda_rss` (RSS 2.0) → `NewsItem` → база. Вміст відповіді назовні не віддаємо — лише підсумок."""
    try:
        result = await safe_fetch(row.url, policy)
    except UnsafeURL as error:
        raise unsafe(error) from error
    except FetchError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"джерело недоступне: {error}") from error
    try:
        raw = parse_pravda_rss(result.text())
    except ValueError as error:                        # пошкоджений XML
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"це не RSS: {error}") from error
    valid, rejected = validate_news(raw)
    saved = await repo.add_many(valid)
    return SourceFetchReport(source_id=row.id, final_url=result.url, redirects=result.redirects,
                             news_found=len(raw), news_valid=len(valid), news_saved=saved,
                             rejected=[f"{r.raw['url']}: {'; '.join(r.errors)}" for r in rejected[:5]])


# ---------------------------------------------------------------------------
# Вхідні webhook (урок 46)
# ---------------------------------------------------------------------------

def get_webhook_secret(request: Request) -> bytes:
    secret: bytes | None = request.app.state.webhook_secret
    if secret is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="webhook вимкнено: задай WEBHOOK_SECRET")
    return secret


@app.post("/api/webhooks/scrape", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED,
          tags=["webhooks"], summary="Збір за підписаним запитом",
          responses={401: {"description": "немає підпису, він не збігається або запит застарий"},
                     409: {"description": "повтор уже отриманого запиту"}})
async def scrape_webhook(request: Request, background: BackgroundTasks, redis: RedisDep, scrapers: ScrapersDep,
                         secret: Annotated[bytes, Depends(get_webhook_secret)],
                         session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
                         ) -> JobStatus:
    """Тіло — як у POST /api/scrape/jobs. Спершу підпис сирих байтів, лише потім розбір JSON."""
    body = await request.body()
    try:
        signature = verify_signature(secret, request.headers, body)
        await remember_delivery(redis, signature)
    except WebhookRejected as error:
        raise HTTPException(error.status_code, detail=str(error)) from error
    try:
        scrape_request = ScrapeRequest.model_validate_json(body or b"{}")
    except ValidationError as error:         # include_input=False: сирі bytes у відповідь JSON не серіалізуються
        raise HTTPException(422, detail=error.errors(include_url=False, include_context=False,
                                                      include_input=False)) from error
    job = await JobStore(redis).create(scrape_request.source, scrape_request.mode)
    background.add_task(run_scrape_job, job.job_id, lambda: collect(scrape_request, scrapers), redis, session_factory)
    return job
