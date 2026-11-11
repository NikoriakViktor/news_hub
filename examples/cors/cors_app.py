"""CORS у FastAPI: безпечне налаштування CORSMiddleware і що ламається від неправильного.

    python cors_demo.py
"""
from typing import Annotated

from fastapi import Cookie, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings, NoDecode
from pydantic import field_validator


class Settings(BaseSettings):
    """CORS_ORIGINS=https://ui.example.com,http://localhost:3000 — список через кому зі змінної середовища."""
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]   # NoDecode: не розбирати як JSON

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value


def create_app(origins: list[str], *, credentials: bool = True, limit_after_cors: bool = False) -> FastAPI:
    app = FastAPI()
    state = {"transfers": 0}

    async def rate_limit(request: Request, call_next):
        if request.headers.get("x-flood"):
            return JSONResponse({"detail": "Too Many Requests"}, status_code=429, headers={"Retry-After": "5"})
        return await call_next(request)

    # add_middleware і app.middleware загортають застосунок: останній доданий — зовнішній, спрацьовує першим
    if not limit_after_cors:
        app.middleware("http")(rate_limit)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=credentials,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )
    if limit_after_cors:
        app.middleware("http")(rate_limit)        # зовні від CORS: його 429 не отримає заголовків CORS

    @app.get("/api/me")
    def me(session_id: Annotated[str | None, Cookie()] = None) -> dict:
        if session_id != "s3cr3t":
            raise HTTPException(401, "not logged in")
        return {"user": "olena", "balance": 1200}

    @app.post("/api/transfer")
    def transfer(amount: Annotated[int, Form()], session_id: Annotated[str | None, Cookie()] = None) -> dict:
        if session_id != "s3cr3t":
            raise HTTPException(401, "not logged in")
        state["transfers"] += 1
        return {"transferred": amount}

    @app.get("/api/transfers")
    def transfers() -> dict:
        return state

    @app.get("/api/boom")
    def boom() -> dict:
        raise RuntimeError("boom")

    return app
