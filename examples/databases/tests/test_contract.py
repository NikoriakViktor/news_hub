"""Контракт репозиторію: фейк і SqlNewsRepository мусять поводитися однаково."""
import pytest

from news_app.repositories import DuplicateUrl, NewsRepository


async def test_add_then_get(repo: NewsRepository) -> None:
    item = await repo.add("https://example.com/1", "Перша новина")
    assert item.id > 0
    assert await repo.get(item.id) == item


async def test_get_missing_is_none(repo: NewsRepository) -> None:
    assert await repo.get(999) is None


async def test_duplicate_url_raises_and_repo_still_works(repo: NewsRepository) -> None:
    await repo.add("https://example.com/1", "Перша новина")
    with pytest.raises(DuplicateUrl):
        await repo.add("https://example.com/1", "Та сама адреса")
    await repo.add("https://example.com/2", "Друга новина")         # транзакція не зламана
    assert [n.url for n in await repo.latest(10)] == ["https://example.com/2", "https://example.com/1"]


async def test_latest_is_newest_first_and_limited(repo: NewsRepository) -> None:
    for i in range(5):
        await repo.add(f"https://example.com/{i}", f"Новина номер {i}")
    assert [n.title for n in await repo.latest(2)] == ["Новина номер 4", "Новина номер 3"]


async def test_add_view(repo: NewsRepository) -> None:
    item = await repo.add("https://example.com/1", "Перша новина")
    await repo.add_view(item.id)
    await repo.add_view(item.id)
    assert (await repo.get(item.id)).views == 2
