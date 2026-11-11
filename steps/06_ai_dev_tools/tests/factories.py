"""Фабрики тестових даних: правильні значення за замовчуванням — у тесті видно лише те, що для нього важливо."""
from news_hub.parser import RawNews


def make_raw(**overrides: str) -> RawNews:
    """make_raw(title="Коротко") — сира новина, як її дає парсер, з одним зміненим полем."""
    item: RawNews = {"title": "Уряд затвердив новий бюджет", "url": "https://www.rbc.ua/ukr/news/budget-1.html",
                     "category": "", "description": "", "datetime": "14:19"}
    return {**item, **overrides}  # type: ignore[typeddict-item]
