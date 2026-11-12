# Базовий образ прикладу: slim, залежності окремим шаром, користувач без root, exec-форма CMD.
#   docker build -t part10-slim .
#   docker run --rm -p 127.0.0.1:18110:8000 part10-slim
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# 1. залежності — рідко змінюються, шар кешується
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. користувач без root, фіксований UID
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

# 3. код — останнім, власник root: app не може його переписати
COPY . .
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# exec-форма: PID 1 — uvicorn, SIGTERM від `docker stop` дістається йому
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
