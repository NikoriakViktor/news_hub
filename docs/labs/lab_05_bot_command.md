# Лаба 5. Команда бота `/top` { #lab-05 }

| | |
|---|---|
| Основа | [крок 9](../tutorials/09_telegram_bot/index.md) — `steps/09_telegram_bot` |
| Що тренує | нова команда aiogram від handler до меню, чиста функція окремо від Telegram, екранування тексту від LLM, перевірка аргументів, тест через двійник Telegram |
| Складність | ★☆☆ |
| Орієнтовний час | 1,5–2 години |

## Мета { #goal }

**Задача.** `/digest` показує підсумки останніх новин, але щоб побачити головні теми дня, треба прочитати весь список. Після аналізу LLM у кожної новини є до п'яти ключових слів (`NewsRow.keywords`). Якщо порахувати, скільки новин згадують кожне слово, вийде список тем: «нбу — 3, інфляція — 2». З нього користувач може одразу підписатися: `/subscribe нбу`.

**Зміна.** Команда `/top [N]`:

- функція `top_keywords(keyword_lists, limit)` у `news_hub/analysis.py` рахує теми і нічого не знає ні про Telegram, ні про базу;
- handler `cmd_top` бере 50 останніх новин, лишає проаналізовані, рахує теми й відповідає. LLM він **не** викликає;
- команда додана в роутер, у меню (`COMMANDS`) і в `/help`.

**Результат.**

```text
🔥 Теми останніх новин (проаналізовано 3)
1. «нбу» — 3
2. «інфляція» — 2
3. «ставка» — 1

Стежити за темою: /subscribe <слово>
```

**Правило.** Логіку команди пишіть чистою функцією і тестуйте окремо, а handler лише збирає дані й форматує відповідь. Усе, що прийшло ззовні, екрануйте. Ключові слова написала модель, тож це теж зовнішній текст, як ім'я користувача чи заголовок.

## Звідки починаємо { #start }

```bash
cp -r steps/09_telegram_bot lab_05 && cd lab_05
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

```text
355 passed, 2 deselected in 22.01s
```

Перечитайте [`news_hub/bot/handlers.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/09_telegram_bot/news_hub/bot/handlers.py) (`cmd_news`: перевірка аргументу через `isdecimal`; `build_router`: порядок реєстрації), [`news_hub/bot/factory.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/09_telegram_bot/news_hub/bot/factory.py) (`COMMANDS`) і [`tests/integration/test_bot.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/09_telegram_bot/tests/integration/test_bot.py) (`telegram.say(...)`).

## Вимоги { #requirements }

1. **`top_keywords(keyword_lists: list[list[str]], limit: int) -> list[tuple[str, int]]`:**
    - слова порівнюються без регістру й без пробілів по краях (`strip().casefold()`) і показуються в цьому вигляді;
    - одна новина дає слову не більше одного голосу, навіть якщо модель повторила його двічі;
    - порожні слова пропускаються;
    - порядок: більше новин вище; при рівності — за абеткою, щоб відповідь не залежала від порядку рядків у базі.
2. **`/top [N]`:** `N` від 1 до 10, за замовчуванням 5. Будь-що інше (`0`, `11`, `багато`, `²`) дає `Використання: /top [1–10]`.
3. **Дані:** 50 останніх новин (`NewsRepository.latest`), з них лише проаналізовані (`analyzed_at is not None`). Немає жодної теми — відповідь `Ще немає проаналізованих новин — спершу /digest.`
4. **Відповідь:** перший рядок `🔥 <b>Теми</b> останніх новин (проаналізовано K)`, далі `місце. «слово» — кількість`, порожній рядок і підказка `Стежити за темою: /subscribe &lt;слово&gt;`. Кожне слово проходить через `esc`.
5. **Реєстрація:** `Command("top")` у `build_router` **до** `F.text`; `BotCommand(command="top", …)` у `COMMANDS`; рядок `/top [N] — …` у `HELP`.
6. Жоден наявний тест не змінюється.

## Критерії приймання { #acceptance }

```python title="tests/unit/test_top_keywords.py"
"""Лаба 5: підрахунок тем для /top — чиста функція, без бази й Telegram."""
from news_hub.analysis import top_keywords


def test_counts_case_insensitively_once_per_news() -> None:
    lists = [["НБУ", "облікова ставка"], ["нбу", "НБУ", "інфляція"], [" Інфляція ", "НБУ"], []]
    assert top_keywords(lists, 5) == [("нбу", 3), ("інфляція", 2), ("облікова ставка", 1)]


def test_ties_alphabetical_and_limit() -> None:
    lists = [["б", "в"], ["а", "в"], ["а", "б"]]
    assert top_keywords(lists, 2) == [("а", 2), ("б", 2)]


def test_blank_keywords_are_ignored() -> None:
    assert top_keywords([["", "  "], ["бюджет"]], 5) == [("бюджет", 1)]
```

```python title="tests/integration/test_bot_top.py"
"""Лаба 5: команда /top — теми останніх новин за ключовими словами аналізу LLM."""
import pytest

from news_hub.analysis import NewsAnalysis
from news_hub.bot.factory import COMMANDS
from news_hub.models import NewsItem
from news_hub.repository import NewsRepository

from .conftest import BotHarness

pytestmark = pytest.mark.asyncio


async def add_analyzed(telegram: BotHarness, *keyword_lists: list[str], plain: int = 0) -> None:
    """Новини з аналізом (ключові слова — як від LLM) і `plain` новин без аналізу."""
    async with telegram.factory() as session:
        repo = NewsRepository(session)
        for number, keywords in enumerate(keyword_lists, 1):
            row = await repo.create(NewsItem.model_validate(
                {"title": f"Проаналізована новина номер {number}", "url": f"https://www.rbc.ua/ukr/news/a-{number}.html"}))
            await repo.save_analysis(row, NewsAnalysis(summary="Підсумок новини.", category="Економіка",
                                                       sentiment="нейтральна", keywords=keywords))
        for number in range(plain):
            await repo.create(NewsItem.model_validate(
                {"title": f"Новина без аналізу номер {number}", "url": f"https://www.rbc.ua/ukr/news/p-{number}.html"}))
        await session.commit()


async def test_top_without_analysis(telegram: BotHarness) -> None:
    assert await telegram.say("/top") == ["Ще немає проаналізованих новин — спершу /digest."]
    await add_analyzed(telegram, plain=3)
    assert await telegram.say("/top") == ["Ще немає проаналізованих новин — спершу /digest."]


async def test_top_counts_and_orders(telegram: BotHarness) -> None:
    await add_analyzed(telegram, ["НБУ", "ставка"], ["нбу", "інфляція"], ["Інфляція", "НБУ"], plain=2)
    [reply] = await telegram.say("/top")
    assert reply.splitlines() == [
        "🔥 <b>Теми</b> останніх новин (проаналізовано 3)",
        "1. «нбу» — 3",
        "2. «інфляція» — 2",
        "3. «ставка» — 1",
        "",
        "Стежити за темою: /subscribe &lt;слово&gt;",
    ]
    [short] = await telegram.say("/top 1")
    assert "1. «нбу» — 3" in short and "інфляція" not in short


async def test_keywords_from_llm_are_escaped(telegram: BotHarness) -> None:
    """Ключові слова написала модель — для бота це зовнішній текст. Двійник відкидає невалідний HTML."""
    await add_analyzed(telegram, ["<script>", "A&B"])
    [reply] = await telegram.say("/top")
    assert "«&lt;script&gt;» — 1" in reply and "«a&amp;b» — 1" in reply


@pytest.mark.parametrize("args", ["0", "11", "багато", "²"])
async def test_top_bad_argument(telegram: BotHarness, args: str) -> None:
    await add_analyzed(telegram, ["НБУ"])
    assert await telegram.say(f"/top {args}") == ["Використання: /top [1–10]"]


async def test_top_is_in_menu_and_help(telegram: BotHarness) -> None:
    assert "top" in [command.command for command in COMMANDS]
    [help_text] = await telegram.say("/help")
    assert "/top [N]" in help_text
```

**До змін.** Unit-тест не збирається (`top_keywords` немає):

```text
E   ImportError: cannot import name 'top_keywords' from 'news_hub.analysis' (…/news_hub/analysis.py)
ERROR tests/unit/test_top_keywords.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

Інтеграційний тест окремо (`pytest tests/integration/test_bot_top.py`) збирається, але всі 8 перевірок падають. Команди немає, і на `/top` відповідає «будь-який текст»:

```text
E       At index 0 diff: 'Не знаю такої команди. /help — що я вмію' != 'Ще немає проаналізованих новин — спершу /digest.'
E       At index 0 diff: 'Не знаю такої команди. /help — що я вмію' != 'Використання: /top [1–10]'
E       AssertionError: assert 'top' in ['news', 'digest', 'subscribe', 'subscriptions', 'help']
8 failed in 3.00s
```

**Після** еталонного розв'язку:

```text
$ pytest -q
366 passed, 2 deselected in 28.22s
$ mypy --strict news_hub
Success: no issues found in 26 source files
```

## Підказки { #hints }

??? tip "Один голос від новини"

    Множина всередині циклу: `{k.strip().casefold() for k in keywords if k.strip()}`. Тоді `["нбу", "НБУ"]` в одній новині дає одне слово.

??? tip "Сортування з рівністю"

    `sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))`: мінус перед кількістю дає спадання, а друге поле розв'язує рівність за абеткою. Без другого поля порядок рівних тем залежав би від того, в якому порядку новини прийшли з бази.

??? tip "Чому тест з `<script>` червоніє без `esc`"

    Двійник Telegram (`tests/telegram_twin.py`) перевіряє HTML так само, як Bot API. Невідомий тег дає `400 Bad Request: can't parse entities`, і aiogram піднімає `TelegramBadRequest`. У справжньому Telegram користувач не отримав би нічого.

## Підхід до розв'язку { #solution }

??? success "Підхід до розв'язку"

    `news_hub/analysis.py`:

    ```python
    def top_keywords(keyword_lists: list[list[str]], limit: int) -> list[tuple[str, int]]:
        """Скільки новин згадують кожне ключове слово: без регістру, одна новина — один голос."""
        counts: dict[str, int] = {}
        for keywords in keyword_lists:
            for keyword in {k.strip().casefold() for k in keywords if k.strip()}:
                counts[keyword] = counts.get(keyword, 0) + 1
        return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
    ```

    `news_hub/bot/handlers.py`:

    ```python
    from ..analysis import AnalysisCache, analyze_news, top_keywords

    TOP_DEFAULT, TOP_MAX, TOP_NEWS = 5, 10, 50   # скільки тем показати; серед скількох останніх новин

    HELP = (
        ...
        "/digest — дайджест: тема й тональність за аналізом LLM\n"
        "/top [N] — головні теми останніх новин (до 10)\n"
        ...
    )


    async def cmd_top(message: Message, command: CommandObject, news: NewsRepository) -> None:
        """Теми останніх новин за ключовими словами аналізу LLM. Нових викликів LLM не робить — лише читає базу."""
        count = TOP_DEFAULT
        if command.args:
            arg = command.args.strip()
            if not arg.isdecimal() or not 1 <= int(arg) <= TOP_MAX:
                await message.answer(f"Використання: /top [1–{TOP_MAX}]")
                return
            count = int(arg)
        analyzed = [row for row in await news.latest(TOP_NEWS) if row.analyzed_at is not None]
        top = top_keywords([row.keywords or [] for row in analyzed], count)
        if not top:
            await message.answer("Ще немає проаналізованих новин — спершу /digest.")
            return
        lines = [f"🔥 <b>Теми</b> останніх новин (проаналізовано {len(analyzed)})"]
        lines += [f"{place}. «{esc(keyword)}» — {mentions}" for place, (keyword, mentions) in enumerate(top, 1)]
        lines += ["", "Стежити за темою: /subscribe &lt;слово&gt;"]
        await answer_lines(message, lines)

    # build_router — після digest і до F.text:
        router.message(Command("top"))(cmd_top)
    ```

    `news_hub/bot/factory.py`, у `COMMANDS`:

    ```python
        BotCommand(command="top", description="Головні теми останніх новин"),
    ```

    `news` у параметрах handler дає `InjectMiddleware`, так само як у `cmd_news`. Нових залежностей не треба.

## Що перевірити самому { #self-check }

- Приберіть `esc` у рядку з темою й запустіть `pytest tests/integration/test_bot_top.py -k escaped`. В еталонному прогоні: `TelegramBadRequest: Telegram server says - Bad Request: can't parse entities: unsupported start tag "script"`. Що в цей час бачив би користувач?
- Зареєструйте `/top` **після** `router.message(F.text)(unknown)`. Які тести впадуть і чому `/help` при цьому працює?
- `/top` рахує теми серед 50 **останніх** новин, а не за останню добу. Що треба змінити в `NewsRepository`, щоб рахувати «за 24 години» (`scraped_at`), і чим це краще для користувача?
- Слова «НБУ» і «Нацбанк» — одна тема, а `top_keywords` рахує їх окремо. Де таке об'єднання мало б жити: у промпті LLM, у `top_keywords` чи в окремому словнику синонімів? Що з цього можна покрити тестом без мережі?
