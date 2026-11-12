"""Авторизація у FastAPI: scopes через Security, перевірка на рівні об'єкта (BOLA), функції (BFLA), полів.

`create_app(secret)` — секрет JWT дає той, хто створює застосунок (authz_demo.py генерує одноразовий).
Вхід тут спрощено: `issue_token(...)` випускає токен з потрібними scopes — автентифікацію показує auth_app.py.

Кожна вразливість — поруч зі своїм виправленням: /v1 — як буває, /v2 — як треба.
- GET    /v1/notes/{id}      будь-яка нотатка за id                  (API1 BOLA)
- GET    /v2/notes/{id}      лише своя; чужа → 404
- PATCH  /v1/notes/{id}      тіло як dict → поля моделі               (API3 масове присвоєння)
- PATCH  /v2/notes/{id}      NoteUpdate(extra="forbid") + перевірка «можна змінювати»
- DELETE /v1/users/{id}      «прихований» адмін-маршрут, лише вхід    (API5 BFLA)
- DELETE /v2/users/{id}      Security(..., scopes=["users:delete"])
- GET    /v1/users/me        віддає модель користувача повністю       (API3 надмірні дані)
- GET    /v2/users/me        response_model=UserOut

Правило «хто може змінювати нотатку» живе в одній функції `can_edit` — її кличуть і API, і бот (`bot_edit_*`).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from pydantic import BaseModel, ConfigDict, Field

ALGORITHM = "HS256"
SCOPES = {"notes:read": "читати свої нотатки", "notes:write": "змінювати свої нотатки",
          "users:delete": "видаляти користувачів (адмін)"}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", scopes=SCOPES)


@dataclass
class User:
    id: int
    name: str
    role: str
    password_hash: str
    telegram_id: int


@dataclass
class Note:
    id: int
    owner_id: int
    title: str
    group_ids: frozenset[int] = frozenset()
    is_public: bool = False


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


def issue_token(secret: str, user: User, scopes: list[str]) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "scope": " ".join(scopes), "iat": now, "exp": now + timedelta(minutes=5)},
                      secret, algorithm=ALGORITHM)


ROLE_SCOPES = {"user": {"notes:read", "notes:write"}, "admin": set(SCOPES)}


def grant_scopes(user: User, requested: list[str]) -> list[str]:
    """Клієнт ПРОСИТЬ scopes (форма входу, поле scope), сервер ДАЄ лише ті, що дозволяє роль."""
    return sorted(set(requested) & ROLE_SCOPES[user.role])


def can_edit(user: User, note: Note) -> bool:
    """ОДНЕ правило для всіх входів: змінює автор або адмін. Учасник групи — лише читає."""
    return note.owner_id == user.id or user.role == "admin"


def can_read(user: User, note: Note, user_groups: frozenset[int]) -> bool:
    return note.owner_id == user.id or bool(note.group_ids & user_groups) or note.is_public


def create_app(secret: str) -> FastAPI:
    app = FastAPI(title="authz example")
    users = {1: User(1, "olena", "user", "$argon2id$…olena", 1001), 2: User(2, "taras", "user", "$argon2id$…taras", 1002),
             3: User(3, "admin", "admin", "$argon2id$…admin", 1003)}
    groups = {1: frozenset({10}), 2: frozenset({10}), 3: frozenset()}               # olena і taras — у групі 10
    notes = {1: Note(1, 1, "Пароль від Wi-Fi", group_ids=frozenset({10})), 2: Note(2, 1, "Подарунок Тарасу"),
             3: Note(3, 2, "Список Тараса")}
    app.state.users, app.state.notes, app.state.groups = users, notes, groups

    def current_user(security_scopes: SecurityScopes, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
        authenticate = f'Bearer scope="{security_scopes.scope_str}"' if security_scopes.scopes else "Bearer"
        try:
            claims = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        except jwt.InvalidTokenError as error:
            raise HTTPException(401, detail="недійсний токен", headers={"WWW-Authenticate": authenticate}) from error
        user = users.get(int(claims["sub"]))
        if user is None:
            raise HTTPException(401, detail="користувача немає", headers={"WWW-Authenticate": authenticate})
        granted = set(claims.get("scope", "").split())
        missing = [s for s in security_scopes.scopes if s not in granted]
        if missing:
            raise HTTPException(403, detail=f"бракує scope: {' '.join(missing)}",
                                headers={"WWW-Authenticate": authenticate})
        return user

    Reader = Annotated[User, Security(current_user, scopes=["notes:read"])]
    Writer = Annotated[User, Security(current_user, scopes=["notes:write"])]
    Anyone = Annotated[User, Depends(current_user)]

    def note_or_404(note_id: int) -> Note:
        note = notes.get(note_id)
        if note is None:
            raise HTTPException(404, detail="нотатки немає")
        return note

    def readable_note(note_id: int, user: Reader) -> Note:
        note = notes.get(note_id)
        if note is None or not can_read(user, note, groups[user.id]):
            raise HTTPException(404, detail="нотатки немає")               # чужа = її немає
        return note

    # --- API1: BOLA --------------------------------------------------------------------------------
    @app.get("/v1/notes/{note_id}", response_model=NoteOut)
    def get_note_v1(note_id: int, user: Reader) -> Note:
        return note_or_404(note_id)                                         # автентифікація є, авторизації немає

    @app.get("/v2/notes/{note_id}", response_model=NoteOut)
    def get_note_v2(note: Annotated[Note, Depends(readable_note)]) -> Note:
        return note

    # --- API3: масове присвоєння + перевірка «можна змінювати» -------------------------------------
    @app.patch("/v1/notes/{note_id}", response_model=NoteOut)
    async def patch_note_v1(note_id: int, request: Request, user: Writer) -> Note:
        note = note_or_404(note_id)
        if note.owner_id != user.id:
            raise HTTPException(403, detail="не твоя нотатка")
        for key, value in (await request.json()).items():                   # будь-яке поле з тіла
            setattr(note, key, value)
        return note

    @app.patch("/v2/notes/{note_id}", response_model=NoteOut)
    def patch_note_v2(body: NoteUpdate, user: Writer, note: Annotated[Note, Depends(readable_note)]) -> Note:
        if not can_edit(user, note):
            raise HTTPException(403, detail="змінювати може лише автор")   # бачить, тож 403 чесний
        note.title = body.title
        return note

    # --- API5: BFLA ---------------------------------------------------------------------------------
    @app.delete("/v1/users/{user_id}", include_in_schema=False)            # «його ж не видно в /docs»
    def delete_user_v1(user_id: int, user: Anyone) -> dict[str, int]:
        users.pop(user_id, None)
        return {"deleted": user_id}

    @app.delete("/v2/users/{user_id}")
    def delete_user_v2(user_id: int, user: Annotated[User, Security(current_user, scopes=["users:delete"])]
                       ) -> dict[str, int]:
        users.pop(user_id, None)
        return {"deleted": user_id}

    # --- API3: надмірні дані у відповіді ------------------------------------------------------------
    @app.get("/v1/users/me")
    def me_v1(user: Anyone) -> dict[str, Any]:
        return user.__dict__

    @app.get("/v2/users/me", response_model=UserOut)
    def me_v2(user: Anyone) -> User:
        return user

    return app


# --- другий вхід: Telegram-бот (без HTTP) — та сама дія «змінити заголовок» --------------------------

def bot_edit_v1(app: FastAPI, telegram_id: int, note_id: int, title: str) -> str:
    """Бот перевіряє лише «це наш користувач?» — правило автора забули."""
    user = next((u for u in app.state.users.values() if u.telegram_id == telegram_id), None)
    note = app.state.notes.get(note_id)
    if user is None or note is None:
        return "не знайдено"
    note.title = title
    return f"змінено: {note.title}"


def bot_edit_v2(app: FastAPI, telegram_id: int, note_id: int, title: str) -> str:
    """Те саме, що PATCH /v2: can_read → can_edit → валідація NoteUpdate."""
    user = next((u for u in app.state.users.values() if u.telegram_id == telegram_id), None)
    note = app.state.notes.get(note_id)
    if user is None or note is None or not can_read(user, note, app.state.groups[user.id]):
        return "не знайдено"
    if not can_edit(user, note):
        return "змінювати може лише автор"
    note.title = NoteUpdate(title=title).title
    return f"змінено: {note.title}"
