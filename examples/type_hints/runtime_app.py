"""Які анотації FastAPI і Pydantic читають під час роботи програми.

    python runtime_demo.py
"""
from typing import Annotated, Any, Literal, Protocol

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, Field
from typing_extensions import TypedDict      # Pydantic приймає TypedDict з typing лише на Python 3.12+

Status = Literal["todo", "in_progress", "done"]


class TaskIn(BaseModel):
    title: Annotated[str, Field(min_length=3)]   # Annotated: тип для mypy + обмеження для Pydantic
    status: Status
    priority: str | None = None                  # можна не передавати, можна передати null
    due: str | None                              # можна передати null, але НЕ можна не передати
    tags: list[str] = []


class TaskOut(BaseModel):
    id: int
    title: str
    status: Status


class Point(TypedDict):
    x: int
    y: int


class Notifier(Protocol):
    def send(self, text: str) -> None: ...


class PrintNotifier:                              # не наслідує Notifier — підходить за формою
    def send(self, text: str) -> None:
        print("   notifier:", text)


def get_notifier() -> Notifier:
    return PrintNotifier()


app = FastAPI()
TASKS: list[dict[str, Any]] = []


@app.post("/tasks", status_code=201)
def create_task(task: TaskIn, notifier: Annotated[Notifier, Depends(get_notifier)]) -> TaskOut:
    row = {"id": len(TASKS) + 1, **task.model_dump(), "secret": "internal"}
    TASKS.append(row)
    notifier.send(f"нова задача {task.title!r}")
    return row                                   # type: ignore[return-value]  # FastAPI сам зробить TaskOut


@app.get("/tasks")
def list_tasks(status: Status | None = None,
               limit: Annotated[int, Query(ge=1, le=50)] = 10) -> list[TaskOut]:
    return [TaskOut(**t) for t in TASKS if status in (None, t["status"])][:limit]


@app.get("/raw")
def raw_tasks() -> list[dict[str, Any]]:                # тип відповіді без схеми: віддасть усе, що є
    return TASKS


@app.post("/points")
def move(point: Point) -> Point:
    return {"x": point["x"] + 1, "y": point["y"] + 1}
