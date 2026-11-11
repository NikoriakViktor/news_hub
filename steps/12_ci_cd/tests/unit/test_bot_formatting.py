"""Урок 47: текст для Telegram (HTML, 4096), ключові слова, налаштування бота — без мережі."""
import pytest

from news_hub.bot.formatting import esc, link, matches, normalize_keyword, split_message
from news_hub.bot.settings import load_bot_settings
from news_hub.notify import build_messages
from news_hub.repository import NewNews
from tests.telegram_twin import html_error


@pytest.mark.parametrize(("text", "valid"), [
    ("<b>жирний</b> і <i>курсив</i>", True),
    ('<a href="https://www.rbc.ua/a?x=1&amp;y=2">посилання</a>', True),
    ("5 &lt; 7 &amp;&amp; 7 &gt; 5", True),
    ("5 < 7", False), ("Олена & Ко", False), ("<script>x</script>", False), ("<b>без кінця", False),
    ("<b><i>навхрест</b></i>", False),
])
def test_twin_follows_html_rules(text: str, valid: bool) -> None:
    assert (html_error(text) is None) is valid


@pytest.mark.parametrize("raw", ["<Олена & Ко>", "5 < 7", "a > b", "&amp; вже екрановано", "\"лапки\" і 'апостроф'"])
def test_escaped_text_is_always_valid(raw: str) -> None:
    assert html_error(f"<b>{esc(raw)}</b>") is None


def test_link_escapes_quotes_in_url() -> None:
    html = link('https://example.com/?q="x"&a=1', "<Заголовок>")
    assert html == '<a href="https://example.com/?q=&quot;x&quot;&amp;a=1">&lt;Заголовок&gt;</a>'
    assert html_error(html) is None


def test_split_only_between_lines() -> None:
    lines = [f"<b>{number:03}</b> " + "я" * 90 for number in range(200)]
    parts = split_message(lines)
    assert len(parts) > 1 and all(len(part) <= 4096 for part in parts)
    assert all(html_error(part) is None for part in parts)
    assert "\n".join(parts).split("\n") == lines                       # нічого не загубилось і не розрізане


def test_old_split_cuts_inside_markup() -> None:
    """Розріз кожні N символів (як split_long_message стартового ai_bot) ламає теги й сутності."""
    text = "\n".join(f"<b>{number:03}</b> Олена &amp; Ко" for number in range(400))
    chunks = [text[i: i + 4000] for i in range(0, len(text), 4000)]
    assert any(html_error(chunk) for chunk in chunks)


@pytest.mark.parametrize(("raw", "keyword"), [
    ("Бюджет", "бюджет"), ("  НБУ ", "нбу"), ("кам'янське", "кам'янське"), ("covid-19", "covid-19"),
    ("а", None), ("два слова", None), ("<b>", None), ("я" * 41, None), ("", None),
])
def test_normalize_keyword(raw: str, keyword: str | None) -> None:
    assert normalize_keyword(raw) == keyword


@pytest.mark.parametrize(("keyword", "title", "found"), [
    ("бюджет", "Уряд ухвалив бюджет на рік", True),
    ("бюджет", "Бюджету бракує 100 млрд", True),               # інше закінчення
    ("рада", "Верховна Рада ухвалила закон", True),
    ("рада", "Це зрада, кажуть експерти", False),              # не підрядок будь-де
    ("нбу", "НБУ знизив ставку", True),
    ("газ", "Газета вийшла вранці", True),                     # межа методу: початок слова — не корінь
])
def test_matches(keyword: str, title: str, found: bool) -> None:
    assert matches(keyword, title) is found


def test_build_messages_only_matching_news() -> None:
    news = [NewNews(1, "Уряд ухвалив бюджет", "https://www.rbc.ua/1"), NewNews(2, "Погода на вихідні", "https://www.rbc.ua/2")]
    [text] = build_messages(["бюджет"], news)
    assert "бюджет" in text and "Погода" not in text and html_error(text) is None
    assert build_messages(["футбол"], news) == []


def test_bot_settings() -> None:
    assert load_bot_settings({}) is None                                       # без токена — бота немає
    settings = load_bot_settings({"BOT_TOKEN": "1:x", "BOT_ADMIN_IDS": "1001, 2002"})
    assert settings is not None and settings.admin_ids == {1001, 2002} and settings.webhook_url is None
    good = "s" * 40
    for env in ({"TELEGRAM_WEBHOOK_URL": "http://news.example/hook", "TELEGRAM_WEBHOOK_SECRET": good},
                {"TELEGRAM_WEBHOOK_URL": "https://news.example/hook"},
                {"TELEGRAM_WEBHOOK_URL": "https://news.example/hook", "TELEGRAM_WEBHOOK_SECRET": "short"},
                {"TELEGRAM_WEBHOOK_URL": "https://news.example/hook", "TELEGRAM_WEBHOOK_SECRET": "з пробілом " + good}):
        with pytest.raises(RuntimeError):
            load_bot_settings({"BOT_TOKEN": "1:x", **env})
