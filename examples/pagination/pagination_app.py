"""Статті й коментарі: фільтр, сортування з білим списком, offset/limit і курсор, вкладений ресурс.

    python pagination_demo.py        # сценарії й виміри
"""
import base64
import json
import os
from collections.abc import Iterator
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import ForeignKey, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

engine = create_engine(os.getenv("DB_URL", "sqlite:///pagination.db"))   # файл, а не :memory: — див. «Методи HTTP»


class Base(DeclarativeBase):
    pass


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), index=True)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    text: Mapped[str] = mapped_column(String(500))


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    category: str


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    post_id: int
    text: str


class Page(BaseModel):
    items: list[PostOut]
    next_cursor: str | None          # None — це остання сторінка


def get_db() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


Db = Annotated[Session, Depends(get_db)]
app = FastAPI(title="Pagination")
SORT_COLUMNS = {"id": Post.id, "title": Post.title}                     # білий список полів для сортування


@app.get("/posts")
def list_posts(
    db: Db,
    category: str | None = None,
    sort: Literal["id", "-id", "title", "-title"] = "-id",               # «-» — за спаданням
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[PostOut]:
    column = SORT_COLUMNS[sort.lstrip("-")]
    order = column.desc() if sort.startswith("-") else column.asc()
    tiebreak = Post.id.desc() if sort.startswith("-") else Post.id.asc()  # однакові title — порядок за id
    stmt = select(Post).order_by(order, tiebreak).offset(offset).limit(limit)
    if category:
        stmt = stmt.where(Post.category == category)
    return [PostOut.model_validate(p) for p in db.scalars(stmt)]


def encode_cursor(post: Post) -> str:
    return base64.urlsafe_b64encode(json.dumps({"id": post.id}).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(json.loads(base64.urlsafe_b64decode(cursor))["id"])
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(400, "недійсний cursor") from error


@app.get("/posts/feed")
def feed(
    db: Db,
    cursor: str | None = None,
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> Page:
    """Новіші першими. Курсор — «після якого запису продовжити», а не «скільки пропустити»."""
    stmt = select(Post).order_by(Post.id.desc()).limit(limit + 1)        # +1: чи є наступна сторінка
    if cursor:
        stmt = stmt.where(Post.id < decode_cursor(cursor))     # «після» = id менший за останній показаний
    if category:
        stmt = stmt.where(Post.category == category)
    rows = list(db.scalars(stmt))
    items, more = rows[:limit], len(rows) > limit
    return Page(items=[PostOut.model_validate(p) for p in items],
                next_cursor=encode_cursor(items[-1]) if more else None)


@app.get("/posts/{post_id}/comments/{comment_id}")
def read_comment(post_id: int, comment_id: int, db: Db) -> CommentOut:
    comment = db.scalar(select(Comment).where(Comment.id == comment_id, Comment.post_id == post_id))
    if comment is None:                        # чужий коментар — теж 404, а не дані іншого поста
        raise HTTPException(404, "Comment not found")
    return CommentOut.model_validate(comment)
