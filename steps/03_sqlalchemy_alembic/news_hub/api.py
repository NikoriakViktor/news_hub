"""HTTP API агрегатора: FastAPI поверх парсера й моделі з уроку 36.

Урок 37: ядро `app/main.py` прототипу `news_dashboard` (`/api/news`, `/stats`, `POST /api/scrape`),
сховище `NewsStore` через `Depends`.
Урок 38 — рефакторинг сховища:
- `NewsStore` у пам'яті → `NewsRepository` над SQLAlchemy (PostgreSQL або SQLite); сесія на запит — `get_db`;
- у відповіді з'явились `id` і `scraped_at` — їх дає база (`NewsOut`);
- повний CRUD окремої новини: `GET/PATCH/DELETE /api/news/{news_id}`, `POST /api/news`;
- той самий url удруге → `409 Conflict` (унікальність гарантує база);
- `Depends(get_db, scope="function")` — COMMIT до відповіді, а не після (див. SessionDep).

Запуск: alembic upgrade head && uvicorn news_hub.api:app --reload  →  http://127.0.0.1:8000/docs
"""
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .db import engine, get_db
from .models import NewsItem, validate_news
from .repository import NewsRepository
from .scraper import PageResult, ScrapeOutcome, scrape_all_async, scrape_sequential
from .snapshot import load_snapshot
from .tables import NewsRow

Scraper = Callable[[list[str] | None], Awaitable[ScrapeOutcome]]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield                                # таблиці створює міграція: alembic upgrade head
    await engine.dispose()               # після зупинки — закрити пул з'єднань


app = FastAPI(
    title="news_hub API",
    description="Новинний агрегатор курсу: парсинг rbc.ua → перевірені `NewsItem` → база → API. Урок 38.",
    version="0.38.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "news", "description": "Новини в базі"},
        {"name": "scrape", "description": "Зібрати новини з сайту або знімка"},
        {"name": "system", "description": "Службові ендпоінти"},
    ],
)


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


@app.get("/api/news", response_model=list[NewsOut], tags=["news"], summary="Список новин")
async def list_news(
    repo: RepoDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    category: str = Query("", description="Новини, Економіка, …"),
    source: str = Query("", description="rbc.ua, auto.rbc.ua, …"),
    lang: Literal["uk", "ru"] | None = Query(None),
) -> list[NewsRow]:
    """Новини з фільтрами й пагінацією: `?lang=uk&limit=5`."""
    return await repo.find(skip=skip, limit=limit, category=category, source=source, lang=lang or "")


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
async def news_stats(repo: RepoDep) -> Stats:
    """Скільки новин у кожній категорії, мові й джерелі — GROUP BY у базі."""
    return Stats(total=await repo.count(), **await repo.stats())


@app.post("/api/scrape", response_model=ScrapeReport, tags=["scrape"], summary="Зібрати новини")
async def scrape(
    request: ScrapeRequest,
    repo: RepoDep,
    scrapers: Annotated[dict[str, Scraper], Depends(get_scrapers)],
) -> ScrapeReport:
    """Завантажує сторінки (або знімок), перевіряє кожну новину моделлю `NewsItem`, зберігає нові."""
    if request.source == "snapshot":
        outcome = ScrapeOutcome(pages=[], news=load_snapshot(), total_time=0.0)
    else:
        pages = [str(url) for url in request.pages] if request.pages else None
        outcome = await scrapers[request.mode](pages)

    valid, rejected = validate_news(outcome.news)
    saved = await repo.add_many(valid)
    return ScrapeReport(
        source=request.source, mode=request.mode, total_time=outcome.total_time, pages=outcome.pages,
        news_found=len(outcome.news), news_valid=len(valid), news_saved=saved, news_total=await repo.count(),
        rejected=[f"{r.raw['url']}: {'; '.join(r.errors)}" for r in rejected[:5]],
    )


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
