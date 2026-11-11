# Структура репозиторію

```text
news_hub/
├── steps/                    ← 12 кроків; кожен — повний робочий проєкт
│   ├── 01_typing_pydantic/
│   ├── 02_fastapi_basics/
│   ├── …
│   └── 12_ci_cd/             ← фінальна версія
├── examples/
│   ├── meteo_api/            ← API метеостанцій: дизайн REST, gRPC для порівняння
│   ├── fastapi_vs_drf/       ← API нотаток на FastAPI — пара до DRF
│   └── fastapi_demo/         ← async чи blocking: виміри
├── docs/                     ← ця книга (MkDocs Material)
├── .github/workflows/
│   ├── steps.yml             ← pytest у кожному кроці
│   ├── news_hub.yml          ← повний CI фінального кроку
│   └── docs.yml              ← публікація книги
├── mkdocs.yml
└── requirements-docs.txt
```

## Папка кроку

Усередині кожного кроку — той самий каркас, який з кроку в крок обростає новими файлами:

```text
steps/NN_*/
├── news_hub/          ← пакет застосунку
├── tests/             ← тести кроку
├── data/              ← знімок стрічки rbc.ua (168 новин) — працює без мережі
├── requirements.txt
├── pytest.ini
└── README.md          ← що тут і як запустити
```

| З кроку | З'являється |
|---|---|
| 2 | `postman/` — колекція запитів з перевірками |
| 3 | `migrations/`, `alembic.ini`, `docker-compose.yml` |
| 5 | `.coveragerc`, поділ `tests/unit` і `tests/integration` |
| 6 | `CLAUDE.md`, `.claude/` — правила й hook для Claude Code |
| 10 | `Dockerfile`, `.dockerignore`, `requirements-dev.txt` |
| 11 | `nginx/`, `scripts/`, `.env.example`, `docker-compose.dev.yml` |

## Чому копії, а не гілки

Кожен крок — окрема папка, а не гілка чи тег. Так будь-який крок відкривається одразу, без `git checkout`,
два кроки видно поруч у редакторі, а CI перевіряє всі кроки одночасно (`steps.yml`).
Різницю між кроками показує `git diff --no-index` — див. [Як читати кроки](how_to_use.md#compare).
