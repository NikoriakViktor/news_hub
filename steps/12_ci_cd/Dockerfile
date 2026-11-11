# news_hub в контейнері. Урок 48.
# Основа — Dockerfile стартового production_bot:
# python:3.12-slim, залежності окремим шаром, користувач без root. Що додано і чому — docs/modules/m5/lesson_48.md.
#
#   docker build -t news_hub:48 .
#   docker run --rm -v news_data:/data news_hub:48 alembic upgrade head          # схема бази на томі
#   docker run -d -p 8000:8000 -v news_data:/data --env-file .env news_hub:48    # повна інструкція — README

FROM python:3.12-slim

# Python у контейнері: .pyc не пишемо (файлова система образу — лише для читання користувачем app),
# stdout без буфера (print одразу в `docker logs`), pip без перевірки нової версії й без попередження
# «pip від root» (у контейнері це нормально: окремого системного Python, який можна зламати, тут немає).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# 1. Залежності — окремий шар: він перезбирається, лише коли змінився requirements.txt.
#    Тут лише залежності роботи; pytest, mypy, fakeredis — requirements-dev.txt, в образ не йдуть.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Користувач без root: зламаний процес не отримає root у контейнері.
#    Фіксований UID — щоб права на томі збігались між перезбираннями й машинами.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir /data && chown app /data

# 3. Код — останнім: змінюється найчастіше. Власник — root, тож app не може переписати код.
#    Що НЕ копіюється (.env, .venv, tests, …) — .dockerignore.
COPY . .

USER app

# SQLite за замовчуванням — на томі /data (у /app користувач app писати не може, і дані б зникли разом
# з контейнером). PostgreSQL і Redis — через змінні середовища під час запуску, не в образі.
ENV DATABASE_URL=sqlite+aiosqlite:////data/news_hub.db

EXPOSE 8000

# «Процес живий?» — python з образу, бо curl у slim немає. /health не торкається бази (див. api.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# exec-форма (JSON-масив): uvicorn стає PID 1 і сам отримує SIGTERM від `docker stop` → коректна зупинка.
# Кількість процесів — змінна WEB_CONCURRENCY (uvicorn читає її сам), за замовчуванням 1:
# у контейнері масштабуємо кількістю контейнерів (урок 49), а не --workers усередині.
CMD ["uvicorn", "news_hub.api:app", "--host", "0.0.0.0", "--port", "8000"]
