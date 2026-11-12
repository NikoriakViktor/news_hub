# Лаба 2. Стрічка з курсором: keyset-пагінація { #lab-02 }

| | |
|---|---|
| Основа | [крок 3](../tutorials/03_sqlalchemy_alembic/index.md) — `steps/03_sqlalchemy_alembic` |
| Що тренує | метод репозиторію з `WHERE … ORDER BY … LIMIT`, модель відповіді, порядок маршрутів, `Query`-перевірки, тести, що ходять по сторінках |
| Складність | ★★☆ |
| Орієнтовний час | 2–3 години |

## Мета { #goal }

**Задача.** `GET /api/news?skip=…&limit=…` з кроку 3 — пагінація зміщенням: `ORDER BY id OFFSET skip LIMIT limit`.
У неї дві проблеми, і обидві з'являються не в тестах, а з живими даними.

1. **Ціна.** Щоб віддати сторінку з кінця, база читає й викидає всі рядки до неї. Вимір на PostgreSQL 16, таблиця
   з 300 000 рядків і первинним ключем `id`:

    ```text
    EXPLAIN (ANALYZE, COSTS OFF) SELECT id, title FROM demo_news ORDER BY id OFFSET 299950 LIMIT 50;
     Limit (actual time=25.479..25.486 rows=50 loops=1)
       ->  Index Scan using demo_news_pkey on demo_news (actual time=0.011..19.573 rows=300000 loops=1)
     Execution Time: 25.503 ms

    EXPLAIN (ANALYZE, COSTS OFF) SELECT id, title FROM demo_news WHERE id > 299950 ORDER BY id LIMIT 50;
     Limit (actual time=0.008..0.014 rows=50 loops=1)
       ->  Index Scan using demo_news_pkey on demo_news (actual time=0.007..0.011 rows=50 loops=1)
             Index Cond: (id > 299950)
     Execution Time: 0.028 ms
    ```

    Перший план прочитав `rows=300000`, щоб показати 50. Другий одразу пішов індексом до `id > 299950`.
    Ціна `OFFSET` росте з номером сторінки, ціна `WHERE id > …` — ні.

2. **Стабільність.** Клієнт прочитав сторінку 1 (`skip=0`), тим часом дві новини з неї видалили. Тепер
   `skip=5` відраховує п'ять рядків від **нового** початку таблиці, і дві новини клієнт не побачить ніколи.
   Додавання в середину дає протилежне: одна новина покажеться двічі.

**Зміна.** Стрічка з курсором (**keyset-пагінація**). Клієнт не каже «пропусти N», а каже «дай наступні після
`id = X`», де `X` — `id` останньої новини, яку він уже показав. Сервер повертає сторінку й курсор
наступної: `next_after`.

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph P1["запит 1: after_id = 0, limit = 3"]
        direction LR
        P1a["WHERE id > 0<br>LIMIT 4"] --> P1b["id 1, 2, 3, 4<br>4 > 3: є ще"] --> P1c["items 1, 2, 3<br>next_after = 3"]
    end
    subgraph P2["запит 2: after_id = 3"]
        direction LR
        P2a["WHERE id > 3<br>LIMIT 4"] --> P2b["id 4, 5, 7, 8<br>(6 видалено)"] --> P2c["items 4, 5, 7<br>next_after = 7"]
    end
    subgraph P3["запит 3: after_id = 7"]
        direction LR
        P3a["WHERE id > 7<br>LIMIT 4"] --> P3b["id 8<br>1 ≤ 3: кінець"] --> P3c["items 8<br>next_after = null"]
    end
    P1 --> P2 --> P3

    class P1a,P2a,P3a step
    class P1b,P2b,P3b decision
    class P1c,P2c warning
    class P3c success
```

**Результат.** Кожна сторінка — один запит індексом первинного ключа; видалення чи додавання між запитами не
зсуває стрічку; остання сторінка сама каже, що вона остання (`next_after: null`), без зайвого порожнього запиту.

**Правило.** Для стрічки й нескінченного скролу — курсор по унікальному впорядкованому ключу, а не `OFFSET`.
Ціна: не можна перейти одразу на сторінку 6001 — для стрічки новин це й не потрібно.

## Звідки починаємо { #start }

```bash
cp -r steps/03_sqlalchemy_alembic lab_02 && cd lab_02
pip install -r requirements.txt
pytest -q
```

```text
32 passed in 0.51s
```

Код, який змінюватимеш:
[`news_hub/repository.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/news_hub/repository.py)
(метод `find` — пагінація зміщенням) і
[`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/news_hub/api.py)
(ендпоінти `/api/news…`).

## Вимоги { #requirements }

1. **Репозиторій.** Метод `NewsRepository.feed(*, after_id: int = 0, limit: int = 50, lang: str = "")` —
   `WHERE id > :after_id ORDER BY id LIMIT :limit`, з необов'язковим фільтром мови. Без `offset()`.
2. **Модель відповіді.** `FeedPage`: `items: list[NewsOut]`, `next_after: int | None`.
3. **Ендпоінт.** `GET /api/news/feed`:
    - `after_id: int` — `≥ 0`, за замовчуванням `0` (з початку);
    - `limit: int` — `1…100`, за замовчуванням `20`;
    - `lang: Literal["uk", "ru"] | None` — той самий фільтр, що в `GET /api/news`;
    - `next_after` — `id` останньої новини сторінки, якщо після неї є ще новини; `null` — якщо сторінка остання.
      Порожньої сторінки «в кінці» бути не повинно: якщо новин рівно `2 × limit`, другий запит уже повертає `null`.
4. **Порядок маршрутів.** `/api/news/feed` оголошено **до** `/api/news/{news_id}` — інакше `"feed"` потрапить у
   `news_id: int` і клієнт отримає `422` про `news_id`.
5. Наявний тест `test_openapi_lists_endpoints` у `tests/test_api.py` перелічує всі шляхи API — додай у нього
   `"/api/news/feed"`: новий ендпоінт — свідома зміна контракту, і тест має про неї знати.
6. `GET /api/news?skip=…` лишається як є — не ламай наявних клієнтів.
7. `mypy --strict news_hub` — без помилок.

## Критерії приймання { #acceptance }

Поклади файл у `tests/test_feed.py` (фікстура `client` — з наявного `tests/conftest.py`: SQLite у пам'яті,
окрема база на кожен тест).

```python title="tests/test_feed.py"
"""Лаба 2: стрічка з keyset-пагінацією — GET /api/news/feed?after_id=&limit=."""
from typing import Any

import pytest
from fastapi.testclient import TestClient


def fill(client: TestClient) -> list[int]:
    """Знімок rbc.ua у базу; повертає id усіх новин за зростанням."""
    assert client.post("/api/scrape", json={"source": "snapshot"}).json()["news_saved"] == 168
    return [news["id"] for news in client.get("/api/news", params={"limit": 1000}).json()]


def walk(client: TestClient, limit: int, **params: Any) -> tuple[list[int], int]:
    """Пройти стрічку від початку до кінця; повертає id і кількість запитів."""
    ids: list[int] = []
    after_id, requests = 0, 0
    while True:
        response = client.get("/api/news/feed", params={"after_id": after_id, "limit": limit, **params})
        assert response.status_code == 200, response.text
        page = response.json()
        requests += 1
        assert len(page["items"]) <= limit
        ids += [news["id"] for news in page["items"]]
        if page["next_after"] is None:
            return ids, requests
        assert page["next_after"] == page["items"][-1]["id"]       # курсор — id останньої новини сторінки
        assert page["next_after"] > after_id, "курсор не рухається — стрічка зациклилась"
        after_id = page["next_after"]


def test_empty_feed(client: TestClient) -> None:
    assert client.get("/api/news/feed").json() == {"items": [], "next_after": None}


@pytest.mark.parametrize("limit", [1, 7, 50])
def test_walk_returns_every_news_once(client: TestClient, limit: int) -> None:
    all_ids = fill(client)
    ids, _ = walk(client, limit)
    assert len(ids) == len(set(ids)), "є повтори"
    assert ids == all_ids


def test_no_empty_page_at_the_end(client: TestClient) -> None:
    fill(client)                                    # 168 = 21 × 8
    ids, requests = walk(client, 8)
    assert (len(ids), requests) == (168, 21)       # 21-ша сторінка вже каже next_after = null


def test_items_have_news_fields(client: TestClient) -> None:
    fill(client)
    first = client.get("/api/news/feed", params={"limit": 1}).json()["items"][0]
    assert first == client.get(f"/api/news/{first['id']}").json()


def test_deleting_between_pages_does_not_shift_feed(client: TestClient) -> None:
    all_ids = fill(client)
    page1 = client.get("/api/news/feed", params={"limit": 5}).json()
    assert [n["id"] for n in page1["items"]] == all_ids[:5]
    # поки клієнт читає першу сторінку, дві новини з неї видалили
    for news_id in all_ids[:2]:
        assert client.delete(f"/api/news/{news_id}").status_code == 204
    page2 = client.get("/api/news/feed", params={"after_id": page1["next_after"], "limit": 5}).json()
    assert [n["id"] for n in page2["items"]] == all_ids[5:10]     # жодна новина не пропущена

    # той самий сценарій зі skip/limit пропустив би дві новини:
    offset_page2 = client.get("/api/news", params={"skip": 5, "limit": 5}).json()
    assert [n["id"] for n in offset_page2] == all_ids[7:12]


def test_lang_filter_is_kept_across_pages(client: TestClient) -> None:
    fill(client)
    ru_total = client.get("/api/news/stats").json()["lang"]["ru"]
    ids, _ = walk(client, 2, lang="ru")
    assert len(ids) == ru_total
    assert {client.get(f"/api/news/{i}").json()["lang"] for i in ids} == {"ru"}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"after_id": -1}, {"lang": "en"}])
def test_bad_params_are_422(client: TestClient, params: dict[str, Any]) -> None:
    response = client.get("/api/news/feed", params=params)
    assert response.status_code == 422
    # помилка саме в цьому параметрі, а не в news_id: маршрут /feed оголошено до /{news_id}
    assert [error["loc"] for error in response.json()["detail"]] == [["query", *params]]


def test_feed_is_in_openapi(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/news/feed" in paths
```

Останній `assert` у `test_deleting_between_pages_does_not_shift_feed` перевіряє не твій код, а стару пагінацію:
він фіксує в тесті саму проблему, заради якої лаба існує.

**До змін** — усі 13 тестів червоні. Навіть `422` не «випадково зелені»: зараз `/api/news/feed` потрапляє в
`/api/news/{news_id}`, і помилка там про `news_id`, а не про `limit`:

```text
$ pytest -q tests/test_feed.py
FAILED tests/test_feed.py::test_empty_feed - AssertionError: assert {'detail'...
FAILED tests/test_feed.py::test_walk_returns_every_news_once[1] - AssertionEr...
FAILED tests/test_feed.py::test_walk_returns_every_news_once[7] - AssertionEr...
FAILED tests/test_feed.py::test_walk_returns_every_news_once[50] - AssertionE...
FAILED tests/test_feed.py::test_no_empty_page_at_the_end - AssertionError: {"...
FAILED tests/test_feed.py::test_items_have_news_fields - KeyError: 'items'
FAILED tests/test_feed.py::test_deleting_between_pages_does_not_shift_feed - ...
FAILED tests/test_feed.py::test_lang_filter_is_kept_across_pages - AssertionE...
FAILED tests/test_feed.py::test_bad_params_are_422[params0] - AssertionError:...
FAILED tests/test_feed.py::test_bad_params_are_422[params1] - AssertionError:...
FAILED tests/test_feed.py::test_bad_params_are_422[params2] - AssertionError:...
FAILED tests/test_feed.py::test_bad_params_are_422[params3] - AssertionError:...
FAILED tests/test_feed.py::test_feed_is_in_openapi - AssertionError: assert '...
13 failed in 0.39s
```

**Після** — увесь набір кроку разом з новими тестами, і типи:

```text
$ pytest -q
45 passed in 3.69s
$ mypy --strict news_hub
Success: no issues found in 9 source files
```

Ті самі тести на PostgreSQL (`docker compose up -d db` з кроку 3 або власний контейнер):

```text
$ TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5591/news_hub_test pytest -q
45 passed in 5.79s
```

## Підказки { #hints }

??? tip "Як дізнатися, що сторінка остання, без зайвого запиту"
    Попроси в бази на **один** рядок більше, ніж `limit`. Прийшло `limit + 1` — наступна сторінка існує: віддай
    перші `limit`, а `next_after` — `id` останнього з них. Прийшло `≤ limit` — це кінець, `next_after = None`.
    Варіант «`next_after` = id останнього, якщо `len(items) == limit`» теж працює, але при `168 = 21 × 8` дає
    22-й порожній запит — `test_no_empty_page_at_the_end` його не пропустить.

??? tip "Ендпоінт повертає модель, а не рядки"
    `response_model=FeedPage` і `FeedPage(items=[NewsOut.model_validate(row) for row in page], ...)`:
    `NewsOut` уже має `from_attributes=True`, тож будується з `NewsRow`.

??? tip "Чому `>`, а не `>=`"
    `after_id` — це id новини, яку клієнт **уже показав**. З `>=` кожна сторінка починається з повтору, а з
    `limit=1` клієнт назавжди застрягає на одній новині — `walk` у тестах це ловить повідомленням
    «курсор не рухається».

## Підхід до розв'язку { #solution }

??? success "Підхід до розв'язку"
    Репозиторій — той самий `select`, що й у `find`, але з умовою на ключ замість `offset`:

    ```python title="news_hub/repository.py"
    async def feed(self, *, after_id: int = 0, limit: int = 50, lang: str = "") -> list[NewsRow]:
        """Keyset-пагінація: WHERE id > :after_id ORDER BY id LIMIT :limit — без OFFSET.

        База одразу йде індексом первинного ключа до after_id, а не читає й викидає skip рядків.
        """
        stmt = select(NewsRow).where(NewsRow.id > after_id).order_by(NewsRow.id).limit(limit)
        if lang:
            stmt = stmt.where(NewsRow.lang == lang)
        return list((await self._session.scalars(stmt)).all())
    ```

    Модель і ендпоінт — у `api.py`; ендпоінт стоїть поруч із `/api/news/search`, тобто до `/api/news/{news_id}`:

    ```python title="news_hub/api.py"
    class FeedPage(BaseModel):
        """Сторінка стрічки: новини й курсор наступної сторінки (null — це остання)."""
        items: list[NewsOut]
        next_after: int | None


    @app.get("/api/news/feed", response_model=FeedPage, tags=["news"], summary="Стрічка з курсором")
    async def news_feed(
        repo: RepoDep,
        after_id: int = Query(0, ge=0, description="id останньої новини попередньої сторінки"),
        limit: int = Query(20, ge=1, le=100),
        lang: Literal["uk", "ru"] | None = Query(None),
    ) -> FeedPage:
        """Оголошено ДО `/api/news/{news_id}`. Беремо limit + 1 рядок: зайвий означає «є ще сторінка»."""
        rows = await repo.feed(after_id=after_id, limit=limit + 1, lang=lang or "")
        page = rows[:limit]
        next_after = page[-1].id if len(rows) > limit else None
        return FeedPage(items=[NewsOut.model_validate(row) for row in page], next_after=next_after)
    ```

    І одна зміна в наявному тесті:

    ```diff title="tests/test_api.py"
         assert set(paths) == {"/health", "/api/news", "/api/news/count", "/api/news/stats", "/api/scrape",
    -                          "/api/news/{news_id}", "/api/news/search"}
    +                          "/api/news/{news_id}", "/api/news/search", "/api/news/feed"}
    ```

    Міграція не потрібна: `id` — первинний ключ, індекс на нього вже є.

## Що перевірити самому { #self-check }

- [ ] Заміни `>` на `>=` у `feed` і запусти `pytest -q tests/test_feed.py`: має впасти 6 тестів, серед них
      `test_walk_returns_every_news_once[1]` з «курсор не рухається». Поверни `>`.
- [ ] Подивись SQL `GET /api/news/feed?after_id=100&limit=5` на PostgreSQL (`echo=True` у `make_engine`):
      `WHERE news.id > … ORDER BY news.id LIMIT …`, без `OFFSET`. На SQLite у тексті буде `LIMIT ? OFFSET ?` —
      це діалект SQLite завжди дописує `OFFSET` до `LIMIT` (зі значенням `0`), а не твій код. Потім виконай
      `EXPLAIN ANALYZE` цього запиту в `psql` і порівняй з планом `OFFSET` з розділу [Мета](#goal).
- [ ] Перенеси ендпоінт **після** `/api/news/{news_id}` — які тести впадуть і з якою помилкою в `detail`?
- [ ] Відкрий `/docs`: чи видно в описі `after_id`, звідки клієнт бере його значення?
- [ ] Ускладнення: стрічка «від нових до старих» (`ORDER BY id DESC`, `WHERE id < :before_id`). А якщо сортувати
      за `scraped_at`, курсором стає пара `(scraped_at, id)`: `WHERE (scraped_at, id) < (:t, :id)` — `scraped_at` не
      унікальний, а курсор мусить бути. Який індекс тоді потрібен?
- [ ] Можеш пояснити, чому `OFFSET` пропускає новини при видаленні, а курсор — ні, не дивлячись у тест.
