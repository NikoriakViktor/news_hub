# Коди відповідей News Hub

Які коди повертає фінальна версія API (`steps/12_ci_cd`) і коли саме. Зібрано з коду
([`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/news_hub/api.py),
`security.py`, `middleware.py`, `webhooks.py`), OpenAPI-схеми застосунку і запуску через `TestClient`.
Що означає кожен клас кодів загалом — [Коди відповідей](../01_http_and_rest/status_codes.md).

## Коди { #codes }

| Код | Коли в News Hub | Хто відповідає | Заголовки |
|---|---|---|---|
| `200 OK` | читання, `POST /api/scrape`, `POST /api/news/{id}/analyze`, вхід, `fetch` джерела, Telegram webhook; повтор доставки webhook (той самий `X-Webhook-Delivery`) — з тим самим завданням | ендпоінт | `X-Cache: HIT/MISS` — на `GET /api/news` і `/api/news/stats` |
| `201 Created` | `POST /api/news`, `POST /api/sources` | `status_code=` у декораторі | — |
| `202 Accepted` | `POST /api/scrape/jobs`, `POST /api/analyze/jobs`, `POST /api/webhooks/scrape` — задача прийнята, відповідь з `job_id` | `status_code=` у декораторі | — |
| `204 No Content` | `DELETE /api/news/{id}`, `DELETE /api/sources/{id}` | `Response(status_code=204)` | — |
| `307 Temporary Redirect` | шлях з `/` у кінці: `/api/news/` → `/api/news` | Starlette (`redirect_slashes`) | `Location` |
| `400 Bad Request` | заборонена адреса RSS-джерела (схема, порт, логін в URL, не публічна IP; і після перенаправлень); тіло Telegram webhook — не update | `unsafe()`, `telegram_webhook` | — |
| `401 Unauthorized` | немає токена, він недійсний чи прострочений; неправильний логін або пароль; webhook без підпису, з чужим підписом, застарілий, без `X-Webhook-Delivery` чи з неправильним id; неправильний секрет Telegram | `require_admin`, `admin_token`, `verify_signature`, `telegram_webhook` | `WWW-Authenticate: Bearer` — для токена |
| `403 Forbidden` | токен справжній, але роль не `admin` | `require_admin` | — |
| `404 Not Found` | новини, джерела чи задачі (зокрема задачі, старшої за добу) немає; невідомий шлях; `/docs`, `/redoc`, `/openapi.json` при `DOCS_ENABLED=false` (у Compose — за замовчуванням) | `get_news_or_404`, `get_source_or_404`, `get_*_job`; маршрутизатор | — |
| `405 Method Not Allowed` | метод, якого в шляху немає: `PUT /api/news/1` | маршрутизатор | `Allow` |
| `409 Conflict` | новина чи джерело з таким `url` уже є (`IntegrityError`); доставка webhook з цим id ще обробляється (рідка гонка: id зайнято, завдання ще не створене) | `create_news`, `create_source`, `scrape_webhook` | — |
| `422 Unprocessable Content` | параметри й тіло не пройшли перевірку; `pages` не з rbc.ua; `null` у `PATCH`; тіло `POST /api/news` не пройшло `NewsItem`; тіло webhook не `ScrapeRequest` | FastAPI; ручні `HTTPException(422, ...)` | — |
| `429 Too Many Requests` | ліміт: збір — `RATE_LIMIT_REQUESTS` за `RATE_LIMIT_WINDOW`, аналіз — `ANALYZE_RATE_LIMIT`, вхід — `LOGIN_RATE_LIMIT` за `LOGIN_RATE_WINDOW` з однієї адреси; вхід під одним іменем — `LOGIN_FAIL_LIMIT` невдалих за `LOGIN_FAIL_WINDOW` з усіх адрес | middleware `rate_limit`; `LoginGuard` в `admin_token` | `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining` |
| `500 Internal Server Error` | необроблений виняток; невдалий `COMMIT` (саме `500`, не `201` — завдяки `scope="function"`); відповідь не пройшла `response_model` | FastAPI / Starlette | — |
| `502 Bad Gateway` | провайдер LLM не відповів або відповідь не пройшла схему; RSS-джерело недоступне, завелике чи не RSS | `llm_error_handler`, `fetch_source` | — |
| `503 Service Unavailable` | база чи Redis недоступні (`/health/ready`); адмін-доступ не налаштовано; LLM не налаштовано; breaker відкритий; webhook вимкнено; бот вимкнений чи в режимі polling | `ready`, `get_admin_settings`, `get_llm_client`, `llm_error_handler`, `get_webhook_secret`, `telegram_webhook` | `Retry-After` — коли breaker відкритий |

Перед API стоїть nginx (`nginx/nginx.conf`, крок 11): він сам відповідає `200 ok` на `/nginx-health`, `413` на
тіло більше за `client_max_body_size 1m` і `502`, якщо `api` ще не готовий
([Порядок запуску](../tutorials/11_compose_deploy/startup_order.md)).

## Перевірено запуском { #run }

Скрипт у тимчасовій папці запускає `news_hub.api:app` кроку 12 (SQLite, fakeredis, налаштований адмін, без LLM,
webhook і бота):

```text
GET /health/ready                        200   {"status":"ok","checks":{"database":"ok","redis":"ok"}}
POST /api/scrape без токена              401 Bearer  {"detail":"потрібен токен: Authorization: Bearer <access_token>"}
POST /api/scrape недійсний токен         401 Bearer  {"detail":"недійсний токен"}
POST /api/scrape snapshot                200   {"source":"snapshot","mode":"async","total_time":0.0,"pages":[],"news_found":168,…
POST /api/scrape pages=чужий хост        422   {"detail":[{"type":"value_error","loc":["body","pages"],"msg":"Value error, сервер заванта…
GET /api/news/999                        404   {"detail":"новини 999 немає"}
GET /api/news/abc                        422   {"detail":[{"type":"int_parsing","loc":["path","news_id"],"msg":"Input should be a valid i…
GET /api/news/ (слеш)                    307
PUT /api/news/1                          405   {"detail":"Method Not Allowed"}
POST /api/news дублікат url              409   {"detail":"новина з url https://www.rbc.ua/rus/news/…
PATCH title=null                         422   {"detail":[{"type":"value_error","loc":["body","title"],"msg":"Value error, поле не може б…
DELETE /api/news/{id}                    204
POST /api/scrape/jobs                    202   {"job_id":"10ea3549f1f4","kind":"scrape","status":"queued","source":"snapshot",…
POST /api/news/1/analyze без LLM         503   {"detail":"LLM не налаштовано: задай GEMINI_API_KEY (або LLM_PROVIDER=anthropic + ANTHROPI…
POST /api/sources 127.0.0.1              400   {"detail":"заборонена адреса: адреса 127.0.0.1 — loopback: сервер туди не звертається"}
POST /api/webhooks/scrape без секрету    503   {"detail":"webhook вимкнено: задай WEBHOOK_SECRET"}
POST /api/telegram/webhook               503   {"detail":"бот вимкнений або працює через polling"}
6-та спроба входу                        429  300 {"detail":"забагато запитів: 5 за 300 с; спробуй через 300 с"}
```

Ліміт входу рахує **всі** спроби, і вдалі теж: тут перша спроба була вдалою, тож шоста — `429`.

Друге проганяння — з `WEBHOOK_SECRET` (той самий крок 12, SQLite, fakeredis). Повтор webhook, лічильник входу
за ім'ям і заголовки безпеки:

```text
webhook, нова доставка                   202  {"job_id":"aaad7d8b273a","kind":"scrape","status":"queued","source":"snapshot","mode":"asy
webhook, та сама доставка, новий підпис  200  {"job_id":"aaad7d8b273a","kind":"scrape","status":"done","source":"snapshot","mode":"async
   той самий job_id: True
webhook без X-Webhook-Delivery           401  {"detail":"X-Webhook-Delivery: 8–64 символи A-Z a-z 0-9 _ -"}
webhook, X-Webhook-Delivery=abc          401  {"detail":"X-Webhook-Delivery: 8–64 символи A-Z a-z 0-9 _ -"}
6-та спроба входу з однієї адреси        429 300 {"detail":"забагато запитів: 5 за 300 с; спробуй через 300 с"}
   ще 15 невдалих (разом 20): [401]
правильний пароль після 20 невдач        429 900 {"detail":"забагато невдалих входів під цим іменем; спробуй через 900 с"}
інше ім'я                                401  {"detail":"неправильне ім'я або пароль"}
заголовки /api/news: {'x-content-type-options': 'nosniff', 'x-frame-options': 'DENY', 'referrer-policy': 'no-referrer', 'cross-origin-opener-policy': 'same-origin', 'content-security-policy': "default-src 'none'; frame-ancestors 'none'"}
/docs: 200 CSP: None | X-Frame-Options: DENY
```

- Перед «ще 15 невдалих» скрипт знімає ліміт за адресою (`LIMITS["login"] = (1000, 300)`) — так виглядає атака з
  багатьох адрес. Шоста спроба, відбита middleware, до `admin_token` не дійшла й невдачею під іменем не рахується:
  п'ять до неї плюс п'ятнадцять — двадцять.
- Після межі навіть правильний пароль отримує `429`, а інше ім'я — далі звичайний `401`.
- Раніше повтор тієї самої доставки з новим підписом запускав збір удруге, а `409` отримувала лише байт-у-байт
  копія ([було → стало](../08_security/webhooks_and_signatures.md#news-hub-replay)).

## За ендпоінтами { #endpoints }

Колонка «OpenAPI» — що видно в `/docs` (`app.openapi()`); «ще» — коди, які дає код, але схема їх не описує:
`AdminDep` (`401`, `403`, `503`), middleware (`429`), ручні `HTTPException`.

| Метод і шлях | OpenAPI | Ще | Адмін |
|---|---|---|---|
| `GET /health` | 200 | — | — |
| `GET /health/ready` | 200, 503 | — | — |
| `GET /api/news` | 200, 422 | — | — |
| `DELETE /api/news` | 200 | 401, 403, 503 | так |
| `POST /api/news` | 201, 409, 422 | 401, 403, 503 | так |
| `GET /api/news/search` | 200, 422 | — | — |
| `GET /api/news/count` | 200 | — | — |
| `GET /api/news/stats` | 200 | — | — |
| `GET /api/news/{news_id}` | 200, 404, 422 | — | — |
| `PATCH /api/news/{news_id}` | 200, 404, 422 | 401, 403, 503 | так |
| `DELETE /api/news/{news_id}` | 204, 404, 422 | 401, 403, 503 | так |
| `POST /api/scrape` | 200, 422 | 401, 403, 429, 503 | так |
| `POST /api/scrape/jobs` | 202, 422 | 401, 403, 429, 503 | так |
| `GET /api/scrape/jobs/{job_id}` | 200, 404, 422 | 401, 403, 503 | так |
| `POST /api/news/{news_id}/analyze` | 200, 404, 422, 502, 503 | 401, 403, 429 | так |
| `POST /api/analyze/jobs` | 202, 422 | 401, 403, 429, 503 | так |
| `GET /api/analyze/jobs/{job_id}` | 200, 404, 422 | 401, 403, 503 | так |
| `POST /api/admin/token` | 200, 401, 422, 429 | 503 | — |
| `GET /api/sources` | 200 | 401, 403, 503 | так |
| `POST /api/sources` | 201, 400, 409, 422 | 401, 403, 503 | так |
| `DELETE /api/sources/{source_id}` | 204, 422 | 401, 403, 404, 503 | так |
| `POST /api/sources/{source_id}/fetch` | 200, 400, 422, 502 | 401, 403, 404, 503 | так |
| `POST /api/webhooks/scrape` | 200, 202, 401, 409 | 422, 503 | підпис HMAC |
| `POST /api/telegram/webhook` | 200, 401, 503 | 400 | секрет Telegram |

`POST /api/analyze/jobs` моделі не викликає: аналіз іде після відповіді, і збої провайдера потрапляють у
статус задачі (`GET /api/analyze/jobs/{job_id}`), а не в код відповіді.

## Як перевірити самому { #check }

```bash
cd steps/12_ci_cd
python -c "from news_hub.api import app
for p, ops in app.openapi()['paths'].items():
    for m, o in ops.items(): print(m.upper(), p, sorted(o['responses']))"
grep -n "HTTPException(\|status_code=" news_hub/*.py
```

Де розібрано: `401`/`403` — [Адмін і JWT](../tutorials/08_security/admin_jwt.md); `409`, `204` —
[CRUD](../tutorials/03_sqlalchemy_alembic/crud.md); `429` — [Rate limit](../tutorials/04_middleware_redis/rate_limit.md);
`202` — [Фоновий збір](../tutorials/04_middleware_redis/background_jobs.md); `502`/`503` LLM —
[Circuit breaker](../tutorials/07_llm_api/circuit_breaker.md); `400` SSRF — [SSRF](../tutorials/08_security/ssrf.md);
webhook — [Підписані webhook](../tutorials/08_security/webhooks.md); `/health/ready` —
[Здоров'я і зупинка](../tutorials/10_docker/health_shutdown.md); `500` замість `201` —
[Сесія на запит](../tutorials/03_sqlalchemy_alembic/session_per_request.md#result).
