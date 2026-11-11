"""HTTP-кеш на боці клієнта: Cache-Control, ETag і 304 Not Modified. FastAPI сам цього не робить."""
import hashlib
import json
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response

app = FastAPI()
ARTICLES = {"rest": {"slug": "rest", "title": "Принципи REST"}}


@app.get("/articles/{slug}")
def get_article(slug: str, response: Response,
                if_none_match: Annotated[str | None, Header()] = None) -> dict | None:
    if slug not in ARTICLES:
        raise HTTPException(404, "Article not found")
    body = json.dumps(ARTICLES[slug], ensure_ascii=False, sort_keys=True).encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:16] + '"'            # «відбиток» поточної версії
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60"}     # 60 с можна не питати взагалі
    if if_none_match == etag:                                            # у клієнта та сама версія
        return Response(status_code=304, headers=headers)               # тіла немає — лише «не змінилось»
    response.headers.update(headers)
    return ARTICLES[slug]


@app.get("/me")
def me(response: Response) -> dict:
    response.headers["Cache-Control"] = "private, no-store"              # особисте — у спільний кеш ні
    return {"user": "olena"}
