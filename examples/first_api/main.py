from fastapi import FastAPI

app = FastAPI(title="Перший API")


@app.get("/")
def hello() -> dict[str, str]:
    return {"message": "Привіт! Це відповідь сервера"}


@app.get("/news/{news_id}")
def get_news(news_id: int, lang: str = "uk") -> dict[str, int | str]:
    return {"id": news_id, "lang": lang, "title": f"Новина номер {news_id}"}
