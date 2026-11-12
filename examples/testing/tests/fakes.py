"""Фейки: справжні, але спрощені реалізації зовнішніх меж."""


class FakeMailer:
    """Пошта в пам'яті: листи — у outbox; адреси з `down` «не відповідають» (ConnectionError)."""

    def __init__(self, down: set[str] | None = None) -> None:
        self.outbox: list[tuple[str, str, str]] = []
        self.down = down or set()

    def send(self, to: str, subject: str, body: str) -> str:
        if to in self.down:
            raise ConnectionError(f"{to}: сервер не відповідає")
        self.outbox.append((to, subject, body))
        return f"fake-{len(self.outbox)}"

    def sent_to(self) -> list[str]:
        return [to for to, _, _ in self.outbox]
