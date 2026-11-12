# Лаба 1. Нове джерело: Atom-стрічка { #lab-01 }

| | |
|---|---|
| Основа | [крок 6](../tutorials/06_ai_dev_tools/index.md) — `steps/06_ai_dev_tools` |
| Що тренує | парсинг XML з просторами імен, відносні URL, час з поясом, фікстура замість мережі, межа «сирі дані → модель», збір кількох стрічок без падіння через одну погану |
| Складність | ★★☆ |
| Орієнтовний час | 3–4 години |

## Мета { #goal }

**Задача.** У News Hub два джерела: HTML-стрічка rbc.ua (`parser.py`) і RSS «Української правди» (`rss.py`). Третє джерело, Укрінформ, віддає стрічку у форматі **Atom**. Це не «ще один RSS»: усі теги в просторі імен `http://www.w3.org/2005/Atom`, посилання записане в атрибуті `href` тегу `<link rel="alternate">` і буває відносним, дата — у RFC 3339 (`2026-11-10T08:00:00Z`), а категорія — в атрибуті `term`. Парсер RSS тут не допоможе, а `root.iter("entry")` не знайде нічого, бо тег насправді називається `{http://www.w3.org/2005/Atom}entry`.

**Зміна.** Три частини:

1. `news_hub/atom.py` — `parse_atom(feed, feed_url) -> list[RawNews]`;
2. домен `ukrinform.ua` — у `ALLOWED_DOMAINS` (`models.py`);
3. `news_hub/feeds.py` — одна точка входу для стрічок: `parse_feed` вибирає парсер за коренем документа, `scrape_feeds` збирає кілька стрічок одночасно, як `scrape_all_async` збирає сторінки.

**Результат.** RSS і Atom збираються одним викликом. Сторінка капчі з кодом `200` чи `404` дає помилку в `PageResult.error` і не валить збір. Кожна новина Укрінформу проходить ту саму перевірку `NewsItem`, що й новини rbc.ua.

**Правило.** Нове джерело — це спершу **фікстура і тести на межові випадки**, потім парсер. Парсер повертає сирі `RawNews` і нічого не відкидає мовчки: погані новини відкидає модель, і їх видно в `rejected`.

Від завдання [«третє джерело через skill»](../tutorials/06_ai_dev_tools/checkpoint.md#third-source) лаба відрізняється тим, що там ще один RSS, а тут інший формат, своя фікстура з навмисними пастками і збір через HTTP.

## Звідки починаємо { #start }

```bash
cp -r steps/06_ai_dev_tools lab_01 && cd lab_01
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

```text
107 passed in 3.74s
```

Корисно перечитати: [`news_hub/rss.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/06_ai_dev_tools/news_hub/rss.py) (той самий підхід для RSS), [`news_hub/scraper.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/06_ai_dev_tools/news_hub/scraper.py) (`fetch_one`, `_outcome`), [`tests/integration/test_scraper_server.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/06_ai_dev_tools/tests/integration/test_scraper_server.py) (фейковий сайт на `TestServer`).

## Вимоги { #requirements }

**Фікстура** `tests/fixtures/ukrinform_atom.xml` — навчальний знімок з позначкою в коментарі (заголовки вигадані). Кожен запис у ній перевіряє окремий випадок:

| Запис | Що перевіряє |
|---|---|
| облігації Мінфіну | звичайний запис; є і `published`, і `updated` — береться `published`; `summary type="html"` з `&lt;p&gt;` |
| пункт незламності | **відносне** посилання `/rubric-society/…`; дата з `Z` (UTC) |
| «Мінфін… (оновлено)» | **дублікат** посилання першого запису — пропускається |
| додаткові поїзди | **немає дати** — новина лишається, `datetime == ""` |
| «Фото дня» | два `<link>`: спершу `rel="enclosure"` (картинка), потім `alternate`; заголовок закороткий, тож новину відхилить модель |
| без посилання | немає `<link>` — запис пропускається |
| передрук з чужого сайту | посилання на `evil.example.com` — парсер його повертає, модель відхиляє |
| ожеледиця | дата `вчора ввечері` — не ламає стрічку, `datetime == ""` |

```xml title="tests/fixtures/ukrinform_atom.xml"
<?xml version="1.0" encoding="UTF-8"?>
<!-- Навчальний знімок стрічки у форматі Atom 1.0. Заголовки вигадані для лаби:
     справжня стрічка щодня інша, а тестам потрібні сталі дані. -->
<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://www.ukrinform.ua/">
  <title>Укрінформ</title>
  <id>https://www.ukrinform.ua/</id>
  <updated>2026-11-10T11:00:00+02:00</updated>
  <link rel="self" href="https://www.ukrinform.ua/atom.xml"/>
  <entry>
    <title>Мінфін розмістив облігації на 12 мільярдів</title>
    <link rel="alternate" href="https://www.ukrinform.ua/rubric-economy/4012001-minfin-rozmistyv-oblihatsii.html"/>
    <id>urn:ukrinform:4012001</id>
    <published>2026-11-10T09:15:00+02:00</published>
    <updated>2026-11-10T11:00:00+02:00</updated>
    <category term="Економіка"/>
    <summary type="html">&lt;p&gt;Попит перевищив пропозицію.&lt;/p&gt;</summary>
  </entry>
  <entry>
    <title>У Києві відкрили ще один пункт незламності</title>
    <link href="/rubric-society/4012002-u-kyievi-vidkryly-punkt.html"/>
    <id>urn:ukrinform:4012002</id>
    <updated>2026-11-10T08:00:00Z</updated>
    <category term="Суспільство"/>
    <summary>Пункт працюватиме цілодобово.</summary>
  </entry>
  <entry>
    <title>Мінфін розмістив облігації (оновлено)</title>
    <link rel="alternate" href="https://www.ukrinform.ua/rubric-economy/4012001-minfin-rozmistyv-oblihatsii.html"/>
    <id>urn:ukrinform:4012001-2</id>
    <updated>2026-11-10T10:30:00+02:00</updated>
  </entry>
  <entry>
    <title>Укрзалізниця призначила додаткові поїзди на свята</title>
    <link rel="alternate" href="https://www.ukrinform.ua/rubric-society/4012003-dodatkovi-poizdy.html"/>
    <id>urn:ukrinform:4012003</id>
    <category term="Суспільство"/>
  </entry>
  <entry>
    <title>Фото дня</title>
    <link rel="enclosure" type="image/jpeg" href="https://static.ukrinform.ua/photos/4012004.jpg"/>
    <link rel="alternate" href="https://www.ukrinform.ua/rubric-society/4012004-foto-dnia.html"/>
    <id>urn:ukrinform:4012004</id>
    <updated>2026-11-10T07:30:00+02:00</updated>
  </entry>
  <entry>
    <title>Новина без посилання не потрапить у стрічку</title>
    <id>urn:ukrinform:4012005</id>
    <updated>2026-11-10T07:00:00+02:00</updated>
  </entry>
  <entry>
    <title>Передрук з чужого сайту про погоду на вихідні</title>
    <link rel="alternate" href="https://evil.example.com/news/4012006.html"/>
    <id>urn:ukrinform:4012006</id>
    <updated>2026-11-10T06:45:00+02:00</updated>
  </entry>
  <entry>
    <title>Синоптики попередили про ожеледицю на дорогах</title>
    <link rel="alternate" href="https://www.ukrinform.ua/rubric-society/4012007-ozheledytsia.html"/>
    <id>urn:ukrinform:4012007</id>
    <updated>вчора ввечері</updated>
    <category term="Суспільство"/>
  </entry>
</feed>
```

**`parse_atom(feed: str, feed_url: str) -> list[RawNews]`** (`news_hub/atom.py`):

- `xml.etree.ElementTree` зі стандартної бібліотеки, як у `rss.py` (без `feedparser`);
- битий XML → `ValueError`; корінь не Atom `<feed>` (HTML-сторінка, RSS) → `ValueError`, а не `[]`; порожній `<feed>` → `[]`;
- посилання: перший `<link>` з `rel="alternate"` або без `rel` (за Atom це те саме); відносне розв'язується від `xml:base` кореня, а без нього — від `feed_url`;
- запис без посилання й повтор посилання пропускаються; порядок як у стрічці;
- `datetime` — `published`, а якщо його немає, то `updated`; переведений у київський час без поясу (`"2026-11-10T10:00:00"`), як у `rss.py`; немає дати чи вона не розбирається → `""`;
- `category` — атрибут `term`; `description` — текст `summary` без HTML-тегів.

**`news_hub/feeds.py`:**

- `parse_feed(text, feed_url)`: корінь `rss` → `parse_pravda_rss`, Atom `feed` → `parse_atom`, інакше `ValueError("невідомий формат стрічки: <html>")` (у дужках — тег кореня);
- `fetch_feed(session, url, t0)` повертає те саме, що `scraper.fetch_one`: `(PageResult, list[RawNews])`. `ClientError`, тайм-аут і `ValueError` записуються в `PageResult.error` як `"ValueError: …"`;
- `scrape_feeds(feeds)` — `asyncio.gather` по всіх стрічках, результат через `_outcome` (без дублікатів за url).

**Не змінювати:** `POST /api/scrape` досі приймає лише сторінки rbc.ua (`is_rbc_host`), жоден наявний тест не редагується.

## Критерії приймання { #acceptance }

Два файли тестів. Покладіть їх у проєкт до того, як писати код.

```python title="tests/unit/test_atom.py"
"""Лаба 1: Atom-стрічка як третє джерело. Специфікація — до коду; фікстура tests/fixtures/ukrinform_atom.xml."""
from pathlib import Path

import pytest

from news_hub.atom import parse_atom
from news_hub.models import is_allowed_host, validate_news

FIXTURES = Path(__file__).parent.parent / "fixtures"
FEED = (FIXTURES / "ukrinform_atom.xml").read_text(encoding="utf-8")
FEED_URL = "https://www.ukrinform.ua/atom.xml"


def test_entries_in_feed_order_without_duplicates_and_without_links() -> None:
    assert [n["url"] for n in parse_atom(FEED, FEED_URL)] == [
        "https://www.ukrinform.ua/rubric-economy/4012001-minfin-rozmistyv-oblihatsii.html",
        "https://www.ukrinform.ua/rubric-society/4012002-u-kyievi-vidkryly-punkt.html",   # був відносний
        "https://www.ukrinform.ua/rubric-society/4012003-dodatkovi-poizdy.html",
        "https://www.ukrinform.ua/rubric-society/4012004-foto-dnia.html",                  # alternate, не enclosure
        "https://evil.example.com/news/4012006.html",
        "https://www.ukrinform.ua/rubric-society/4012007-ozheledytsia.html",
    ]


def test_fields_are_clean_text() -> None:
    first = parse_atom(FEED, FEED_URL)[0]
    assert first == {"title": "Мінфін розмістив облігації на 12 мільярдів",
                     "url": "https://www.ukrinform.ua/rubric-economy/4012001-minfin-rozmistyv-oblihatsii.html",
                     "category": "Економіка",
                     "description": "Попит перевищив пропозицію.",             # summary type="html" без <p>
                     "datetime": "2026-11-10T09:15:00"}                       # published, а не updated


def test_time_is_kyiv_local_and_never_breaks_the_feed() -> None:
    """+02:00 і Z → київський час без поясу; немає дати або «вчора ввечері» → "" (новина лишається)."""
    assert [n["datetime"] for n in parse_atom(FEED, FEED_URL)] == [
        "2026-11-10T09:15:00", "2026-11-10T10:00:00", "", "2026-11-10T07:30:00", "2026-11-10T06:45:00", ""]


def test_relative_link_without_xml_base_uses_feed_url() -> None:
    feed = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Заголовок відносної новини</title>'
            '<link href="news/1.html"/></entry></feed>')
    assert parse_atom(feed, "https://www.ukrinform.ua/ukr/atom.xml")[0]["url"] == \
        "https://www.ukrinform.ua/ukr/news/1.html"


@pytest.mark.parametrize("text", [
    "<html><body><h1>403 Forbidden</h1></body></html>",       # сторінка помилки з кодом 200
    "<rss><channel></channel></rss>",                         # інший формат — не Atom
    "<feed><entry>",                                           # битий XML
])
def test_not_atom_raises_value_error(text: str) -> None:
    with pytest.raises(ValueError):
        parse_atom(text, FEED_URL)


def test_empty_feed_is_empty_list() -> None:
    assert parse_atom('<feed xmlns="http://www.w3.org/2005/Atom"></feed>', FEED_URL) == []


def test_pipeline_atom_to_model() -> None:
    valid, rejected = validate_news(parse_atom(FEED, FEED_URL))
    assert [(n.source, n.lang, n.category) for n in valid] == [
        ("ukrinform.ua", "uk", "Економіка"), ("ukrinform.ua", "uk", "Суспільство"),
        ("ukrinform.ua", "uk", "Суспільство"), ("ukrinform.ua", "uk", "Суспільство"),
    ]
    assert [r.raw["title"] for r in rejected] == ["Фото дня", "Передрук з чужого сайту про погоду на вихідні"]


@pytest.mark.parametrize(("host", "allowed"), [
    ("ukrinform.ua", True), ("www.ukrinform.ua", True),
    ("fakeukrinform.ua", False), ("ukrinform.ua.evil.com", False),
])
def test_ukrinform_is_allowed_host(host: str, allowed: bool) -> None:
    assert is_allowed_host(host) is allowed
```

```python title="tests/integration/test_feeds_server.py"
"""Лаба 1: збір стрічок (RSS і Atom) справжнім aiohttp проти локального сервера — без інтернету."""
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from news_hub.feeds import parse_feed, scrape_feeds

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest_asyncio.fixture
async def feeds_site() -> AsyncIterator[TestServer]:
    def xml(name: str) -> web.Response:
        return web.Response(text=(FIXTURES / name).read_text(encoding="utf-8"), content_type="application/xml")

    async def atom(request: web.Request) -> web.Response:
        return xml("ukrinform_atom.xml")

    async def rss(request: web.Request) -> web.Response:
        return xml("pravda_rss.xml")

    async def captcha(request: web.Request) -> web.Response:        # 200, але не стрічка
        return web.Response(text="<html><body>Підтвердіть, що ви не робот</body></html>", content_type="text/html")

    app = web.Application()
    app.router.add_get("/atom.xml", atom)
    app.router.add_get("/rss.xml", rss)
    app.router.add_get("/captcha/", captcha)
    async with TestServer(app) as server:
        yield server


def test_parse_feed_dispatches_by_root() -> None:
    atom = (FIXTURES / "ukrinform_atom.xml").read_text(encoding="utf-8")
    rss = (FIXTURES / "pravda_rss.xml").read_text(encoding="utf-8")
    assert len(parse_feed(atom, "https://www.ukrinform.ua/atom.xml")) == 6
    assert len(parse_feed(rss, "https://www.pravda.com.ua/rss/")) == 4
    with pytest.raises(ValueError, match="невідомий формат стрічки: <html>"):
        parse_feed("<html></html>", "https://www.ukrinform.ua/")


@pytest.mark.asyncio
async def test_rss_and_atom_in_one_scrape_and_bad_feeds_do_not_break_it(feeds_site: TestServer) -> None:
    urls = [str(feeds_site.make_url(path)) for path in ("/atom.xml", "/rss.xml", "/captcha/", "/missing/")]
    outcome = await scrape_feeds(urls)

    assert [page.count for page in outcome.pages] == [6, 4, 0, 0]
    assert outcome.pages[0].error is None and outcome.pages[1].error is None
    assert outcome.pages[2].error == "ValueError: невідомий формат стрічки: <html>"
    assert (outcome.pages[3].error or "").startswith("ClientResponseError")
    sources = {item["url"].split("/")[2] for item in outcome.news}
    assert sources == {"www.ukrinform.ua", "evil.example.com", "www.pravda.com.ua", "www.epravda.com.ua"}
    assert len(outcome.news) == 10
```

Зверніть увагу на інтеграційний тест. Стрічку віддає `127.0.0.1:<порт>`, а відносне посилання все одно стає `https://www.ukrinform.ua/…`, бо в фікстурі є `xml:base`. Без `xml:base` новини мали б адресу тестового сервера, і модель їх відхилила б.

**До змін** модулів немає, тест не збирається:

```text
E   ModuleNotFoundError: No module named 'news_hub.atom'
=========================== short test summary info ============================
ERROR tests/integration/test_feeds_server.py
ERROR tests/unit/test_atom.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.67s
```

**Після** еталонного розв'язку:

```text
$ pytest -q
122 passed in 3.45s
$ mypy --strict news_hub
Success: no issues found in 15 source files
```

## Підказки { #hints }

??? tip "Простір імен у ElementTree"

    `ET.fromstring` записує тег з простором імен як `{uri}local`. Заведіть константу `ATOM = "{http://www.w3.org/2005/Atom}"` і шукайте `entry.find(ATOM + "title")`, `root.iter(ATOM + "entry")`. Атрибут `xml:base` — це `root.get("{http://www.w3.org/XML/1998/namespace}base")`.

??? tip "Відносні посилання"

    `urllib.parse.urljoin(base, href)`: абсолютний `href` повертається як є, `"/a.html"` береться від кореня сайту, `"news/1.html"` — від «папки» бази. Базу теж треба розв'язати від адреси стрічки: `urljoin(feed_url, xml_base or "")`.

??? tip "RFC 3339 і `Z`"

    `datetime.fromisoformat` у Python 3.11+ розуміє `Z`, а в 3.10 — ні. Щоб код працював на обох версіях, зробіть `value.replace("Z", "+00:00")`. Порожній рядок і «вчора ввечері» дають `ValueError`, тоді повертайте `""`.

??? tip "Чому `ValueError` у `fetch_feed`"

    `asyncio.gather` без `return_exceptions` падає на першому винятку, і новини решти стрічок губляться. Тому `fetch_one` ловить помилки всередині й записує їх у `PageResult.error`. Для стрічок до мережевих помилок додається ще `ValueError` від парсера.

## Підхід до розв'язку { #solution }

??? success "Підхід до розв'язку"

    `news_hub/models.py` — одна зміна:

    ```python
    ALLOWED_DOMAINS: tuple[str, ...] = ("rbc.ua", "pravda.com.ua", "epravda.com.ua", "ukrinform.ua")
    ```

    `news_hub/atom.py`:

    ```python
    import xml.etree.ElementTree as ET
    from datetime import datetime, timezone
    from urllib.parse import urljoin
    from zoneinfo import ZoneInfo

    from bs4 import BeautifulSoup

    from .parser import RawNews

    ATOM = "{http://www.w3.org/2005/Atom}"
    XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"
    KYIV = ZoneInfo("Europe/Kyiv")


    def _text(entry: ET.Element, tag: str) -> str:
        found = entry.find(ATOM + tag)
        return (found.text or "").strip() if found is not None else ""


    def _alternate_href(entry: ET.Element) -> str:
        for link in entry.findall(ATOM + "link"):
            if link.get("rel", "alternate") == "alternate" and link.get("href"):
                return link.get("href", "").strip()
        return ""


    def _kyiv_datetime(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(KYIV).replace(tzinfo=None).isoformat()


    def parse_atom(feed: str, feed_url: str) -> list[RawNews]:
        try:
            root = ET.fromstring(feed)
        except ET.ParseError as error:
            raise ValueError(f"пошкоджений Atom: {error}") from error
        if root.tag != ATOM + "feed":
            raise ValueError(f"очікуємо Atom (<feed>), а отримали <{root.tag}>")

        base = urljoin(feed_url, root.get(XML_BASE, ""))
        news_list: list[RawNews] = []
        seen_urls: set[str] = set()
        for entry in root.iter(ATOM + "entry"):
            href = _alternate_href(entry)
            url = urljoin(base, href) if href else ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            category = entry.find(ATOM + "category")
            news_list.append({
                "title": _text(entry, "title"),
                "url": url,
                "category": (category.get("term", "") if category is not None else "").strip(),
                "description": BeautifulSoup(_text(entry, "summary"), "html.parser").get_text().strip(),
                "datetime": _kyiv_datetime(_text(entry, "published") or _text(entry, "updated")),
            })
        return news_list
    ```

    `news_hub/feeds.py` використовує `HEADERS`, `PageResult`, `ScrapeOutcome` і `_outcome` зі `scraper.py`. Нової моделі результату немає:

    ```python
    def parse_feed(text: str, feed_url: str) -> list[RawNews]:
        try:
            root = ET.fromstring(text)
        except ET.ParseError as error:
            raise ValueError(f"пошкоджена стрічка: {error}") from error
        if root.tag == "rss":
            return parse_pravda_rss(text)
        if root.tag == ATOM + "feed":
            return parse_atom(text, feed_url)
        raise ValueError(f"невідомий формат стрічки: <{root.tag}>")


    async def fetch_feed(session: aiohttp.ClientSession, url: str, t0: float) -> tuple[PageResult, list[RawNews]]:
        start = time.perf_counter() - t0
        error = None
        items: list[RawNews] = []
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                text = await resp.text(errors="replace")
            items = parse_feed(text, url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            error = f"{type(e).__name__}: {e}"
        end = time.perf_counter() - t0
        return PageResult(url=url, start=round(start, 3), end=round(end, 3), count=len(items), error=error), items


    async def scrape_feeds(feeds: list[str]) -> ScrapeOutcome:
        t0 = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            results = await asyncio.gather(*(fetch_feed(session, url, t0) for url in feeds))
        return _outcome(list(results), t0)
    ```

    Помилку для чужого домену варто оновити в `NewsItem.only_allowed` («очікуємо новину з rbc.ua, pravda.com.ua, epravda.com.ua або ukrinform.ua»). Тести її тексту не перевіряють, а читач API — бачить.

## Що перевірити самому { #self-check }

- Приберіть `xml:base` з фікстури. Unit-тести лишаться зеленими, бо там `feed_url` уже на домені Укрінформу, а впаде інтеграційний: серед джерел з'явиться `127.0.0.1:<порт>`. Яку адресу тепер має новина «пункт незламності» і що з нею зробила б модель?
- Поміняйте в `_alternate_href` умову на «перший `<link>`, який є». Котрий тест це ловить?
- Чому `parse_feed` визначає формат за коренем документа, а не за `Content-Type` чи закінченням `.xml` в адресі?
- `scrape_feeds` поки ніхто не викликає з API. Що потрібно, щоб `POST /api/scrape` збирав і стрічки? Зверніть увагу на `ScrapeRequest.only_rbc`, і на те, що довільні URL користувача — це SSRF ([крок 8](../tutorials/08_security/ssrf.md)).
- `mypy --strict news_hub` чистий? `_text` і `_kyiv_datetime` мають однакові назви в `rss.py` і `atom.py`. Чи варто їх об'єднувати, і що тоді стане спільною залежністю?
