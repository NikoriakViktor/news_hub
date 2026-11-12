"""Сервіси: правила застосунку. Не знають ні SQL, ні SQLAlchemy — лише UnitOfWork і репозиторії."""
from .repositories import News
from .uow import UnitOfWork

BANNED_WORDS = ("казино",)


class Rejected(Exception):
    """Новина не пройшла модерацію."""


async def publish(uow: UnitOfWork, url: str, title: str) -> News:
    """Додати новину й запис у журнал — разом або ніяк."""
    async with uow:
        item = await uow.news.add(url, title)
        await uow.audit.record("publish", item.id)
        if any(word in title.lower() for word in BANNED_WORDS):
            raise Rejected(title)              # після add і record: обидва мають скасуватися
        await uow.commit()
        return item
