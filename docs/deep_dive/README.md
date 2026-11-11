# News Hub Deep Dive

Розбір фінальної версії — [`steps/12_ci_cd`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/12_ci_cd):
не «як ми сюди дійшли» (це Zero to Hero), а «як воно влаштоване зараз».

```mermaid
flowchart LR
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    SRC["rbc.ua · RSS"] --> P["parser · rss"] --> M["NewsItem<br>Pydantic"] --> R["repository<br>SQLAlchemy"]
    R --> DB["PostgreSQL"]
    API["FastAPI<br>api.py"] --> R
    API --> C["Redis<br>кеш · ліміт · задачі"]
    API --> L["LLM<br>Gemini / Anthropic"]
    BOT["Telegram-бот<br>aiogram"] --> R

    class SRC,P,M,R,API,C,L,BOT step
    class DB success
```

## Розділи (у роботі)

| Розділ | Що там |
|---|---|
| Архітектура | компоненти, залежності між модулями, правила (`CLAUDE.md` кроку 12) |
| Карта модулів | кожен файл `news_hub/` — за що відповідає, з якого кроку |
| Життєвий цикл запиту | nginx → middleware → залежності → ендпоінт → репозиторій → кеш → відповідь |
| Модель даних і міграції | таблиці `news`, `sources`, `subscriptions`; міграції 0001–0004 |
| Карта тестів | unit / integration / docker / live — що справжнє, що підмінене |
| CI | jobs `news_hub.yml` і чому саме такі |
