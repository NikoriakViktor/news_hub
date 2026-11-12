"""Автентифікація у FastAPI: OAuth2PasswordBearer + JWT (access і refresh) і, для порівняння, сесія в cookie.

Запуск: `create_app(secret, users)` — секрет і паролі передає той, хто створює застосунок (auth_demo.py
генерує одноразові). Сховище — словники в пам'яті: щоб було видно, ЩО саме серверу доводиться пам'ятати.

- POST /token          форма username/password → access (5 хв) + refresh (7 днів)
- GET  /me             Authorization: Bearer <access>
- POST /refresh        ротація: старий refresh більше не діє; повторне використання → відкликати всю «родину»
- POST /logout         відкликати «родину» цього входу: її access і refresh (сервер пам'ятає її до exp)
- POST /logout-all     token_version += 1 — недійсні всі токени користувача
- POST /password-reset, POST /password-reset/confirm   однакова відповідь для будь-якого email; одноразове посилання
- POST /session, GET /session/me, DELETE /session      сесія: випадковий ідентифікатор у cookie, дані на сервері
- POST /session/transfer        дія з cookie БЕЗ перевірки джерела (CSRF)
- POST /session/transfer-safe   та сама дія з перевіркою Origin
"""
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

ALGORITHM = "HS256"                        # у коді, а не з налаштувань
ACCESS_TTL = timedelta(minutes=5)
REFRESH_TTL = timedelta(days=7)
ALLOWED_ORIGINS = {"https://app.example.com"}

ph = PasswordHasher()


@dataclass
class Store:
    users: dict[str, dict[str, Any]] = field(default_factory=dict)       # username → hash, token_version
    refresh: dict[str, dict[str, Any]] = field(default_factory=dict)     # jti → user, family, used
    revoked_families: set[str] = field(default_factory=set)
    sessions: dict[str, str] = field(default_factory=dict)               # session id → username
    outbox: list[tuple[str, str]] = field(default_factory=list)          # «надіслані листи»: (кому, посилання)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class ResetIn(BaseModel):
    email: str


class ResetConfirmIn(BaseModel):
    token: str
    new_password: str


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")                    # лише ОПИС для OpenAPI + читання заголовка


def create_app(secret: str, users: dict[str, str], emails: dict[str, str] | None = None) -> FastAPI:
    app = FastAPI(title="auth example")
    emails = emails or {}
    store = Store(users={name: {"hash": ph.hash(pw), "token_version": 0, "email": emails.get(name)}
                         for name, pw in users.items()})
    app.state.store = store
    dummy_hash = ph.hash(secrets.token_urlsafe(16))

    def unauthorized(detail: str) -> HTTPException:
        return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})

    def issue(username: str, family: str | None = None) -> TokenPair:
        now = datetime.now(timezone.utc)
        family = family or uuid.uuid4().hex
        version = store.users[username]["token_version"]
        access = {"sub": username, "type": "access", "jti": uuid.uuid4().hex, "ver": version, "fam": family,
                  "iat": now, "exp": now + ACCESS_TTL}
        refresh_jti = uuid.uuid4().hex
        refresh = {"sub": username, "type": "refresh", "jti": refresh_jti, "ver": version, "fam": family,
                   "iat": now, "exp": now + REFRESH_TTL}
        store.refresh[refresh_jti] = {"user": username, "family": family, "used": False}
        return TokenPair(access_token=jwt.encode(access, secret, algorithm=ALGORITHM),
                         refresh_token=jwt.encode(refresh, secret, algorithm=ALGORITHM))

    def decode(token: str, expected_type: str) -> dict[str, Any]:
        try:
            claims: dict[str, Any] = jwt.decode(token, secret, algorithms=[ALGORITHM],
                                                options={"require": ["exp", "sub", "jti", "type"]})
        except jwt.ExpiredSignatureError as error:
            raise unauthorized("токен прострочений") from error
        except jwt.InvalidTokenError as error:
            raise unauthorized("недійсний токен") from error
        if claims["type"] != expected_type:
            raise unauthorized(f"потрібен {expected_type}-токен")
        user = store.users.get(claims["sub"])
        if user is None:
            raise unauthorized("недійсний токен")
        if expected_type != "reset" and claims.get("ver") != user["token_version"]:   # reset: свій механізм — pwd
            raise unauthorized("токен відкликано (вихід на всіх пристроях)")
        if claims.get("fam") in store.revoked_families:
            raise unauthorized("сесію відкликано")
        return claims

    def current_claims(token: Annotated[str, Depends(oauth2_scheme)]) -> dict[str, Any]:
        return decode(token, "access")

    Claims = Annotated[dict[str, Any], Depends(current_claims)]

    @app.post("/token", response_model=TokenPair)
    def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenPair:
        user = store.users.get(form.username)
        try:
            ph.verify(user["hash"] if user else dummy_hash, form.password)       # хеш перевіряється завжди
        except VerifyMismatchError:
            raise unauthorized("неправильне ім'я або пароль") from None
        if user is None:
            raise unauthorized("неправильне ім'я або пароль")
        return issue(form.username)

    @app.get("/me")
    def me(claims: Claims) -> dict[str, Any]:
        return {"user": claims["sub"], "jti": claims["jti"][:8]}

    @app.post("/refresh", response_model=TokenPair)
    def refresh(body: RefreshIn) -> TokenPair:
        claims = decode(body.refresh_token, "refresh")
        record = store.refresh.get(claims["jti"])
        if record is None:
            raise unauthorized("невідомий refresh-токен")
        if record["used"]:                                     # украдений і вже використаний кимось іншим
            store.revoked_families.add(record["family"])
            raise unauthorized("повторне використання refresh-токена: усю сесію відкликано")
        record["used"] = True
        return issue(claims["sub"], family=record["family"])

    @app.post("/logout", status_code=204)
    def logout(claims: Claims) -> Response:
        store.revoked_families.add(claims["fam"])             # access цього входу живий ще до 5 хв — тому список
        return Response(status_code=204)

    @app.post("/logout-all", status_code=204)
    def logout_all(claims: Claims) -> Response:
        store.users[claims["sub"]]["token_version"] += 1
        return Response(status_code=204)

    # --- скидання пароля -----------------------------------------------------------------------------

    def password_fingerprint(username: str) -> str:
        """Частина поточного хешу: змінився пароль — старе посилання більше не діє."""
        return hashlib.sha256(store.users[username]["hash"].encode()).hexdigest()[:16]

    @app.post("/password-reset", status_code=202)
    def password_reset(body: ResetIn) -> dict[str, str]:
        username = next((name for name, u in store.users.items() if u.get("email") == body.email), None)
        if username is not None:
            now = datetime.now(timezone.utc)
            token = jwt.encode({"sub": username, "type": "reset", "pwd": password_fingerprint(username),
                                "jti": uuid.uuid4().hex, "iat": now, "exp": now + timedelta(minutes=30)},
                               secret, algorithm=ALGORITHM)
            store.outbox.append((body.email, f"https://app.example.com/reset?token={token}"))
        return {"detail": "якщо такий email є, лист надіслано"}          # однаково для будь-якого email

    @app.post("/password-reset/confirm", status_code=204)
    def password_reset_confirm(body: ResetConfirmIn) -> Response:
        claims = decode(body.token, "reset")
        if claims.get("pwd") != password_fingerprint(claims["sub"]):
            raise unauthorized("посилання вже використано")
        store.users[claims["sub"]]["hash"] = ph.hash(body.new_password)
        store.users[claims["sub"]]["token_version"] += 1                  # новий пароль — усі старі токени геть
        return Response(status_code=204)

    # --- сесія в cookie -------------------------------------------------------------------------------

    def session_user(sid: Annotated[str | None, Cookie()] = None) -> str:
        username = store.sessions.get(sid or "")
        if username is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="немає сесії")
        return username

    SessionUser = Annotated[str, Depends(session_user)]

    @app.post("/session", status_code=204)
    def session_login(form: Annotated[OAuth2PasswordRequestForm, Depends()], response: Response) -> None:
        user = store.users.get(form.username)
        try:
            ph.verify(user["hash"] if user else dummy_hash, form.password)
        except VerifyMismatchError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="неправильне ім'я або пароль") from None
        sid = secrets.token_urlsafe(32)                     # випадковий ідентифікатор, у ньому нічого немає
        store.sessions[sid] = form.username
        response.set_cookie("sid", sid, httponly=True, secure=True, samesite="lax", max_age=3600)

    @app.get("/session/me")
    def session_me(user: SessionUser) -> dict[str, str]:
        return {"user": user}

    @app.delete("/session", status_code=204)
    def session_logout(user: SessionUser, sid: Annotated[str, Cookie()]) -> Response:
        store.sessions.pop(sid, None)                        # вихід діє миттєво: даних більше немає
        return Response(status_code=204)

    @app.post("/session/transfer")
    def transfer(user: SessionUser) -> dict[str, str]:
        return {"done": f"переказ від {user}"}

    @app.post("/session/transfer-safe")
    def transfer_safe(user: SessionUser, request: Request) -> dict[str, str]:
        origin = request.headers.get("origin")
        if origin not in ALLOWED_ORIGINS:                    # немає Origin або чужий — відмова
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"чуже джерело: {origin}")
        return {"done": f"переказ від {user}"}

    return app
