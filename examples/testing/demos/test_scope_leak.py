"""Змінюваний об'єкт у фікстурі з scope="module": тести залежать від порядку.

pytest demos/test_scope_leak.py                       → другий тест червоний
pytest demos/test_scope_leak.py -k second             → той самий тест окремо зелений
"""
import pytest

from newsapp.digest import send_digest
from tests.fakes import FakeMailer


@pytest.fixture(scope="module")
def mailer() -> FakeMailer:
    return FakeMailer()                               # один outbox на всі тести модуля


def test_first_digest(mailer: FakeMailer) -> None:
    send_digest(["olena@example.com"], ["Новина"], mailer)
    assert mailer.sent_to() == ["olena@example.com"]


def test_second_digest(mailer: FakeMailer) -> None:
    send_digest(["taras@example.com"], ["Новина"], mailer)
    assert mailer.sent_to() == ["taras@example.com"]
