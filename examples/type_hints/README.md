# Анотації типів: що читає FastAPI, а що лише mypy

```bash
pip install -r requirements.txt
python runtime_demo.py          # що FastAPI і Pydantic перевіряють під час запиту; схема OpenAPI
python mypy_only.py             # виконується, хоча код з помилками
mypy --strict mypy_only.py      # ті самі помилки до запуску
python future_gotcha.py         # from __future__ import annotations і модель усередині функції
```

Розбір — сторінка книги «Анотації типів» (Частина II).
