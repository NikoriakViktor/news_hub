"""HTTP API агрегатора: FastAPI поверх парсера й моделі з уроку 36.

Основа — `app/main.py` прототипу `news_dashboard` (618 рядків: скрапінг, MongoDB, NLP,
архів, тренди). Рефакторинг уроку 37 лишає ядро — `/health`, `GET /api/news` з фільтрами,
`/api/news/count`, `/api/news/stats`, `POST /api/scrape`, `DELETE /api/news` — і змінює:
- `NewsItem` у відповіді — модель з уроку 36, а не друга копія полів;
- MongoDB у кожному ендпоінті → `NewsStore` через `Depends` (урок 38 підставить базу);
- `@app.on_event("startup")` (застарів) → `lifespan`;
- рядки з regex (`pattern="^(async|sequential)$"`) → `Literal`;
- `POST /api/scrape` приймав будь-які URL → лише сторінки rbc.ua; `source="snapshot"` — знімок.

Запуск: uvicorn news_hub.api:app --reload  →  http://127.0.0.1:8000/docs
"""
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel, Field, HttpUrl, field_validator

from .models import NewsItem, validate_news
from .scraper import PageResult, ScrapeOutcome, scrape_all_async, scrape_sequential
from .snapshot import load_snapshot
from .store import NewsStore

Scraper = Callable[[list[str] | None], Awaitable[ScrapeOutcome]]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.store = NewsStore()        # до першого запиту
    yield                                # тут сервер працює
    app.state.store.clear()              # після зупинки


app = FastAPI(
    title="news_hub API",
    description="Новинний агрегатор курсу: парсинг rbc.ua → перевірені `NewsItem` → API. Урок 37.",
    version="0.37.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "news", "description": "Новини, що вже зібрані"},
        {"name": "scrape", "description": "Зібрати новини з сайту або знімка"},
        {"name": "system", "description": "Службові ендпоінти"},
    ],
)


# ---------------------------------------------------------------------------
# Залежності: звідки ендпоінт бере сховище і скрапер
# ---------------------------------------------------------------------------

def get_store(request: Request) -> NewsStore:
    store: NewsStore = request.app.state.store
    return store


def get_scrapers() -> dict[str, Scraper]:
    return {"async": scrape_all_async, "sequential": scrape_sequential}


StoreDep = Annotated[NewsStore, Depends(get_store)]


# ---------------------------------------------------------------------------
# Моделі запитів і відповідей
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    source: Literal["live", "snapshot"] = Field("live", description="live — сайт; snapshot — збережений знімок")
    mode: Literal["async", "sequential"] = Field("async", description="сторінки одночасно чи по черзі")
    pages: list[HttpUrl] | None = Field(None, max_length=20, description="порожньо — стандартний список сторінок")

    @field_validator("pages")
    @classmethod
    def only_rbc(cls, pages: list[HttpUrl] | None) -> list[HttpUrl] | None:
        for url in pages or []:
            if not (url.host or "").endswith("rbc.ua"):
                raise ValueError(f"сервер завантажує лише сторінки rbc.ua, а не {url.host}")
        return pages


class ScrapeReport(BaseModel):
    source: str
    mode: str
    total_time: float
    pages: list[PageResult]
    news_found: int = Field(description="усього новин на сторінках (без дублікатів)")
    news_valid: int = Field(description="пройшли перевірку NewsItem")
    news_saved: int = Field(description="нових у сховищі")
    news_total: int = Field(description="у сховищі після збору")
    rejected: list[str] = Field(description="перші 5 причин відхилення")


class Stats(BaseModel):
    total: int
    category: dict[str, int]
    lang: dict[str, int]
    source: dict[str, int]


# ---------------------------------------------------------------------------
# Ендпоінти
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/news", response_model=list[NewsItem], tags=["news"], summary="Список новин")
async def list_news(
    store: StoreDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    category: str = Query("", description="Новини, Економіка, …"),
    source: str = Query("", description="rbc.ua, auto.rbc.ua, …"),
    lang: Literal["uk", "ru"] | None = Query(None),
) -> list[NewsItem]:
    """Новини з фільтрами й пагінацією: `?lang=uk&limit=5`."""
    return store.find(skip=skip, limit=limit, category=category, source=source, lang=lang or "")


@app.get("/api/news/count", tags=["news"])
async def news_count(store: StoreDep) -> dict[str, int]:
    return {"count": store.count()}


@app.get("/api/news/stats", response_model=Stats, tags=["news"])
async def news_stats(store: StoreDep) -> Stats:
    """Скільки новин у кожній категорії, мові й джерелі."""
    return Stats(total=store.count(), **store.stats())


@app.post("/api/scrape", response_model=ScrapeReport, tags=["scrape"], summary="Зібрати новини")
async def scrape(
    request: ScrapeRequest,
    store: StoreDep,
    scrapers: Annotated[dict[str, Scraper], Depends(get_scrapers)],
) -> ScrapeReport:
    """Завантажує сторінки (або знімок), перевіряє кожну новину моделлю `NewsItem`, зберігає нові."""
    if request.source == "snapshot":
        outcome = ScrapeOutcome(pages=[], news=load_snapshot(), total_time=0.0)
    else:
        pages = [str(url) for url in request.pages] if request.pages else None
        outcome = await scrapers[request.mode](pages)

    valid, rejected = validate_news(outcome.news)
    saved = store.add_many(valid)
    return ScrapeReport(
        source=request.source, mode=request.mode, total_time=outcome.total_time, pages=outcome.pages,
        news_found=len(outcome.news), news_valid=len(valid), news_saved=saved, news_total=store.count(),
        rejected=[f"{r.raw['url']}: {'; '.join(r.errors)}" for r in rejected[:5]],
    )


@app.delete("/api/news", tags=["news"])
async def delete_all_news(store: StoreDep) -> dict[str, int]:
    return {"deleted": store.clear()}
