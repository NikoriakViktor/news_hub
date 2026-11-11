"""Урок 46: пароль, JWT і налаштування адміна — без бази й HTTP."""
import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from news_hub.security import (AdminSettings, authenticate, create_access_token, decode_token, env_lines,
                               hash_password, load_admin_settings, verify_password)

SECRET = "s" * 64
SETTINGS = AdminSettings(jwt_secret=SECRET, username="admin", password_hash=hash_password("правильний", rounds=4))


def test_password_hash_is_salted_and_verifiable() -> None:
    first, second = hash_password("пароль", rounds=4), hash_password("пароль", rounds=4)
    assert first != second and first.startswith("$2b$04$")          # сіль — у кожного хешу своя
    assert verify_password("пароль", first) and not verify_password("Пароль", first)


def test_password_longer_than_72_bytes_is_wrong_not_500() -> None:
    """bcrypt ≥ 5 кидає ValueError на > 72 байти; для входу це просто «не той пароль»."""
    assert verify_password("я" * 100, SETTINGS.password_hash) is False
    with pytest.raises(ValueError, match="72"):
        hash_password("я" * 37)                                          # 74 байти UTF-8


@pytest.mark.parametrize(("username", "password", "ok"), [
    ("admin", "правильний", True),
    ("admin", "неправильний", False),
    ("root", "правильний", False),
    ("admin ", "правильний", False),
])
def test_authenticate(username: str, password: str, ok: bool) -> None:
    assert authenticate(SETTINGS, username, password) is ok


def test_token_roundtrip() -> None:
    payload = decode_token(SETTINGS, create_access_token(SETTINGS, "admin"))
    assert (payload["sub"], payload["role"]) == ("admin", "admin")
    assert payload["exp"] - payload["iat"] == 30 * 60


def test_expired_token() -> None:
    old = create_access_token(SETTINGS, "admin", now=datetime.now(timezone.utc) - timedelta(hours=1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(SETTINGS, old)


def _b64(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def forged_tokens() -> dict[str, str]:
    exp = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())
    claims = {"sub": "admin", "role": "admin", "exp": exp}
    good = create_access_token(SETTINGS, "admin")
    header, _, signature = good.split(".")
    return {
        "інший секрет": jwt.encode(claims, "x" * 64, algorithm="HS256"),
        "alg none": f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}.",
        "HS512 тим самим секретом": jwt.encode(claims, SECRET, algorithm="HS512"),
        "змінений payload": f"{header}.{_b64({**claims, 'sub': 'hacker'})}.{signature}",
        "без role": jwt.encode({"sub": "admin", "exp": exp}, SECRET, algorithm="HS256"),
        "без exp": jwt.encode({"sub": "admin", "role": "admin"}, SECRET, algorithm="HS256"),
        "не JWT": "abc.def",
    }


@pytest.mark.parametrize("case", list(forged_tokens()))
def test_forged_tokens_are_rejected(case: str) -> None:
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(SETTINGS, forged_tokens()[case])


def test_settings_from_env() -> None:
    assert load_admin_settings({}) is None                               # не налаштовано → 503, а не «change-me»
    good = {"JWT_SECRET": SECRET, "ADMIN_PASSWORD_HASH": SETTINGS.password_hash}
    assert load_admin_settings(good) == AdminSettings(SECRET, "admin", SETTINGS.password_hash)
    for bad in ({**good, "JWT_SECRET": "change-me-in-production"}, {**good, "JWT_SECRET": ""},
                {**good, "ADMIN_PASSWORD_HASH": "change-me"}, {"ADMIN_PASSWORD_HASH": SETTINGS.password_hash}):
        with pytest.raises(RuntimeError):
            load_admin_settings(bad)


@pytest.mark.parametrize("quoted", [True, False])
def test_env_lines_give_a_working_hash(monkeypatch: pytest.MonkeyPatch, quoted: bool) -> None:
    """Урок 48: `docker run --env-file` бере значення буквально — з лапками хеш не пройде перевірку."""
    monkeypatch.setattr("news_hub.security.hash_password", lambda password: bcrypt_hash(password))
    lines = env_lines("s3cret", quoted=quoted)
    literal = dict(line.split("=", 1) for line in lines)             # як читає docker run --env-file
    settings = load_admin_settings({"JWT_SECRET": literal["JWT_SECRET"].strip("'"),
                                    "ADMIN_PASSWORD_HASH": literal["ADMIN_PASSWORD_HASH"].strip("'")})
    assert settings is not None and authenticate(settings, "admin", "s3cret")
    if quoted:
        with pytest.raises(RuntimeError, match="bcrypt"):                # лапки лишились у значенні
            load_admin_settings(literal)
    else:
        assert load_admin_settings(literal) is not None


def bcrypt_hash(password: str) -> str:
    return hash_password(password, rounds=4)


def test_truncated_hash_fails_at_startup() -> None:
    """Урок 49: Compose підставляє `$змінні` у .env без лапок — від хешу лишається «$2b$12».

    Раніше це проходило перевірку «починається з $2», застосунок стартував, а вхід адміна відповідав 500.
    """
    full = bcrypt_hash("s3cret")
    truncated = full[:6]                                              # "$2b$04" — як після підстановки
    with pytest.raises(RuntimeError, match="одинарних лапках"):
        load_admin_settings({"JWT_SECRET": SECRET, "ADMIN_PASSWORD_HASH": truncated})
    assert load_admin_settings({"JWT_SECRET": SECRET, "ADMIN_PASSWORD_HASH": full}) is not None
