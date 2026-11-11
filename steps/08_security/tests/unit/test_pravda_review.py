"""Тести рецензента: чого специфікація test_pravda.py не передбачила (урок 42).

AI-асистент зробив усі тести специфікації зеленими. Рецензія його коду знайшла три випадки поза нею —
кожен тут: на коді асистента тест падав, після виправлення проходить.
"""
import subprocess
import sys

from news_hub.models import validate_news
from news_hub.rss import parse_pravda_rss

ITEM = ('<item><title>Уряд оновив правила вступу до університетів</title>'
        '<link>https://www.pravda.com.ua/news/2026/09/26/7501001/</link>{extra}</item>')


def feed(*items: str) -> str:
    return "<rss><channel>" + "".join(items) + "</channel></rss>"


def test_item_without_category_is_not_named_after_year() -> None:
    """Без <category> категорію брали з URL: /news/2026/09/26/… → «2026»."""
    valid, _ = validate_news(parse_pravda_rss(feed(ITEM.format(extra="<pubDate>Sat, 26 Sep 2026 21:40:00 +0300</pubDate>"))))
    assert [n.category for n in valid] == ["Новини"]


def test_item_without_pub_date_does_not_break_feed() -> None:
    """Одна новина без <pubDate> кидала ValueError — і губилася вся стрічка."""
    news = parse_pravda_rss(feed(ITEM.format(extra="<category>Новини</category>"),
                                 ITEM.replace("7501001", "7501002").format(extra="<pubDate>garbage</pubDate>")))
    assert [n["datetime"] for n in news] == ["", ""]
    valid, rejected = validate_news(news)
    assert (len(valid), rejected, valid[0].published_time) == (2, [], None)


def test_rss_module_imports_without_system_tz_database() -> None:
    """Windows не має системної бази часових поясів: ZoneInfo("Europe/Kyiv") бере її з пакета tzdata.

    Імітуємо: PYTHONTZPATH вказує в порожнечу. Без tzdata в requirements.txt імпорт падав
    (ZoneInfoNotFoundError) — на Windows news_hub.rss не імпортувався б узагалі.
    """
    code = "import news_hub.rss as r; print(r.KYIV)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env={"PYTHONTZPATH": "/nonexistent", "PATH": ""}, cwd=".")
    assert result.returncode == 0, result.stderr[-300:]
    assert result.stdout.strip() == "Europe/Kyiv"
