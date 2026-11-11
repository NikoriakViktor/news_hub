# Частина II. Типи і Pydantic

Анотації типів, `TypedDict`, `mypy --strict` і моделі Pydantic v2 як межа довіри між «сирими» даними ззовні й кодом, який їм вірить.

## Розділи

| Розділ | Код | Стан |
|---|---|---|
| [Анотації типів: що читає FastAPI, а що лише mypy](type_hints.md) | `examples/type_hints/runtime_app.py`, `mypy_only.py` | готово |
| [Моделі Pydantic 2](pydantic_models.md) | `examples/pydantic_v2/models_demo.py`, `migration_demo.py` | готово |
| [Режими lax і strict](strict_mode.md) | `examples/pydantic_v2/strict_demo.py` | готово |
| Межа довіри | — | у роботі |

## На практиці — Zero to Hero

- [Крок 1. Типи і Pydantic](../tutorials/01_typing_pydantic/index.md) — `steps/01_typing_pydantic`
