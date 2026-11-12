"""Відправник імпортовано іменем: щоб підмінити його в тесті, патчать newsapp.alerts.send_email."""
from .mail import send_email

EDITOR = "editor@example.com"


def alert_editor(title: str) -> str:
    """Термінова новина → лист редактору. Повертає id листа."""
    return send_email(EDITOR, subject="Терміново", body=title)
