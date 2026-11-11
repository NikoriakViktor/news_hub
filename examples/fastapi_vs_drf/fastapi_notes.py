"""Той самий API нотаток на FastAPI — для порівняння з DRF (урок 36).

Дані — у словнику в пам'яті: база для FastAPI — урок 39, вхід — урок 47.
FastAPI-гілка курсу (уроки 37–51) далі будує новинний агрегатор.

    uvicorn fastapi_notes:app --reload   →  http://127.0.0.1:8000/docs
"""
from typing import Optional

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

app = FastAPI(title="Notes API (FastAPI)")
NOTES: dict[int, dict] = {}


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = ""
    priority: int = Field(1, ge=1, le=4)
    is_pinned: bool = False


class NotePatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=4)
    is_pinned: Optional[bool] = None


class NoteOut(NoteIn):
    id: int


@app.get("/api/notes/", response_model=list[NoteOut])
def list_notes(search: str = ""):
    notes = [note for note in NOTES.values() if search.lower() in note["title"].lower()]
    return sorted(notes, key=lambda note: (not note["is_pinned"], -note["priority"]))


@app.post("/api/notes/", status_code=201, response_model=NoteOut)
def create_note(body: NoteIn):
    note_id = max(NOTES, default=0) + 1
    NOTES[note_id] = {"id": note_id, **body.model_dump()}
    return NOTES[note_id]


@app.get("/api/notes/{note_id}/", response_model=NoteOut)
def get_note(note_id: int):
    if note_id not in NOTES:
        raise HTTPException(404, "Нотатку не знайдено.")
    return NOTES[note_id]


@app.patch("/api/notes/{note_id}/", response_model=NoteOut)
def patch_note(note_id: int, body: NotePatch):
    note = get_note(note_id)
    note.update(body.model_dump(exclude_unset=True))
    return note


@app.delete("/api/notes/{note_id}/", status_code=204)
def delete_note(note_id: int):
    get_note(note_id)
    del NOTES[note_id]
    return Response(status_code=204)


@app.post("/api/notes/{note_id}/pin/", response_model=NoteOut)
def pin_note(note_id: int):
    note = get_note(note_id)
    note["is_pinned"] = not note["is_pinned"]
    return note
