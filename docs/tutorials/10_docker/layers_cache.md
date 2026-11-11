# Шари й кеш

> Крок 10 · розділ 2 з 4. Код: [`Dockerfile`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/10_docker/Dockerfile).
> Теорія: [Частина X. Docker, Compose і CI/CD](../../10_docker_and_ci/README.md).

## Задача { #task }

Змінили один рядок в одному `.py` і перезбираємо образ. Це має тривати секунди, а не стільки, скільки `pip install` усіх залежностей (у вимірах цього розділу — від 35 секунд до двох хвилин, залежно від мережі).

## Як Docker використовує кеш { #how }

Docker виконує `Dockerfile` згори донизу. Для кожної інструкції він перевіряє, чи є в кеші шар, зібраний з **тих самих вхідних даних** (та сама інструкція, ті самі файли для `COPY`) поверх **того самого** попереднього шару. Є — бере готовий (`CACHED`). Немає — виконує інструкцію, і кеш для **всіх наступних** інструкцій уже не використовується.

| Інструкція | Від чого залежить її кеш |
|---|---|
| `FROM python:3.12-slim` | який саме образ під цим тегом лежить локально |
| `ENV …`, `WORKDIR /app`, `USER app` | текст інструкції |
| `COPY requirements.txt .` | вміст `requirements.txt` |
| `RUN pip install …` | текст команди й попередній шар; **не** те, що зараз лежить на PyPI |
| `COPY . .` | вміст усіх файлів контексту, тобто все, що не відсіяв `.dockerignore` |

Тому порядок: від того, що змінюється рідко (базовий образ, залежності), до того, що змінюється щодня (код).

## Зміна: залежності — до коду { #change }

```dockerfile title="Dockerfile (фрагмент)"
WORKDIR /app

# 1. Залежності — окремий шар: він перезбирається, лише коли змінився requirements.txt.
#    Тут лише залежності роботи; pytest, mypy, fakeredis — requirements-dev.txt, в образ не йдуть.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Користувач без root …
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir /data && chown app /data

# 3. Код — останнім: змінюється найчастіше. Власник — root, тож app не може переписати код.
#    Що НЕ копіюється (.env, .venv, tests, …) — .dockerignore.
COPY . .
```

`--no-cache-dir` — щоб pip не зберігав завантажені пакети у своєму кеші всередині шару: в образі вони вже не потрібні, а місце займають.

Стартовий `Dockerfile` уже мав цей порядок — його лишаємо. Нове в кроці 10 — `.dockerignore`: кеші `**/__pycache__`, `.pytest_cache`, `.mypy_cache` змінюються після кожного запуску тестів, і без `.dockerignore` вони інвалідували б шар `COPY . .` навіть тоді, коли код не змінився. А `Dockerfile`, `.dockerignore`, `docker-compose*.yml` в `.dockerignore` — щоб правка самого `Dockerfile` не зачіпала шар коду.

## Результат: перезбирання після зміни одного файлу { #result }

Змінили один `.py` (дописали коментар у `news_hub/models.py`) і перезібрали:

```text
$ echo "# x" >> news_hub/models.py
$ time docker build --progress=plain -t news_hub:10 .
#6 [4/6] RUN pip install --no-cache-dir -r requirements.txt
#6 CACHED
#7 [2/6] WORKDIR /app
#7 CACHED
#8 [3/6] COPY requirements.txt .
#8 CACHED
#9 [5/6] RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app     && mkdir /data && chown app /data
#9 CACHED
#10 [6/6] COPY . .
#10 DONE 0.1s
real    0m1.654s
```

BuildKit друкує кроки не по порядку (`[4/6]` раніше за `[2/6]`): коли шар береться з кешу, чекати попереднього не треба. Важливо одне: усе до `COPY . .` — `CACHED`.

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph A1 ["правильний порядок: крок 1"]
        direction LR
        A1a["FROM python:3.12-slim"] --> A1b["образ той самий"] --> A1c["CACHED"]
    end
    subgraph A2 ["крок 2"]
        direction LR
        A2a["COPY requirements.txt"] --> A2b["файл не змінився"] --> A2c["CACHED"]
    end
    subgraph A3 ["крок 3"]
        direction LR
        A3a["RUN pip install"] --> A3b["попередній шар з кешу,<br>інструкція та сама"] --> A3c["CACHED"]
    end
    subgraph A4 ["крок 4"]
        direction LR
        A4a["RUN useradd"] --> A4b["попередній шар з кешу"] --> A4c["CACHED"]
    end
    subgraph A5 ["крок 5"]
        direction LR
        A5a["COPY . ."] --> A5b["змінився один .py"] --> A5c["виконати: 0.1 с"]
    end
    R1["перезбирання: 1.7 с"]
    A1 --> A2 --> A3 --> A4 --> A5 --> R1

    class A1a,A2a,A3a,A4a,A5a step
    class A1b,A2b,A3b,A4b,A5b decision
    class A1c,A2c,A3c,A4c success
    class A5c warning
    class R1 success
```

## А якщо навпаки { #wrong-order }

Той самий проєкт, але `COPY . .` **перед** `pip install`:

```dockerfile title="Dockerfile з неправильним порядком"
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["uvicorn", "news_hub.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

```text
$ echo "# y" >> news_hub/models.py
$ time docker build --progress=plain -t news_hub:wrong .
#6 [2/4] WORKDIR /app
#6 CACHED
#7 [3/4] COPY . .
#7 DONE 0.2s
#8 [4/4] RUN pip install --no-cache-dir -r requirements.txt
#8 DONE 127.8s
real    2m17.076s
```

Ще один вимір на тому ж порядку (у Dockerfile з [Знайди помилку](checkpoint.md#find-bug)) — 37.7 с. Розкид — від мережі: `pip install` щоразу заново качає всі пакети. А з правильним порядком мережа не потрібна взагалі.

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph B1 ["неправильний порядок: крок 1"]
        direction LR
        B1a["FROM python:3.12-slim"] --> B1b["CACHED"]
    end
    subgraph B2 ["крок 2"]
        direction LR
        B2a["COPY . ."] --> B2b["змінився один .py"] --> B2c["виконати"]
    end
    subgraph B3 ["крок 3"]
        direction LR
        B3a["RUN pip install"] --> B3b["попередній шар новий —<br>кеш уже не діє"] --> B3c["знову качати й ставити<br>усі залежності"]
    end
    R2["перезбирання: 2 хв 17 с"]
    B1 --> B2 --> B3 --> R2

    class B1a,B2a,B3a step
    class B2b,B3b decision
    class B1b success
    class B2c warning
    class B3c,R2 error
```

| Порядок | Перезбирання після зміни одного `.py` |
|---|---|
| `COPY requirements.txt` → `pip install` → `COPY . .` (крок 10) | 1.654 с |
| `COPY . .` → `pip install` | 2 хв 17 с (і 37.7 с в іншому вимірі) |

## Коли кеш залежностей **має** злетіти { #when-rebuild }

- **Змінився `requirements.txt`.** `COPY requirements.txt .` отримує новий вміст → `pip install` і все після нього виконуються заново. Так і треба.
- **Треба свіжі версії без зміни `requirements.txt`.** Кеш не знає, що на PyPI вийшла нова версія: `fastapi>=0.121` у кеші лишиться тією, що встановилась першого разу. Перезібрати без кешу — `docker build --no-cache …`, або оновити базовий образ — `docker build --pull …`.
- **Новий базовий образ.** `docker pull python:3.12-slim` приніс оновлення безпеки → змінився шар `FROM` → перезбирається все.

Версії «від і вище» в `requirements.txt` (`>=`) означають, що два образи, зібрані в різні дні **без кешу**, можуть мати різні версії бібліотек. Що «від і вище» справді працює й на найменших дозволених версіях, перевіряє CI у [кроці 12](../12_ci_cd/index.md).

## Правило { #rule }

!!! tip "Правило"
    Інструкції в `Dockerfile` — від тих, що змінюються рідко, до тих, що змінюються щодня: базовий образ → залежності (`COPY requirements.txt` + `pip install`) → код (`COPY . .`). Зміна коду не повинна зачіпати шар залежностей, а `.dockerignore` не дає кешам і самому `Dockerfile` інвалідувати шар коду.

**Далі:** [Користувач, дані й змінні середовища](user_data_env.md) — від чийого імені працює контейнер і де лежить база.
