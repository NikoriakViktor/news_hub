"""Ендпоінт, що показує кожну частину HTTP-запиту, і два маршрути для 307 / 405.

    uvicorn inspect_app:app --port 8014
"""
from typing import Annotated

from fastapi import Cookie, FastAPI, Header, Request, Response
from pydantic import BaseModel

app = FastAPI()


class Payload(BaseModel):
    message: str


@app.post("/inspect")
async def inspect_http(
    request: Request,
    response: Response,
    payload: Payload,
    user_agent: Annotated[str | None, Header()] = None,
    x_request_id: Annotated[str | None, Header()] = None,
    session_id: Annotated[str | None, Cookie()] = None,
) -> dict:
    response.headers["X-Server"] = "news-hub-demo"
    response.set_cookie("visited", "true")
    return {
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
        "user_agent": user_agent,
        "x_request_id": x_request_id,
        "session_id": session_id,
        "raw_body": (await request.body()).decode(),
        "message": payload.message,
    }


@app.get("/items/")
def items() -> list[int]:
    return [1, 2]
