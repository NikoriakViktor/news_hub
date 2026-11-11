"""Адмін-доступ: пароль (bcrypt) → JWT → `require_admin` на кожному ендпоінті запису. Урок 46.

Основа — стартовий `production_bot` (`backend/`):
`core/security.py` (хеш пароля, `create_access_token`, `decode_token`), `api/deps.py`
(`get_current_admin`: 401 — недійсний чи прострочений токен, 403 — не адмін) і `api/admin/auth.py`
(`POST /admin/auth/token`). Рефакторинг уроку 46:
- налаштування — `AdminSettings` з середовища, без значень «change-me» за замовчуванням: секрет JWT
  коротший за 32 символи — застосунок не стартує; нічого не задано — ендпоінти запису відповідають 503;
- у середовищі — **хеш** пароля (`ADMIN_PASSWORD_HASH`), а не сам пароль; згенерувати:
  `python -m news_hub.security`;
- bcrypt напряму: паролі довші за 72 байти bcrypt не приймає (ValueError) — такий пароль просто
  неправильний, а не помилка 500;
- ім'я порівнюється `hmac.compare_digest`, а пароль перевіряється завжди, навіть для чужого імені:
  за часом відповіді не видно, чи вгадали ім'я;
- алгоритм зафіксовано в коді (HS256), `decode` вимагає `exp`, `sub` і `role`.

JWT (урок 40): header.payload.signature, підпис — HMAC-SHA256(header.payload, JWT_SECRET). Сервер нічого не
зберігає: будь-хто, хто знає секрет, може випустити токен — тому секрет довгий, випадковий і лише в env.
"""
import argparse
import getpass
import hmac
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_ALGORITHM = "HS256"          # у коді, а не з env: алгоритм — не налаштування
MIN_SECRET_LENGTH = 32
BCRYPT_MAX_BYTES = 72


@dataclass(frozen=True)
class AdminSettings:
    jwt_secret: str
    username: str
    password_hash: str
    expire_minutes: int = 30


def load_admin_settings(env: Mapping[str, str] = os.environ) -> AdminSettings | None:
    """None — адмінку не налаштовано (ендпоінти запису → 503). Налаштовано погано — RuntimeError при старті."""
    secret, password_hash = env.get("JWT_SECRET", ""), env.get("ADMIN_PASSWORD_HASH", "")
    if not secret and not password_hash:
        return None
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(f"JWT_SECRET має бути не коротшим за {MIN_SECRET_LENGTH} символи; "
                           "згенеруй: python -m news_hub.security")
    if not password_hash.startswith("$2"):
        raise RuntimeError("ADMIN_PASSWORD_HASH — bcrypt-хеш ($2b$…), а не пароль; "
                           "згенеруй: python -m news_hub.security")
    return AdminSettings(jwt_secret=secret, username=env.get("ADMIN_USERNAME", "admin"),
                         password_hash=password_hash,
                         expire_minutes=int(env.get("JWT_EXPIRE_MINUTES", "30")))


# ---------------------------------------------------------------------------
# Пароль
# ---------------------------------------------------------------------------

def hash_password(password: str, rounds: int = 12) -> str:
    """bcrypt: сіль у самому хеші, 2^rounds ітерацій — навмисно повільно (~0,2 с при 12)."""
    data = password.encode()
    if len(data) > BCRYPT_MAX_BYTES:
        raise ValueError(f"пароль довший за {BCRYPT_MAX_BYTES} байти: bcrypt його не прийме")
    return bcrypt.hashpw(data, bcrypt.gensalt(rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    data = password.encode()
    if len(data) > BCRYPT_MAX_BYTES:        # bcrypt ≥ 5 кидає ValueError — для нас це просто «не той пароль»
        return False
    return bcrypt.checkpw(data, password_hash.encode())


def authenticate(settings: AdminSettings, username: str, password: str) -> bool:
    name_ok = hmac.compare_digest(username.encode(), settings.username.encode())
    password_ok = verify_password(password, settings.password_hash)     # завжди — однаковий час
    return name_ok and password_ok


# ---------------------------------------------------------------------------
# Токен
# ---------------------------------------------------------------------------

def create_access_token(settings: AdminSettings, subject: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    payload = {"sub": subject, "role": "admin", "iat": now,
               "exp": now + timedelta(minutes=settings.expire_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_token(settings: AdminSettings, token: str) -> dict[str, Any]:
    """Підпис, строк дії і обов'язкові поля. Помилки — jwt.ExpiredSignatureError / jwt.InvalidTokenError."""
    payload: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM],
                                         options={"require": ["exp", "sub", "role"]})
    return payload


# ---------------------------------------------------------------------------
# Залежності FastAPI
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False, description="POST /api/admin/token → access_token")


def get_admin_settings(request: Request) -> AdminSettings:
    settings: AdminSettings | None = request.app.state.admin
    if settings is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="адмін-доступ не налаштовано: задай JWT_SECRET і ADMIN_PASSWORD_HASH")
    return settings


AdminSettingsDep = Annotated[AdminSettings, Depends(get_admin_settings)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def require_admin(settings: AdminSettingsDep,
                  credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]) -> str:
    """401 — немає токена, підроблений чи прострочений; 403 — токен справжній, але не адміна."""
    if credentials is None:
        raise _unauthorized("потрібен токен: Authorization: Bearer <access_token>")
    try:
        payload = decode_token(settings, credentials.credentials)
    except jwt.ExpiredSignatureError as error:
        raise _unauthorized("токен прострочений") from error
    except jwt.InvalidTokenError as error:
        raise _unauthorized("недійсний токен") from error
    if payload["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="потрібні права адміністратора")
    subject: str = payload["sub"]
    return subject


AdminDep = Depends(require_admin)


def env_lines(password: str, quoted: bool = True) -> list[str]:
    """Рядки ADMIN_PASSWORD_HASH і JWT_SECRET.

    quoted=True — для `export` у shell і `.env` Compose: у хеші є `$`, одинарні лапки не дають його підставити.
    quoted=False — для `docker run --env-file` (урок 48): там значення береться буквально, разом з лапками,
    і хеш у лапках уже не хеш — застосунок не стартує.
    """
    q = "'" if quoted else ""
    return [f"ADMIN_PASSWORD_HASH={q}{hash_password(password)}{q}", f"JWT_SECRET={q}{secrets.token_urlsafe(48)}{q}"]


def main(argv: list[str] | None = None) -> None:
    """python -m news_hub.security [--env-file] → рядки для .env: хеш пароля і випадковий секрет JWT."""
    parser = argparse.ArgumentParser(description="Хеш пароля адміна й секрет JWT для змінних середовища")
    parser.add_argument("--env-file", action="store_true", help="без лапок — для docker run --env-file")
    args = parser.parse_args(argv)
    password = getpass.getpass("Пароль адміністратора: ")
    print("\n".join(env_lines(password, quoted=not args.env_file)))


if __name__ == "__main__":
    main()
