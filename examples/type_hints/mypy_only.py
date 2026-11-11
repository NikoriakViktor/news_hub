"""Помилки, які бачить лише mypy: python mypy_only.py пройде, mypy --strict mypy_only.py — ні.

    mypy --strict mypy_only.py
"""
from typing import Annotated, Literal, Protocol

from pydantic import Field
from typing_extensions import TypedDict

Status = Literal["todo", "in_progress", "done"]


class Point(TypedDict):
    x: int
    y: int


class Notifier(Protocol):
    def send(self, text: str) -> None: ...


class EmailNotifier:
    def send(self, text: str, to: str) -> None:      # зайвий обов'язковий параметр — уже не Notifier
        print(f"{to}: {text}")


def notify(notifier: Notifier) -> None:
    notifier.send("готово")


def set_status(status: Status) -> None:
    print("status:", status)


def first_letter(name: str | None) -> str:
    return name[0]                                   # name може бути None


def label(status: Status) -> str:
    if status == "todo":
        return "до роботи"
    elif status == "in_progress":
        return "в роботі"
    # "done" забули: функція поверне None


Title = Annotated[str, Field(min_length=3)]
bad_title: Title = 42                                # для mypy Annotated[str, ...] — просто str; Field тут нічого не перевіряє


def shout(title: Title) -> str:
    return title.upper()


point: Point = {"x": 1, "yy": 2}                     # одруківка в ключі
set_status("archived")                               # не з Literal
print("рантайм пройшов до кінця:", point, label("done"))
notify(EmailNotifier())                              # падає лише тут, у рантаймі: TypeError
