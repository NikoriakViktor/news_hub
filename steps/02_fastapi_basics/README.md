# news_hub — новинний агрегатор (крок 2: FastAPI)

Наскрізний проєкт книги: парсер новин → перевірені моделі → API → база → кеш → підсумки від Gemini → Telegram-бот → Docker. Кожен крок — рефакторинг проєкту попереднього.

| Крок | Що додається |
|---|---|
| 1 | стартовий парсер з анотаціями типів; `NewsItem` на Pydantic |
| **2** | **FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman** ← ти тут |
| 3 | SQLAlchemy: новини в базі, унікальний `url` |
| 4 | middleware, кеш і rate limit на Redis |
| 5 | тести API (pytest + httpx) |
| 7 | Gemini: підсумок, категорія, тональність |
| 9 | Telegram-бот: `/news`, `/digest` |
| 48–50 | Docker, Compose, CI/CD |

## Що тут

```
news_hub/
├── news_hub/
│   ├── parser.py     ← стартовий parse_rbc_news + типи: HTML → list[RawNews]
│   ├── models.py     ← NewsItem (Pydantic), validate_news: RawNews → перевірені / відхилені
│   ├── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
│   ├── scraper.py    ← крок 2: сторінки rbc.ua через aiohttp — разом (gather) або по черзі
│   ├── store.py      ← крок 2: NewsStore — сховище в пам'яті (крок 3 → SQLAlchemy)
│   └── api.py        ← крок 2: FastAPI — /api/news, /api/news/stats, POST /api/scrape
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── postman/news_hub.postman_collection.json   ← 7 запитів з перевірками
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
└── tests/            ← pytest: моделі, парсер, знімок, API (TestClient)
```

## Запуск

```bash
pip install -r requirements.txt
pytest                      # 23 тести
mypy --strict news_hub      # перевірка типів
uvicorn news_hub.api:app --reload
```

- http://127.0.0.1:8000/docs — Swagger UI: спершу `POST /api/scrape` з `{"source": "snapshot"}`, потім `GET /api/news`;
- Postman: Import → `postman/news_hub.postman_collection.json` → Run collection;
- без Postman: `npx newman run postman/news_hub.postman_collection.json`.

Свіжа стрічка (коли `www.rbc.ua` доступний з мережі) — `POST /api/scrape` з `{}` або
`{"mode": "sequential"}`; у відповіді — час кожної сторінки й помилки, якщо сторінка не завантажилась.

Розбір змін — [Крок 2 у книзі](https://nikoriakviktor.github.io/news_hub/tutorials/02_fastapi_basics/).
