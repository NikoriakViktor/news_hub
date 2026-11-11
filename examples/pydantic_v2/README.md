# Моделі Pydantic 2

```bash
pip install -r requirements.txt
python models_demo.py       # Field, model_validate, model_dump(mode=...), exclude_unset і PATCH
python strict_demo.py       # lax і strict: що перетворюється, чотири способи strict, strict у FastAPI
python validators_demo.py   # field_validator before/after, model_validator, computed_field, типові помилки
python migration_demo.py    # той самий код; запусти ще раз після pip install "pydantic<2" — побачиш різницю з Pydantic 1
```

Розбір — сторінка книги «Моделі Pydantic 2» (Частина II).
