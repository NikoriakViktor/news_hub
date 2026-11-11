# Стан кроків — локальна перевірка

Дата: 2026-11-11. Python 3.12.3 (WSL2), `pytest -q` у папці кроку (`pytest.ini`: `-m "not llm and not docker"`).
Кожен крок 01–09 — в окремому чистому venv лише з його `requirements.txt` (+ `pytest pytest-asyncio fakeredis`,
як у `steps.yml`); 10–12 — `requirements-dev.txt`. `examples/meteo_api` — окремий venv з його `requirements.txt`.

| Папка | Результат |
|---|---|
| `steps/01_typing_pydantic` | passed — 12 |
| `steps/02_fastapi_basics` | passed — 23 |
| `steps/03_sqlalchemy_alembic` | passed — 32 |
| `steps/04_middleware_redis` | passed — 41 |
| `steps/05_api_testing` | passed — 86 |
| `steps/06_ai_dev_tools` | passed — 107 |
| `steps/07_llm_api` | passed — 168 (2 deselected: `llm`) |
| `steps/08_security` | passed — 279 (2 deselected); див. примітку |
| `steps/09_telegram_bot` | passed — 335 (2 deselected); див. примітку |
| `steps/10_docker` | passed — 340 (8 deselected: `llm`, `docker`) |
| `steps/11_compose_deploy` | passed — 343 (8 deselected) |
| `steps/12_ci_cd` | passed — 343 (8 deselected) |
| `examples/meteo_api` | passed — 7 |

Не запускалось локально: `pytest -m docker`, `scripts/smoke.sh`, PostgreSQL-прогін, `mypy --strict`,
`uv --resolution lowest-direct` — це робить `news_hub.yml` у CI.

## Примітка: рідкісне падіння в кроках 08–09

У ~2 з 40 прогонів упав один тест (`test_scrape_job_is_not_an_analyze_job`: `KeyError: 'job_id'` — відповідь
не `202`). Повторити 27 прогонами не вдалося. Найімовірніша причина — стрибок годинника WSL (того ж дня `tar`
показав зсув на 38 с): PyJWT перевіряє `iat`, і токен «з майбутнього» дає `401`. На раннерах GitHub такого
нема; якщо падіння з'явиться в CI — розібрати окремо.
