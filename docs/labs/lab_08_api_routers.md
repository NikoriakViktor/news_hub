# Лаба 8. `api.py` → `APIRouter` { #lab-08 }

| | |
|---|---|
| Основа | [крок 12](../tutorials/12_ci_cd/index.md) — `steps/12_ci_cd` |
| Що тренує | рефакторинг без зміни поведінки, `APIRouter` і `include_router`, характеризаційний тест (знімок OpenAPI), цикли імпортів, `dependency_overrides` після перенесення коду |
| Складність | ★★★ |
| Орієнтовний час | 3–4 години |

## Мета { #goal }

**Задача.** У кроці 12 [`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/news_hub/api.py)
займає 816 рядків. У ньому lifespan, middleware, перемикач `/docs`, 16 залежностей, 13 моделей запитів і відповідей і 24 операції
(метод + шлях) семи тегів. Щоб знайти один ендпоінт, треба гортати весь файл, а дві зміни в різних тегах дають
конфлікт у тому самому файлі.

**Зміна.** Розкласти ендпоінти на `news_hub/routers/<тег>.py`: один модуль на тег OpenAPI, у кожному
`router = APIRouter()`. Залежності винести в `deps.py`, моделі — в `schemas.py`. В `api.py` лишається лише складання
застосунку.

**Результат.** Для клієнта API не змінилось нічого. Шляхи, методи, параметри, відповіді й `operationId` збігаються зі
знімком, знятим **до** рефакторингу. Тести кроку 12 зелені, `mypy --strict` чистий.

**Правило.** Рефакторинг не змінює поведінку, і це доводять тести, а не відчуття. Тому спершу пишеться тест, який
фіксує поточну поведінку (знімок OpenAPI), а вже потім переноситься код. Також варто перевірити, що тести, які
перебирають ендпоінти, після перенесення бачать їх стільки ж, скільки до нього.

## Звідки починаємо { #start }

```bash
cp -r steps/12_ci_cd lab_08 && cd lab_08
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

```text
363 passed, 8 deselected
```

**Перший крок, до будь-яких змін коду:** зніми знімок OpenAPI.

```bash
python -c "import json; from news_hub.api import app; s = app.openapi(); print(json.dumps({'paths': s['paths'], \
'schemas': sorted(s['components']['schemas'])}, ensure_ascii=False, indent=1, sort_keys=True))" > tests/openapi_snapshot.json
```

У знімку зберігаються `paths` і **назви** схем, але не вміст схем. Вміст трохи залежить від версій FastAPI і Pydantic:
з мінімальними версіями (job `min-versions`) у `ValidationError` немає полів `ctx`/`input`, а в `TokenResponse`
з'являється `enum`. Повний знімок падав би там без жодної зміни в коді. А `paths` і список назв схем збігаються на
обох наборах версій (перевірено: FastAPI 0.162.4 і 0.121.0).

## Вимоги { #requirements }

1. Пакет `news_hub/routers/` з модулями `system`, `news`, `scrape`, `analyze`, `admin`, `webhooks`, `telegram`. У
   кожному — `router = APIRouter()` з ендпоінтами **лише свого** тегу.
2. `news_hub/deps.py` — залежності (`SessionDep`, `RepoDep`, `get_scrapers`, `get_session_factory`, `get_llm_client`,
   `get_fetch_policy`, …). `news_hub/schemas.py` — моделі запитів і відповідей. Роутери **не** імпортують `api.py`.
3. `api.py`: docstring, lifespan і реєстрація бота, `docs_enabled()` і `app = FastAPI(...)`, middleware **у тому самому
   порядку**, обробник `LLMError`, `include_router` для кожного роутера. Жодного `@app.get/post/...`, менше 250 рядків.
4. Тести підміняють залежності, імпортуючи їх з `news_hub.api`
   (`from news_hub.api import app, docs_enabled, get_scrapers, get_session_factory, …`). Ці імпорти мають працювати й
   далі: `api.py` реекспортує ці функції (`__all__`). `monkeypatch.setattr("news_hub.api.TELEGRAM_RETRY_DELAYS", …)` теж має
   працювати, тож `register_bot` лишається в `api.py`.
5. Шляхи `/api/news/search`, `/count`, `/stats` зареєстровано **до** `/api/news/{news_id}`.
6. Знімок OpenAPI збігається. `pytest -q` і `mypy --strict news_hub` зелені.

## Критерії приймання { #acceptance }

```python title="tests/integration/test_routers.py"
"""Лаба 8: api.py розкладено на APIRouter — а для клієнта не змінилось нічого.

tests/openapi_snapshot.json знято ДО рефакторингу (шляхи й назви схем: їх не змінює версія FastAPI чи Pydantic,
а от вміст схем — трохи змінює, і job min-versions порівнював би не те):
    python -c "import json; from news_hub.api import app; s = app.openapi(); print(json.dumps({'paths': s['paths'], \
    'schemas': sorted(s['components']['schemas'])}, ensure_ascii=False, indent=1, sort_keys=True))" > tests/openapi_snapshot.json
"""
import ast
import importlib
import json
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute

from news_hub.api import app

from .test_admin_api import api_routes, endpoints

PACKAGE = Path(__file__).resolve().parents[2] / "news_hub"
SNAPSHOT = Path(__file__).resolve().parents[1] / "openapi_snapshot.json"
ROUTERS = {"system": "system", "news": "news", "scrape": "scrape", "analyze": "analyze",
           "admin": "admin", "webhooks": "webhooks", "telegram": "telegram"}        # модуль → тег


def test_openapi_is_the_same_as_before() -> None:
    before = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    schema = app.openapi()
    assert schema["paths"] == before["paths"]                       # шляхи, методи, параметри, відповіді, operationId
    assert sorted(schema["components"]["schemas"]) == before["schemas"]


@pytest.mark.parametrize(("module", "tag"), sorted(ROUTERS.items()))
def test_each_tag_lives_in_its_own_router(module: str, tag: str) -> None:
    router = getattr(importlib.import_module(f"news_hub.routers.{module}"), "router", None)
    assert isinstance(router, APIRouter), f"news_hub/routers/{module}.py: немає router = APIRouter(...)"
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert routes, f"router у {module}.py порожній"
    assert {tag} == {t for route in routes for t in route.tags}, f"у {module}.py — ендпоінти з чужим тегом"


def test_api_py_only_assembles_the_app() -> None:
    tree = ast.parse((PACKAGE / "api.py").read_text(encoding="utf-8"))
    routes = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
              for deco in node.decorator_list
              if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
              and deco.func.attr in {"get", "post", "put", "patch", "delete"}]
    assert routes == [], f"ендпоінти досі в api.py: {routes}"
    assert len((PACKAGE / "api.py").read_text(encoding="utf-8").splitlines()) < 250


def test_static_news_paths_come_before_news_id() -> None:
    paths = [route.path for route in api_routes(app.routes)]
    first_param = paths.index("/api/news/{news_id}")
    for path in ("/api/news/search", "/api/news/count", "/api/news/stats"):
        assert paths.index(path) < first_param, f"{path} після /api/news/{{news_id}}: потрапить у news_id"


def test_security_test_still_sees_every_endpoint() -> None:
    """Порожній список ендпоінтів зробив би тести доступу (test_admin_api.py) зеленими й марними."""
    operations = {(method.upper(), path) for path, item in app.openapi()["paths"].items() for method in item}
    assert {(method, path) for method, path, _ in endpoints()} == operations
```

Тест бере `api_routes` і `endpoints` з `tests/integration/test_admin_api.py`. Обхід маршрутів там треба змінити
**одночасно** з тестом: чому — у розділі [«Пастка: тест доступу, що перестав щось перевіряти»](#trap).

```diff title="tests/integration/test_admin_api.py"
+from collections.abc import Iterator, Sequence
 from datetime import datetime, timedelta, timezone
 ...
 from fastapi.testclient import TestClient
+from starlette.routing import BaseRoute
 ...
+def api_routes(routes: Sequence[BaseRoute]) -> Iterator[APIRoute]:
+    """Усі APIRoute застосунку, і з підключених роутерів теж (префіксів у news_hub немає).
+
+    Старіші FastAPI копіюють маршрути роутера в app.routes; новіші (0.16x) кладуть туди обгортку з
+    original_router — без обходу вкладених роутерів цей тест не бачив би жодного ендпоінта.
+    """
+    for route in routes:
+        if isinstance(route, APIRoute):
+            yield route
+        elif (router := getattr(route, "original_router", None)) is not None:
+            yield from api_routes(router.routes)
+
+
 def endpoints() -> list[tuple[str, str, APIRoute]]:
-    return [(method, route.path, route) for route in app.routes if isinstance(route, APIRoute)
-            for method in sorted(route.methods)]
+    return [(method, route.path, route) for route in api_routes(app.routes) for method in sorted(route.methods)]
```

**До рефакторингу** (знімок знято, обхід маршрутів оновлено, `api.py` ще не чіпали):

```text
$ pytest -q
FAILED tests/integration/test_routers.py::test_each_tag_lives_in_its_own_router[admin-admin]
FAILED tests/integration/test_routers.py::test_each_tag_lives_in_its_own_router[analyze-analyze]
FAILED tests/integration/test_routers.py::test_each_tag_lives_in_its_own_router[news-news]
FAILED tests/integration/test_routers.py::test_each_tag_lives_in_its_own_router[scrape-scrape]
FAILED tests/integration/test_routers.py::test_each_tag_lives_in_its_own_router[system-system]
FAILED tests/integration/test_routers.py::test_each_tag_lives_in_its_own_router[telegram-telegram]
FAILED tests/integration/test_routers.py::test_each_tag_lives_in_its_own_router[webhooks-webhooks]
FAILED tests/integration/test_routers.py::test_api_py_only_assembles_the_app
8 failed, 366 passed, 8 deselected
```

Сім тестів падають з `ModuleNotFoundError: No module named 'news_hub.routers'`, восьмий — з
`AssertionError: ендпоінти досі в api.py: ['health', 'ready', 'list_news', 'search_news', …]`. Знімок, порядок шляхів і повнота
`endpoints()` зелені вже зараз, і так має бути: вони фіксують поведінку, яку рефакторинг не повинен змінити.

**Після рефакторингу:**

```text
$ pytest -q
374 passed, 8 deselected
$ mypy --strict news_hub
Success: no issues found in 36 source files
```

Ті самі тести з мінімальними версіями залежностей, як у job `min-versions`
(`uv venv --python 3.10`, `uv pip install --resolution lowest-direct -r requirements-dev.txt`, FastAPI 0.121.0):

```text
374 passed, 8 deselected, 30 warnings
```

### Пастка: тест доступу, що перестав щось перевіряти { #trap }

Зроби рефакторинг, але **не** змінюй `endpoints()` у `test_admin_api.py`:

```text
$ pytest -q tests/integration/test_admin_api.py -rs
E       AssertionError: assert set() == {('GET', '/ap...health'), ...}
SKIPPED [1] tests/integration/test_admin_api.py:46: got empty parameter set for (method, path)
1 failed, 21 passed, 1 skipped
```

До рефакторингу в цьому файлі було `36 passed`. Тепер 14 перевірок «анонім отримує `401` на кожному ендпоінті запису»
не впали, а **зникли**: `parametrize` отримав порожній список і перетворився на один `SKIPPED`. Причина в FastAPI 0.16x.
`include_router` більше не копіює маршрути роутера в `app.routes`, а додає обгортку (`_IncludedRouter` з полем
`original_router`). `isinstance(route, APIRoute)` по `app.routes` тепер не знаходить жодного ендпоінта.

Тут допоміг сусідній тест `test_every_other_endpoint_requires_admin`: він порівнює множину з `PUBLIC` і тому впав.
Якби його не було, ти побачив би зелений прогін з одним `skipped`, тобто ознаку, яку легко пропустити.
`test_security_test_still_sees_every_endpoint` закриває цю дірку явно. Він звіряє `endpoints()` з OpenAPI, і порожній
список більше не пройде непомітно.

## Підказки { #hints }

??? tip "З чого почати, щоб не отримати цикл імпортів"
    Роутерам потрібні залежності (`RepoDep`, `AdminDep`), а `api.py` потрібні роутери. Якщо залежності лишаться в
    `api.py`, то `api → routers.news → api`, і імпорт впаде з `ImportError: cannot import name … (most likely due to a
    circular import)`. Тому першими переносяться `deps.py` і `schemas.py`, вони не імпортують ні `api`, ні `routers`.
    Потім роутери, по одному. Після кожного запускай `pytest -q`.

??? tip "`dependency_overrides` після перенесення"
    Ключ у `app.dependency_overrides` — **об'єкт функції**. Тест робить `from news_hub.api import get_scrapers`, а
    роутер `from ..deps import get_scrapers`. Це той самий об'єкт, тож підміна працює. Якщо скопіювати функцію замість
    перенесення, буде два різні об'єкти: тести почнуть ходити в справжній сайт і справжню базу. `__all__` в `api.py` фіксує, що
    саме з нього імпортують ззовні. Без нього `mypy --strict` на коді, який робить `from news_hub.api import get_scrapers`,
    скаржиться: `Module "news_hub.api" does not explicitly export attribute "get_scrapers"`.

??? tip "Теги: у декораторі чи в `APIRouter(tags=[...])`?"
    Найпростіше лишити `tags=["news"]` у кожному декораторі, як було: тоді знімок OpenAPI збігається байт у байт. Якщо
    задати ще й `APIRouter(tags=["news"])`, FastAPI додасть тег удруге, `"tags": ["news", "news"]`, і знімок це
    покаже.

??? tip "Middleware не переносять у роутери"
    Middleware належать застосунку, а не роутеру: `APIRouter` їх не має. Рядки реєстрації лишаються в `api.py` без змін і
    в тому самому порядку. `SecurityHeadersMiddleware` — чистий ASGI-клас (`app.add_middleware`), а не ще один
    `@app.middleware("http")`: додатковий шар `BaseHTTPMiddleware` змінював момент, коли завершуються фонові задачі
    відносно відповіді, і тести фонового аналізу почали іноді падати (3 з 20 прогонів інтеграційних тестів кроку 8). Порядок і заголовки перевіряють
    `test_security_headers_on_every_answer` і `test_docs_enabled` у `test_admin_api.py`.

??? tip "Що лишається в `api.py`"
    lifespan, `start_bot`, `register_bot` разом із `TELEGRAM_RETRY_DELAYS` (тест підміняє його саме в
    `news_hub.api`), `docs_enabled()` (тест імпортує його з `news_hub.api`) і `app = FastAPI(...)` з `openapi_tags` і
    `docs_url`/`redoc_url`/`openapi_url`, три `app.middleware("http")` і `app.add_middleware(SecurityHeadersMiddleware)` у
    тому самому порядку, `@app.exception_handler(LLMError)` і цикл `include_router`. `uvicorn news_hub.api:app` у `Dockerfile` і Compose не змінюється.

## Підхід до розв'язку { #solution }

??? success "Підхід до розв'язку"

    Структура після рефакторингу (рядків у файлі):

    ```text
    news_hub/api.py              193   застосунок: lifespan, docs_enabled, middleware, обробник LLMError, include_router
    news_hub/deps.py             106   усі Depends і Annotated-аліаси
    news_hub/schemas.py          129   NewsOut, NewsPatch, ScrapeRequest, …, SourceFetchReport
    news_hub/routers/system.py    38   /health, /health/ready
    news_hub/routers/news.py     119   /api/news… (список, пошук, count, stats, CRUD)
    news_hub/routers/scrape.py    58   /api/scrape, /api/scrape/jobs…, collect()
    news_hub/routers/analyze.py   53   /api/news/{news_id}/analyze, /api/analyze/jobs…
    news_hub/routers/admin.py    108   /api/admin/token (LoginGuard, bcrypt у пулі потоків), /api/sources…
    news_hub/routers/webhooks.py  56   /api/webhooks/scrape (claim_delivery; collect — зі scrape.py)
    news_hub/routers/telegram.py  31   /api/telegram/webhook
    ```

    Роутер — це той самий код, що був в `api.py`, лише `@app.` замінено на `@router.`:

    ```python title="news_hub/routers/scrape.py (початок)"
    """Збір новин: одразу або у фоні (тег scrape)."""
    from fastapi import APIRouter, BackgroundTasks, HTTPException, status

    from ..deps import NotifierDep, RedisDep, RepoDep, Scraper, ScrapersDep, SessionFactoryDep
    from ..jobs import JobStatus, JobStore, run_scrape_job
    from ..models import validate_news
    from ..schemas import ScrapeReport, ScrapeRequest
    from ..scraper import ScrapeOutcome
    from ..security import AdminDep
    from ..snapshot import load_snapshot

    router = APIRouter()


    async def collect(request: ScrapeRequest, scrapers: dict[str, Scraper]) -> ScrapeOutcome:
        """Знімок або сторінки сайту → сирі новини (спільне для POST /api/scrape і фонового збору)."""
        ...


    @router.post("/api/scrape", response_model=ScrapeReport, tags=["scrape"], summary="Зібрати новини",
                 dependencies=[AdminDep])
    async def scrape(request: ScrapeRequest, repo: RepoDep, scrapers: ScrapersDep, background: BackgroundTasks,
                     notifier: NotifierDep) -> ScrapeReport:
        ...
    ```

    Кінець `api.py`:

    ```python title="news_hub/api.py (імпорти й кінець файлу)"
    from .deps import get_fetch_policy, get_llm_client, get_scrapers, get_session_factory
    from .routers import admin, analyze, news, scrape, system, telegram, webhooks

    # Тести підміняють ці залежності через app.dependency_overrides і імпортують їх звідси.
    __all__ = ["app", "docs_enabled", "get_fetch_policy", "get_llm_client", "get_scrapers", "get_session_factory"]
    ...

    # Middleware: останній зареєстрований — зовнішній. Запит іде request_context → SecurityHeaders → rate_limit
    # → invalidate_cache → ендпоінт, відповідь — у зворотному порядку (тож і 429 отримує заголовки безпеки).
    app.middleware("http")(invalidate_cache)
    app.middleware("http")(rate_limit)
    app.add_middleware(SecurityHeadersMiddleware)
    app.middleware("http")(request_context)
    ...


    # Роутери — у порядку тегів у /docs. Порядок шляхів ВСЕРЕДИНІ news.router теж важливий (див. routers/news.py).
    for module in (system, news, scrape, analyze, admin, webhooks, telegram):
        app.include_router(module.router)
    ```

    Усередині `routers/news.py` порядок той самий, що був в `api.py`: список, `/search`, `/count`, `/stats`,
    `DELETE /api/news`, `POST /api/news`, далі `/{news_id}`. Між роутерами порядок не критичний: шляхи різних тегів не
    перетинаються. `/api/news/{news_id}/analyze` має на один сегмент більше, ніж `/api/news/{news_id}`.

## Що перевірити самому { #self-check }

- [ ] Знімок OpenAPI знято **до** першої зміни в `api.py`, і `git diff tests/openapi_snapshot.json` після рефакторингу
      порожній.
- [ ] `pytest -q` → `374 passed`, у `test_admin_api.py` знову `36 passed` і жодного `skipped`.
- [ ] `mypy --strict news_hub` чистий, а `python -c "import news_hub.api"` не падає з циклом імпортів.
- [ ] Перестав місцями `/api/news/search` і `/api/news/{news_id}` у `routers/news.py` і подивився, що впаде: тест
      порядку чи наявні тести пошуку. Потім повернув як було.
- [ ] Можеш пояснити, чому характеризаційний тест (знімок) пишуть **до** рефакторингу і чому в ньому лише `paths` і
      назви схем.
- [ ] Можеш пояснити, чому `get_scrapers` має бути **тим самим** об'єктом у `deps.py` і в `news_hub.api`.
- [ ] Відкрив `/docs`: теги й ендпоінти ті самі, у тому самому порядку тегів.
