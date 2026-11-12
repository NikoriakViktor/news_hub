"""Підміни (test doubles): dummy, stub, mock, spy, fake; patch where used; autospec."""
from unittest import mock

import pytest

from newsapp import alerts
from newsapp.digest import send_digest
from newsapp.mail import SmtpMailer
from tests.fakes import FakeMailer

READERS = ["olena@example.com", "taras@example.com"]


def test_dummy_is_never_touched() -> None:
    """Dummy — лише щоб заповнити параметр. spec=[]: будь-яке звернення до атрибута — AttributeError."""
    assert send_digest(READERS, [], mailer=mock.Mock(spec=[])) == {"sent": [], "failed": []}


def test_stub_gives_canned_answer() -> None:
    """Stub — готова відповідь; що з ним робили, тест не питає."""
    class AlwaysOk:
        def send(self, to: str, subject: str, body: str) -> str:
            return "id-1"

    assert send_digest(READERS, ["Новина"], AlwaysOk())["sent"] == READERS


def test_mock_records_calls() -> None:
    """Mock — запам'ятовує виклики; тест перевіряє, ЯК код ним скористався."""
    mailer = mock.Mock()
    send_digest(["olena@example.com"], ["Перша", "Друга"], mailer)
    mailer.send.assert_called_once_with("olena@example.com", subject="Дайджест новин: 2", body="• Перша\n• Друга")


def test_side_effect_sequence() -> None:
    """side_effect — список: перший виклик кидає виняток, другий повертає значення."""
    mailer = mock.Mock()
    mailer.send.side_effect = [ConnectionError("таймаут"), "id-2"]
    assert send_digest(READERS, ["Новина"], mailer) == {"sent": READERS[1:], "failed": READERS[:1]}
    assert mailer.send.call_count == 2


def test_spy_wraps_real_object() -> None:
    """Spy — справжня поведінка (тут — фейку) плюс запис викликів."""
    fake = FakeMailer()
    spy = mock.Mock(wraps=fake)
    send_digest(READERS, ["Новина"], spy)
    assert fake.sent_to() == READERS                          # листи справді «пішли»
    assert [c.args[0] for c in spy.send.call_args_list] == READERS


def test_fake_has_state_and_rules() -> None:
    """Fake — робоча спрощена реалізація: пам'ятає листи, уміє «падати» для окремих адрес."""
    fake = FakeMailer(down={"taras@example.com"})
    report = send_digest(READERS, ["Новина"], fake)
    assert report == {"sent": ["olena@example.com"], "failed": ["taras@example.com"]}
    assert fake.outbox == [("olena@example.com", "Дайджест новин: 1", "• Новина")]


def test_patch_where_used() -> None:
    """alerts.py робить `from .mail import send_email` — патчимо ім'я в alerts, а не в mail."""
    with mock.patch("newsapp.alerts.send_email", return_value="id-7") as fake_send:
        assert alerts.alert_editor("Уряд ухвалив бюджет") == "id-7"
    fake_send.assert_called_once_with("editor@example.com", subject="Терміново", body="Уряд ухвалив бюджет")


@mock.patch.object(alerts, "EDITOR", "night-editor@example.com")
@mock.patch("newsapp.alerts.send_email")
def test_patch_as_decorator(fake_send: mock.Mock) -> None:
    """Декоратори застосовуються знизу вгору; patch.object з новим значенням аргумент не додає."""
    alerts.alert_editor("Вночі")
    assert fake_send.call_args.args == ("night-editor@example.com",)


def test_plain_mock_accepts_any_call() -> None:
    """Звичайний Mock не знає справжнього інтерфейсу: одруківка в аргументі — і жодної помилки."""
    mailer = mock.Mock()
    mailer.send("olena@example.com", subjekt="Дайджест")       # у SmtpMailer.send немає subjekt
    mailer.sned("olena@example.com")                          # і методу sned теж немає
    assert mailer.send.called and mailer.sned.called


def test_autospec_checks_the_real_signature() -> None:
    mailer = mock.create_autospec(SmtpMailer, instance=True)
    with pytest.raises(TypeError, match="missing a required argument: 'subject'"):
        mailer.send("olena@example.com", subjekt="Дайджест")
    with pytest.raises(AttributeError, match="sned"):
        mailer.sned("olena@example.com")


def test_misspelled_assert_is_an_error() -> None:
    """Одруківка в assert-методі — AttributeError, а не «зелений» тест (assert*, assret*, asert*, called_once*)."""
    mailer = mock.Mock()
    with pytest.raises(AttributeError, match="is not a valid assertion"):
        mailer.send.assert_called_onse()
