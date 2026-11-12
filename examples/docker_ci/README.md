# Docker, Compose, сервер і CI — приклади

Маленький FastAPI-застосунок (`app/main.py`) і все, що навколо нього: варіанти `Dockerfile`, стек Compose з nginx і TLS,
вимірювання воркерів, приклад workflow GitHub Actions і BFF. Розбір — Частина X книги («Docker, Compose і CI/CD»).

```text
app/
  main.py                    /health, /whoami, /io, /cpu, /job, /visits
  requirements.txt           залежності роботи (в образ)
  requirements-dev.txt       тести й scripts/load.py (не в образ)
  test_main.py               pytest
  Dockerfile                 slim, шари, користувач без root, exec-форма, HEALTHCHECK
  Dockerfile.naive           як не треба: повний образ, root, shell-форма
  Dockerfile.alpine          те саме на Alpine
  Dockerfile.multistage      компілятор лише в етапі builder
  Dockerfile.entrypoint      ENTRYPOINT-скрипт + CMD (entrypoint.sh / entrypoint-noexec.sh)
compose/
  compose.yaml               api + Redis + nginx (TLS), дві мережі, том, профіль tools
  compose.override.yaml      розробка: порти на 127.0.0.1 (підхоплюється автоматично)
  compose.prod.yaml          сервер: restart, stop_grace_period, ротація журналів
  nginx.conf, make_cert.sh   TLS із самопідписаним сертифікатом
scripts/load.py              N одночасних запитів: час і кількість процесів
workflows/ci.yml             приклад CI/CD (не запускається: лежить не в .github/workflows/)
workflows/broken.yml         чотири помилки для actionlint
bff/bff_demo.py              BFF: послідовно, gather, тайм-аут і запасна відповідь
ruff.toml                    src = ["app"]: main — свій модуль для ruff
```

## Образ

```bash
cd app
docker build -t part10-slim .
docker run --rm -p 127.0.0.1:18110:8000 part10-slim
curl 127.0.0.1:18110/whoami

docker build -f Dockerfile.naive -t part10-naive .
docker build -f Dockerfile.alpine -t part10-alpine .
docker build -f Dockerfile.multistage -t part10-multi .
docker build -f Dockerfile.multistage --target builder -t part10-builder .
docker image ls | grep part10

docker build -f Dockerfile.entrypoint -t part10-ep-exec .            # FROM part10-slim
docker build -f Dockerfile.entrypoint --build-arg SCRIPT=entrypoint-noexec.sh -t part10-ep-noexec .
```

## Compose

```bash
cd compose
cp .env.example .env && sh make_cert.sh
docker compose up -d --build --wait
curl -k https://localhost:18112/whoami
docker compose --profile tools run --rm redis-cli
docker compose -f compose.yaml -f compose.prod.yaml config     # що вийде на сервері
docker compose down -v
```

Мережа `edge` — `10.231.7.0/24`. Якщо вона зайнята на твоїй машині, зміни підмережу, адресу nginx і `FORWARDED_ALLOW_IPS`.

## Воркери

```bash
pip install -r app/requirements.txt -r app/requirements-dev.txt
docker run -d --name part10-w4 --cpus 4 -p 127.0.0.1:18110:8000 part10-slim \
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
python scripts/load.py "http://127.0.0.1:18110/io?seconds=0.5" 200
python scripts/load.py "http://127.0.0.1:18110/cpu?rounds=1000000" 32
docker stop -t 10 part10-w4 && docker rm part10-w4
```

## Тести, workflow, BFF

```bash
cd app && pytest -q                       # з REDIS_URL — і з Redis
actionlint workflows/ci.yml               # 0 помилок
actionlint workflows/broken.yml           # 4 помилки
python bff/bff_demo.py                    # потрібні fastapi і httpx
```
