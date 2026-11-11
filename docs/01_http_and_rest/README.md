# Частина I. HTTP і дизайн REST API

Що таке API і які вони бувають (REST, gRPC, GraphQL, WebSocket), принципи REST, коди відповідей, версіонування. Приклад — API метеостанцій `examples/meteo_api`, бо на ньому видно дизайн API ще до FastAPI-специфіки.

## Розділи

| Розділ | Код | Стан |
|---|---|---|
| [HTTP-запит і відповідь зсередини](http_anatomy.md) | `examples/http_anatomy/inspect_app.py`, `raw_client.py` | готово |
| [Методи HTTP: безпечність, ідемпотентність, кеш](http_methods.md) | `examples/http_anatomy/methods_app.py` | готово |
| [Коди відповідей](status_codes.md) | `examples/http_anatomy/codes_app.py` | готово |
| Які бувають API | `examples/meteo_api/meteo_api/grpc_meteo.py`, `meteo.proto` | у роботі |
| Принципи REST | — | у роботі |
| Кейс: API v1 → v2 | `meteo_api/legacy/` | у роботі |
| Архітектура: API, клієнт і карта | `examples/meteo_api` | у роботі |

## Код

[`examples/meteo_api`](https://github.com/NikoriakViktor/news_hub/tree/main/examples/meteo_api) — API метеостанцій: REST, gRPC-версія для порівняння, клієнт-карта.
