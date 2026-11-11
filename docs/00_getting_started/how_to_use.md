# Як читати кроки

## Маршрут одного кроку

1. Відкрий сторінку кроку в [Zero to Hero](../tutorials/README.md): «Де ми зараз», яку проблему розв'язуємо.
2. Прочитай, що змінюється, і відкрий ці файли в `steps/NN_*`.
3. Коли не ясно, чому зроблено саме так, — переходь за посиланням у розділ книги (частини I–X).
4. Запусти тести кроку й сам API.
5. Пройди контрольну точку і практику кроку.

## Порівняння кроків { #compare }

Наступний крок = попередній + зміни. Що змінилось:

```bash
# які файли змінились і наскільки
git diff --no-index --stat steps/03_sqlalchemy_alembic steps/04_middleware_redis

# самі зміни в коді застосунку
git diff --no-index steps/03_sqlalchemy_alembic/news_hub steps/04_middleware_redis/news_hub
```

У PyCharm: виділи дві папки → **Compare Directories** (`Ctrl+D`). У VS Code: правий клік на файлі →
**Select for Compare**, потім на іншому → **Compare with Selected**.

## Приклади поза кроками

- `examples/meteo_api` — API метеостанцій для [Частини I](../01_http_and_rest/README.md): дизайн REST, gRPC-версія для порівняння.
- `examples/fastapi_vs_drf` — той самий API нотаток на FastAPI для порівняння з DRF ([Частина III](../03_fastapi_core/fastapi_vs_drf.md)).
- `examples/fastapi_demo` — що блокує сервер: [виміри на кроці 2](../tutorials/02_fastapi_basics/async_measurements.md).
