# Як користуватися книгою

Книга має дві половини, які читаються разом:

- **Zero to Hero** — 12 кроків. Кожен крок — це папка `steps/NN_*` з повним робочим проєктом і сторінка в книзі,
  яка пояснює, що змінилося порівняно з попереднім кроком і чому.
- **Книга FastAPI** — частини I–X зі знаннями: як працює HTTP API, FastAPI, async, бази, кеш, тести, безпека, Docker.
  Крок посилається на потрібні розділи, тож теорію читаєш тоді, коли вона знадобилась.

```mermaid
flowchart LR
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    A["сторінка кроку<br>що змінюємо"] --> B["код кроку<br>steps/NN"]
    B --> C{"незрозуміло<br>чому так?"}
    C -->|так| D["розділ книги<br>частини I–X"]
    D --> B
    C -->|ні| E["тести кроку<br>pytest"]
    E --> F["контрольна точка<br>наступний крок"]

    class A,B,D,E step
    class C decision
    class F success
```

## У цьому розділі

| Сторінка | Що там |
|---|---|
| [Необхідні знання](prerequisites.md) | що варто знати до початку |
| [Налаштування](local_setup.md) | Python, venv, залежності кроку, PostgreSQL і Redis |
| [Структура репозиторію](repository_structure.md) | `steps/`, `examples/`, `docs/`, CI |
| [Як читати кроки](how_to_use.md) | маршрут, порівняння кроків, приклади поза кроками |
