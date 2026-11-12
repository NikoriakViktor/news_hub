"""Зовнішня межа: пошта. Справжній відправник ходить по SMTP — у тестах його підміняють."""
import os
import smtplib
from email.message import EmailMessage
from typing import Protocol


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> str:
        """Надсилає лист; повертає id повідомлення. Збій мережі — ConnectionError."""
        ...


class SmtpMailer:
    """Справжній відправник: кожен лист — з'єднання з SMTP-сервером."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        # налаштування читаються при створенні, а не при імпорті — тест може задати їх monkeypatch.setenv
        self.host = host or os.getenv("SMTP_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("SMTP_PORT", "2525"))     # у прикладі SMTP-сервера немає

    def send(self, to: str, subject: str, body: str) -> str:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = "news@example.com", to, subject
        message.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=5) as smtp:     # ConnectionRefusedError ⊂ ConnectionError
            smtp.send_message(message)
        return message["Message-ID"] or to


def send_email(to: str, subject: str, body: str) -> str:
    """Функція модуля — її імпортують інші модулі (alerts.py): приклад для patch where used."""
    return SmtpMailer().send(to, subject, body)
