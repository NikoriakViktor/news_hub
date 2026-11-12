"""Розсилка дайджесту: відправник приходить параметром — у тесті передаємо підміну."""
from pathlib import Path

from .mail import Mailer


def send_digest(subscribers: list[str], titles: list[str], mailer: Mailer) -> dict[str, list[str]]:
    """Лист кожному підписнику; збій одного не зупиняє інших. Немає новин — листів немає."""
    report: dict[str, list[str]] = {"sent": [], "failed": []}
    if not titles:
        return report
    body = "\n".join(f"• {title}" for title in titles)
    for email in subscribers:
        try:
            mailer.send(email, subject=f"Дайджест новин: {len(titles)}", body=body)
        except ConnectionError:
            report["failed"].append(email)
        else:
            report["sent"].append(email)
    return report


def write_digest(path: Path, titles: list[str]) -> int:
    """Дайджест у файл (UTF-8, рядок на новину); повертає кількість рядків."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{title}\n" for title in titles), encoding="utf-8")
    return len(titles)
