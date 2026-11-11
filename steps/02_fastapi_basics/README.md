# news_hub — новинний агрегатор (крок 2: FastAPI)

Наскрізний проєкт FastAPI-гілки курсу: парсер новин → перевірені моделі → API → база → кеш → підсумки від Gemini → Telegram-бот → Docker. Кожен урок — рефакторинг проєкту попереднього.

| Урок | Крок |
|---|---|
| 37 | стартовий парсер з анотаціями типів; `NewsItem` на Pydantic |
| **38** | **FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman** ← ти тут |
| 39 | SQLAlchemy: новини в базі, унікальний `url` |
| 40 | middleware, кеш і rate limit на Redis |
| 42 | тести API (pytest + httpx) |
| 44 | Gemini: підсумок, категорія, тональність |
| 48 | Telegram-бот: `/news`, `/digest` |
| 48–50 | Docker, Compose, CI/CD |

## Що тут

```
news_hub/
├── news_hub/
│   ├── parser.py     ← стартовий parse_rbc_news + типи: HTML → list[RawNews]
│   ├── models.py     ← NewsItem (Pydantic), validate_news: RawNews → перевірені / відхилені
│   ├── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
│   ├── scraper.py    ← урок 38: сторінки rbc.ua через aiohttp — разом (gather) або по черзі
│   ├── store.py      ← урок 38: NewsStore — сховище в пам'яті (урок 39 → SQLAlchemy)
│   └── api.py        ← урок 38: FastAPI — /api/news, /api/news/stats, POST /api/scrape
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── postman/news_hub.postman_collection.json   ← 7 запитів з перевірками
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
└── tests/            ← pytest: моделі, парсер, знімок, API (TestClient)
```

Джерела коду: API і скрапер — прототип `news_dashboard/app/main.py` і `scraper.py`; `parse_rbc_news` — ноутбук про веб-скрапінг `note_lesson_32_web_scraping.ipynb`; словник категорій — `news_dashboard/app/scraper.py`. Знімок — `rbc_news.json` поруч із тим самим ноутбуком.

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

Розбір змін — [урок 38 у книзі курсу](https://nikoriakviktor.github.io/PY-Course-Victor-Nikoriak-11-11-2026/modules/m4/lesson_38/).
