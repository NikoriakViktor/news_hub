"""Урок 46: хто може писати. Читання — будь-хто; запис, збір, аналіз, джерела — лише адмін з JWT."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from news_hub.api import app
from news_hub.security import AdminSettings, create_access_token, load_admin_settings, require_admin

from .conftest import ADMIN_PASSWORD

# Єдині ендпоінти без токена адміна. Новий ендпоінт сюди не потрапить сам: або AdminDep, або рішення тут.
PUBLIC = {
    ("GET", "/health"), ("GET", "/api/news"), ("GET", "/api/news/search"), ("GET", "/api/news/count"),
    ("GET", "/api/news/stats"), ("GET", "/api/news/{news_id}"),
    ("POST", "/api/admin/token"),                   # вхід — пароль
    ("POST", "/api/webhooks/scrape"),               # свій захист — підпис HMAC (test_webhooks_api.py)
    ("POST", "/api/telegram/webhook"),              # урок 47: свій захист — секретний заголовок Telegram
}


def admin_protected(route: APIRoute) -> bool:
    stack = list(route.dependant.dependencies)
    while stack:
        dependency = stack.pop()
        if dependency.call is require_admin:
            return True
        stack.extend(dependency.dependencies)
    return False


def endpoints() -> list[tuple[str, str, APIRoute]]:
    return [(method, route.path, route) for route in app.routes if isinstance(route, APIRoute)
            for method in sorted(route.methods)]


def test_every_other_endpoint_requires_admin() -> None:
    unprotected = {(method, path) for method, path, route in endpoints() if not admin_protected(route)}
    assert unprotected == PUBLIC


@pytest.mark.parametrize(("method", "path"), sorted({(m, p) for m, p, _ in endpoints()} - PUBLIC))
def test_anonymous_gets_401(anon: TestClient, method: str, path: str) -> None:
    url = path.replace("{news_id}", "1").replace("{job_id}", "abc").replace("{source_id}", "1")
    response = anon.request(method, url, json={})
    assert response.status_code == 401, response.text
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_anonymous_cannot_wipe_the_database(anon: TestClient) -> None:
    anon.post("/api/scrape", json={"source": "snapshot"}, headers=_token_headers())     # адмін зібрав новини
    assert anon.delete("/api/news").status_code == 401
    assert anon.get("/api/news/count").json() == {"count": 168}          # читати — можна, стерти — ні


def _settings() -> AdminSettings:
    settings = load_admin_settings()
    assert settings is not None
    return settings


def _token_headers(token: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or create_access_token(_settings(), 'admin')}"}


def test_login_and_use_token(anon: TestClient) -> None:
    response = anon.post("/api/admin/token", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert (body["token_type"], body["expires_in"]) == ("bearer", 1800)
    headers = _token_headers(body["access_token"])
    assert anon.post("/api/scrape", json={"source": "snapshot"}, headers=headers).status_code == 200


@pytest.mark.parametrize(("username", "password"), [
    ("admin", "wrong"), ("root", ADMIN_PASSWORD), ("admin", "я" * 100), ("", ""),
])
def test_bad_login_is_one_answer(anon: TestClient, username: str, password: str) -> None:
    """Однакова відповідь для чужого імені й чужого пароля; довгий пароль — 401, а не 500."""
    response = anon.post("/api/admin/token", json={"username": username, "password": password})
    assert (response.status_code, response.json()) == (401, {"detail": "неправильне ім'я або пароль"})


def test_login_brute_force_is_rate_limited(anon: TestClient) -> None:
    codes = [anon.post("/api/admin/token", json={"username": "admin", "password": f"guess-{i}"}).status_code
             for i in range(7)]
    assert codes == [401] * 5 + [429, 429]
    right = anon.post("/api/admin/token", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert right.status_code == 429                  # навіть правильний пароль — після вікна
    assert int(right.headers["Retry-After"]) > 0


def test_expired_token_is_401(anon: TestClient) -> None:
    old = create_access_token(_settings(), "admin", now=datetime.now(timezone.utc) - timedelta(hours=1))
    response = anon.delete("/api/news", headers=_token_headers(old))
    assert (response.status_code, response.json()["detail"]) == (401, "токен прострочений")


def test_unsigned_token_is_401(anon: TestClient) -> None:
    """alg: none — «підпис не потрібен»: бібліотека з algorithms=["HS256"] такий токен не приймає."""
    unsigned = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9."
    response = anon.delete("/api/news", headers=_token_headers(unsigned))
    assert (response.status_code, response.json()["detail"]) == (401, "недійсний токен")


def test_valid_token_without_admin_role_is_403(anon: TestClient) -> None:
    settings = _settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    user_token = jwt.encode({"sub": "reader", "role": "user", "exp": exp}, settings.jwt_secret, algorithm="HS256")
    assert anon.delete("/api/news", headers=_token_headers(user_token)).status_code == 403


def test_not_configured_is_503(anon: TestClient) -> None:
    saved, app.state.admin = app.state.admin, None
    try:
        assert anon.delete("/api/news", headers={"Authorization": "Bearer x"}).status_code == 503
        assert anon.post("/api/admin/token", json={"username": "a", "password": "b"}).status_code == 503
        assert anon.get("/api/news").status_code == 200                  # читання працює й так
    finally:
        app.state.admin = saved


def test_swagger_has_authorize_button(anon: TestClient) -> None:
    schema = anon.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert schema["paths"]["/api/news"]["delete"]["security"] == [{"HTTPBearer": []}]
    assert "security" not in schema["paths"]["/api/news"]["get"]
