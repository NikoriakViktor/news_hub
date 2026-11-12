"""Сервіс publish з обома UnitOfWork: фейк повторює семантику транзакції, тому висновки ті самі."""
import pytest

from news_app.repositories import DuplicateUrl
from news_app.services import Rejected, publish
from news_app.uow import UnitOfWork


async def latest(uow: UnitOfWork) -> list[str]:
    async with uow:
        return [n.url for n in await uow.news.latest(10)]


async def test_publish_saves_news(uow: UnitOfWork) -> None:
    item = await publish(uow, "https://example.com/1", "Гривня зміцнилася")
    assert item.id > 0
    assert await latest(uow) == ["https://example.com/1"]


async def test_rejected_news_rolls_back_everything(uow: UnitOfWork) -> None:
    with pytest.raises(Rejected):
        await publish(uow, "https://example.com/1", "Найкраще казино країни")
    assert await latest(uow) == []                  # і новина, і запис журналу скасовані


async def test_duplicate_url(uow: UnitOfWork) -> None:
    await publish(uow, "https://example.com/1", "Гривня зміцнилася")
    with pytest.raises(DuplicateUrl):
        await publish(uow, "https://example.com/1", "Інший заголовок")
    assert await latest(uow) == ["https://example.com/1"]
