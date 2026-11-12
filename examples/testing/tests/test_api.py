"""API через TestClient: dependency_overrides, lifespan, 404/409/422/500, middleware."""
import pytest
from fastapi.testclient import TestClient

from newsapp.api import app, get_mailer
from newsapp.mail import SmtpMailer
from tests.fakes import FakeMailer

BUDGET = {"title": "Уряд ухвалив бюджет", "source": "rbc.ua"}


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_create_then_get(client: TestClient) -> None:
    created = client.post("/articles", json=BUDGET)
    assert created.status_code == 201
    assert created.json() == {"slug": "уряд-ухвалив-бюджет", **BUDGET}
    assert client.get("/articles/уряд-ухвалив-бюджет").json()["title"] == BUDGET["title"]


def test_unknown_slug_is_404(client: TestClient) -> None:
    response = client.get("/articles/немає-такої")
    assert (response.status_code, response.json()) == (404, {"detail": "новину не знайдено"})


@pytest.mark.parametrize(("body", "loc"), [
    ({"title": "Коро", "source": "rbc.ua"}, ["body", "title"]),           # min_length=5
    ({"title": "Уряд ухвалив бюджет", "source": "x" * 21}, ["body", "source"]),
    ({"title": "Уряд ухвалив бюджет"}, ["body", "source"]),               # поля немає
], ids=["short-title", "long-source", "missing-source"])
def test_invalid_body_is_422(client: TestClient, body: dict[str, str], loc: list[str]) -> None:
    response = client.post("/articles", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == loc


def test_title_without_words_is_422_not_500(client: TestClient) -> None:
    response = client.post("/articles", json={"title": "?!?!?", "source": "rbc.ua"})
    assert (response.status_code, response.json()["detail"]) == (422, "у заголовку немає слів: '?!?!?'")


def test_duplicate_is_409_and_first_survives(client: TestClient) -> None:
    assert client.post("/articles", json=BUDGET).status_code == 201
    assert client.post("/articles", json=BUDGET).status_code == 409
    assert client.get("/articles/уряд-ухвалив-бюджет").status_code == 200    # ROLLBACK не зачепив першу


def test_search_ignores_case_in_cyrillic(client: TestClient) -> None:
    client.post("/articles", json=BUDGET)
    assert [a["slug"] for a in client.get("/articles", params={"q": "БЮДЖЕТ"}).json()] == ["уряд-ухвалив-бюджет"]


def test_digest_goes_through_fake_mailer(client: TestClient, mailer: FakeMailer) -> None:
    client.post("/articles", json=BUDGET)
    report = client.post("/digest", json={"subscribers": ["olena@example.com"]}).json()
    assert report == {"sent": ["olena@example.com"], "failed": []}
    assert mailer.outbox[0][2] == "• Уряд ухвалив бюджет"


class BrokenMailer:
    def send(self, to: str, subject: str, body: str) -> str:
        raise RuntimeError("SMTP пароль: hunter2")        # не ConnectionError — send_digest не ловить


def test_unexpected_error_is_500_without_details(client: TestClient) -> None:
    app.dependency_overrides[get_mailer] = BrokenMailer
    client.post("/articles", json=BUDGET)
    quiet = TestClient(app, raise_server_exceptions=False)        # відповідь 500, а не виняток у тесті
    response = quiet.post("/digest", json={"subscribers": ["olena@example.com"]})
    assert (response.status_code, response.text) == (500, "Internal Server Error")
    assert "hunter2" not in response.text
    assert "X-Request-ID" not in response.headers      # 500 формує ServerErrorMiddleware — зовні нашого middleware


@pytest.mark.parametrize(("sent", "kept"), [
    ("abc-123", True),
    ("", False),                              # немає — генеруємо
    ("x" * 65, False),                        # задовгий
    ("<script>alert(1)</script>", False),     # потрапив би в журнали як є
], ids=["valid", "missing", "too-long", "unsafe-chars"])
def test_request_id_middleware(client: TestClient, sent: str, kept: bool) -> None:
    rid = client.get("/health", headers={"X-Request-ID": sent}).headers["X-Request-ID"]
    if kept:
        assert rid == sent
    else:
        assert rid != sent and len(rid) == 32


def test_lifespan_creates_real_dependencies() -> None:
    """Без підмін: справжній lifespan, справжній get_db (SQLite у пам'яті застосунку)."""
    with TestClient(app) as c:
        assert isinstance(app.state.mailer, SmtpMailer)
        assert c.post("/articles", json=BUDGET).status_code == 201
        assert c.get("/articles/уряд-ухвалив-бюджет").status_code == 200     # COMMIT справжнього get_db
    with TestClient(app) as c:                                                    # новий старт — нова база
        assert c.get("/articles/уряд-ухвалив-бюджет").status_code == 404
