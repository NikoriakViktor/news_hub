"""Репозиторій на справжній базі: транзакція на тест, обмеження бази, відмінності SQLite і PostgreSQL."""
from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from newsapp.storage import Article, ArticleRepo


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Article)) or 0


@pytest.mark.parametrize("run", [1, 2])
def test_commit_in_test_is_still_rolled_back(db: Session, run: int) -> None:
    """Обидва запуски бачать порожню таблицю: COMMIT закрив лише SAVEPOINT, зовнішню транзакцію відкотить фікстура."""
    assert count(db) == 0
    ArticleRepo(db).add("Уряд ухвалив бюджет", "rbc.ua")
    db.commit()
    assert count(db) == 1


def test_duplicate_slug_violates_unique(db: Session, make_article: Callable[..., Article]) -> None:
    make_article(title="Уряд ухвалив бюджет")
    with pytest.raises(IntegrityError):
        make_article(title="Уряд ухвалив бюджет!")        # slug той самий: уряд-ухвалив-бюджет


def test_rollback_after_error_keeps_committed_data(db: Session, make_article: Callable[..., Article]) -> None:
    """Як ендпоінт POST /articles: перша новина закомічена, дубль → IntegrityError → rollback."""
    make_article(title="Уряд ухвалив бюджет")
    db.commit()
    with pytest.raises(IntegrityError):
        make_article(title="Уряд ухвалив бюджет")
    db.rollback()
    assert count(db) == 1


def test_search_is_case_insensitive_for_cyrillic(db: Session, make_article: Callable[..., Article]) -> None:
    make_article(title="Уряд ухвалив бюджет")
    assert [a.title for a in ArticleRepo(db).search("УРЯД")] == ["Уряд ухвалив бюджет"]


def test_search_treats_percent_literally(db: Session, make_article: Callable[..., Article]) -> None:
    make_article(title="Інфляція 5% за рік")
    make_article(title="Інфляція сповільнилась")
    assert [a.title for a in ArticleRepo(db).search("5%")] == ["Інфляція 5% за рік"]
    assert ArticleRepo(db).search("%") == [ArticleRepo(db).get("інфляція-5-за-рік")]


@pytest.mark.postgres
def test_too_long_source_is_rejected_by_database(db: Session, make_article: Callable[..., Article]) -> None:
    """VARCHAR(20): PostgreSQL відхиляє 21 символ. SQLite мовчки зберігає — тому тест лише для PostgreSQL."""
    with pytest.raises(DataError, match="too long"):
        make_article(source="x" * 21)
