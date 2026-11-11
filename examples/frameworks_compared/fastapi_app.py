"""Нотатки на FastAPI: перевірку робить Pydantic за анотаціями типів."""
from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI(title="Notes")
NOTES: list[dict] = []


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    priority: int = Field(1, ge=1, le=4)


@app.get("/api/notes")
def list_notes(limit: int = Query(10, ge=1, le=100)) -> list[dict]:
    return NOTES[:limit]


@app.post("/api/notes", status_code=201)
def create_note(note: NoteIn) -> dict:
    NOTES.append({"id": len(NOTES) + 1, **note.model_dump()})
    return NOTES[-1]
