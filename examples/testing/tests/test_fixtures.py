"""Фікстури: scope і порядок, yield, tmp_path, monkeypatch, фабрика, вбудовані capsys."""
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from newsapp import digest
from newsapp.mail import SmtpMailer
from newsapp.storage import Article, ArticleRepo

EVENTS: list[str] = []


@pytest.fixture(scope="module")
def expensive() -> Iterator[str]:
    """Дорога підготовка (з'єднання, сервер) — раз на модуль."""
    EVENTS.clear()                           # той самий процес може зібрати модуль ще раз (mutmut, IDE)
    EVENTS.append("module: setup")
    yield "ресурс"
    EVENTS.append("module: teardown")


@pytest.fixture
def per_test(expensive: str) -> Iterator[str]:
    """Фікстура може просити іншу фікстуру — як тест."""
    EVENTS.append("function: setup")
    yield f"дані поверх «{expensive}»"
    EVENTS.append("function: teardown")      # виконується, навіть якщо тест упав


def test_first(per_test: str) -> None:
    assert per_test == "дані поверх «ресурс»"
    assert EVENTS[-1] == "function: setup"


def test_second(per_test: str) -> None:
    assert EVENTS[-1] == "function: setup"
    assert EVENTS.count("module: setup") == 1          # module-фікстуру створено один раз на модуль


def test_write_digest_to_tmp_path(tmp_path: Path) -> None:
    path = tmp_path / "out" / "digest.txt"               # окрема папка для кожного тесту
    assert digest.write_digest(path, ["Перша", "Друга"]) == 2
    assert path.read_text(encoding="utf-8") == "Перша\nДруга\n"


def test_env_via_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "mail.test")
    monkeypatch.delenv("SMTP_PORT", raising=False)
    mailer = SmtpMailer()
    assert (mailer.host, mailer.port) == ("mail.test", 2525)


def test_env_is_restored_after_monkeypatch() -> None:
    assert SmtpMailer().host != "mail.test"             # попередній тест нічого не залишив


def test_attribute_via_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(digest, "send_digest", lambda *args: {"sent": ["усім"], "failed": []})
    assert digest.send_digest([], [], None) == {"sent": ["усім"], "failed": []}


def test_factory_shows_only_what_matters(make_article: Callable[..., Article], db: Session) -> None:
    make_article()
    make_article(title="Уряд ухвалив бюджет")
    make_article()
    assert [a.title for a in ArticleRepo(db).search("бюджет")] == ["Уряд ухвалив бюджет"]


def test_capsys_captures_print(capsys: pytest.CaptureFixture[str]) -> None:
    print("надіслано 2 листи")
    assert capsys.readouterr().out == "надіслано 2 листи\n"
