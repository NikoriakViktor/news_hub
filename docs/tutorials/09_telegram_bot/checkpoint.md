# Контрольна точка: крок 9

## Перевір, що крок робочий { #check }

З папки `steps/09_telegram_bot`:

```text
$ pytest -q -p no:cacheprovider
........................................................................ [ 20%]
...
355 passed, 2 deselected in 18.00s
$ mypy --strict news_hub
Success: no issues found in 26 source files
```

`2 deselected` — живі тести LLM (`tests/live/`, лише `pytest -m llm`). Порівняно з кроком 8 (294 тести) додалось 61:

| Файл | Що перевіряє | Тестів |
|---|---|---|
| `tests/unit/test_bot_formatting.py` | правила HTML двійника; екранування; `link` з лапками в URL; розріз між рядками (і що розріз кожні N символів ламає розмітку); слова підписки; збіги; налаштування бота | 33 |
| `tests/integration/test_bot.py` | команди через `dp.feed_update`: ім'я з `<` і `&`, `/news` (найновіші, HTML у заголовку), підписки й ліміт 10, `/digest` з LLM і без, rate limit, `/scrape` лише адміну і під лімітом збору API, група з id > 32 біт | 11 |
| `tests/integration/test_notify.py` | через API: сповіщення один раз, заблокований чат (403) втрачає підписки, 429 → `retry_after`, розбиття на частини, фонова задача, без бота нічого не ламається | 6 |
| `tests/integration/test_telegram_webhook.py` | webhook: секрет, 401 (зокрема з JWT адміна), 400, 503 без бота; `lifespan` ставить webhook і не видаляє його | 7 |
| `tests/unit/test_security.py` (+4) | `BOT_ADMIN_IDS` — частина `AdminSettings`; без адмін-доступу API, не число, не ASCII-цифри → помилка при старті | 4 |

Ті самі тести на PostgreSQL і Redis — `TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test TEST_REDIS_URL=redis://localhost:6379/15 pytest` (як у кроці 8). Лише там `chat_id` групи (`-1001234567890`) перевіряється на справжньому `BIGINT`: SQLite зберігає будь-яке ціле.

## Чекліст { #checklist }

- [ ] `python -m tests.telegram_twin --port 8081` + `python -m news_hub.bot` з `BOT_TOKEN=123456:TEST-TOKEN TELEGRAM_API_URL=http://127.0.0.1:8081`: `/news` через `/_twin/say` → `Новин поки немає.`
- [ ] `BOT_ADMIN_IDS=1001` без `JWT_SECRET` і `ADMIN_PASSWORD_HASH` → бот не стартує: `RuntimeError: BOT_ADMIN_IDS задано, а адмін-доступ — ні …`.
- [ ] `/scrape snapshot` від адміна (`BOT_ADMIN_IDS`) → `Зібрано: 168, нових: 168, відхилено: 0; …`; від інших → `Ця команда — лише для адміністратора.`; шостий `/scrape` за хвилину → `Забагато зборів: 5 за 60 с; …`
- [ ] `/start` з `first_name` `<Олена & Ко>` → `Привіт, <b>&lt;Олена &amp; Ко&gt;</b>! …`, двійник прийняв повідомлення.
- [ ] `/subscribe Зеленськ`, потім `POST /api/scrape` зі знімком → одне сповіщення `🔔 Нові новини за підписками (зеленськ):`; повторний збір → нового сповіщення немає.
- [ ] uvicorn з `TELEGRAM_WEBHOOK_URL` і `TELEGRAM_WEBHOOK_SECRET`: `getWebhookInfo` показує адресу; запит без заголовка → `401`; після зупинки webhook лишається.
- [ ] Можеш пояснити, чому webhook відповідає `200` до того, як бот обробив update.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `Задай BOT_TOKEN (від @BotFather); для двійника — ще TELEGRAM_API_URL`, вихід з кодом 1 | `python -m news_hub.bot` без `BOT_TOKEN` | задай токен; без мережі — двійник і `TELEGRAM_API_URL` |
| `RuntimeError: TELEGRAM_WEBHOOK_URL: Telegram надсилає webhook лише на https://`, потім `Application startup failed. Exiting.` | webhook на `http://` без `TELEGRAM_API_URL` | `https://` на сервері; `http://` — лише з двійником або локальним Bot API server |
| `RuntimeError: TELEGRAM_WEBHOOK_SECRET: 32–256 символів …` | секрету немає, він короткий або з пробілом | `python -c 'import secrets; print(secrets.token_urlsafe(48))'` |
| `RuntimeError: BOT_ADMIN_IDS задано, а адмін-доступ — ні` | адмінів бота задано, а `JWT_SECRET` і `ADMIN_PASSWORD_HASH` — ні | `python -m news_hub.security` і обидва рядки в середовище; адмін один для API і бота |
| `RuntimeError: BOT_ADMIN_IDS — числові id Telegram через кому` | у списку `@username` чи інший не числовий запис | числовий `user_id` (його показує, наприклад, журнал `/scrape від не-адміна …`) |
| бот мовчить, у журналі `TelegramBadRequest: … can't parse entities` | у HTML потрапив чужий текст без `esc` | `esc` / `link` для всього, що прийшло ззовні ([розділ 2](html_replies.md)) |
| `RuntimeError: Router is already attached to <Dispatcher …>` | роутер — змінна модуля, а диспетчерів два (API і тест) | новий роутер на кожен диспетчер: `build_router()` |
| бот відповідає `Не знаю такої команди` на кожну команду | `F.text` зареєстровано раніше за команди | `F.text` — останнім у `build_router()` |
| бот «підписав», а `/subscriptions` порожній | зміни в сесії без COMMIT | COMMIT після handler — у `InjectMiddleware` |
| `POST /api/telegram/webhook` → `503 бот вимкнений або працює через polling` | немає `BOT_TOKEN` або `TELEGRAM_WEBHOOK_URL` / секрету | це не помилка: ендпоінт працює лише в режимі webhook |
| `getUpdates` → `409 Conflict: can't use getUpdates method while webhook is active` | webhook увімкнено, а хтось питає polling | `python -m news_hub.bot` видаляє webhook сам; на сервері після цього треба перезапустити застосунок, щоб `lifespan` знову поставив webhook |
| сервер перестав отримувати update після того, як хтось запустив polling з тим самим токеном | polling викликав `deleteWebhook` | один токен — один режим; для розробки — окремий тестовий бот від @BotFather |

## Практика { #practice }

### Розібраний приклад: `/search <слово>` { #worked-example }

Задача: пошук у заголовках прямо в боті — `/search бюджет`.

1. **Звідки дані.** Пошук уже є в API (`GET /api/news/search`, `NewsRepository.search`): `icontains(q, autoescape=True)` — без урахування регістру, `%` і `_` у слові — звичайні символи. Нового SQL не треба.
2. **Що перевірити на вході.** Ті самі межі, що в API: 2–60 символів.
3. **Як показати.** Як `/news`: заголовок, список `link(...)`, `answer_lines` — частини ≤ 4096. Слово користувача — через `esc`.

```python title="news_hub/bot/handlers.py"
async def cmd_search(message: Message, command: CommandObject, news: NewsRepository) -> None:
    """/search <слово> — заголовки, що містять слово (той самий пошук, що GET /api/news/search)."""
    query = (command.args or "").strip()
    if not 2 <= len(query) <= 60:
        await message.answer("Використання: /search &lt;слово&gt; — від 2 до 60 символів")
        return
    rows = await news.search(query, limit=10)
    if not rows:
        await message.answer(f"Нічого не знайдено за «{esc(query)}»")
        return
    await answer_lines(message, [f"🔎 <b>{esc(query)}</b>: {len(rows)}", ""] +
                       [f"• {link(row.url, row.title)}" for row in rows])
```

У `build_router()` — рядок `router.message(Command("search"))(cmd_search)` перед `F.text`. Тест:

```python title="tests/integration/test_bot.py"
async def test_search(telegram: BotHarness) -> None:
    await add_news(telegram, "Уряд ухвалив бюджет на рік", "Погода на вихідні: <сонячно> & тепло")
    [found] = await telegram.say("/search БЮДЖЕТ")
    assert found.startswith("🔎 <b>БЮДЖЕТ</b>: 1") and "Погода" not in found
    [found] = await telegram.say("/search сонячно")
    assert "&lt;сонячно&gt; &amp; тепло" in found
    assert await telegram.say("/search футбол") == ["Нічого не знайдено за «футбол»"]
    assert (await telegram.say("/search я"))[0].startswith("Використання: /search")
```

```text
$ pytest -q tests/integration/test_bot.py -k search
1 passed, 10 deselected
$ mypy --strict news_hub
Success: no issues found in 26 source files
```

Що бот відповідає на `/search сонячно` і `/search 100%`:

```text
['🔎 <b>сонячно</b>: 1\n\n• <a href="https://www.rbc.ua/ukr/news/test-2.html">Погода на вихідні: &lt;сонячно&gt; &amp; тепло</a>']
['Нічого не знайдено за «100%»']
```

`100%` не знайшов **усе**: `%` — звичайний символ завдяки `autoescape=True`. Бот лише інакше **показує** той самий результат, що й API.

### Зміни приклад { #modify }

1. У `build_router()` перенеси `router.message(F.text)(unknown)` на самий початок. Що відповість бот на `/help`, `/subscribe бюджет`, `/subscriptions`?
2. В `InjectMiddleware` прибери `await session.commit()`. Надішли `/subscribe бюджет`, потім `/subscriptions`. Що побачить користувач?

??? success "Що покаже запуск"

    1. На всі три — `['Не знаю такої команди. /help — що я вмію']`. `F.text` пропускає будь-який текст, зокрема команди, а aiogram бере **перший** handler, чий фільтр підійшов.
    2. `/subscribe бюджет` → `['✅ Підписка на «бюджет»']`, але `/subscriptions` → `['Підписок немає. Додай: /subscribe &lt;слово&gt;']`. INSERT виконався в сесії, а без COMMIT вона закрилась із ROLLBACK. Бот «пообіцяв» те, чого немає в базі. Тест `test_subscriptions` це ловить.

### Спробуй самостійно: кнопка «Відписатися» { #unsubscribe-button }

Під сповіщенням — inline-кнопка «Відписатися від «бюджет»». Натискання приходить як `callback_query` з `callback_data`; бот видаляє підписку й відповідає `answer_callback_query`.

**Критерії перевірки:**

- `callback_data` не довше за 64 байти (обмеження Telegram) і не містить нічого, крім слова;
- натискання від **іншого** чату не видаляє чужу підписку (`callback_query.message.chat.id`);
- `allowed_updates` у `start_bot` пропускає `callback_query` (зараз там лише `["message"]`);
- двійник отримує `answerCallbackQuery` (додай метод `m_answerCallbackQuery` у `tests/telegram_twin.py`);
- тест у `tests/integration/test_bot.py`.

### Знайди помилку { #find-bug }

Handler привітання і його тест (тест зелений):

```python
async def cmd_start(message: Message) -> None:
    user = message.from_user
    await message.answer(f"Привіт, <b>{user.first_name}</b>!\n\nПросто напиши своє запитання.")


async def test_start_greets_user(telegram: BotHarness) -> None:
    [reply] = await telegram.say("/start", first_name="Олена")
    assert "Привіт, <b>Олена</b>!" in reply
```

Кому бот не відповість ніколи? Справжній вивід такого привітання проти двійника:

```text
'Олена': надіслано
'<Олена>': TelegramBadRequest: Telegram server says - Bad Request: can't parse entities: unexpected character at byte offset 11
'Tom & Jerry': TelegramBadRequest: Telegram server says - Bad Request: can't parse entities: unsupported entity at byte offset 15
```

??? success "Відповідь"

    Ім'я вставлено в HTML без екранування. Для Telegram `<` і `&` поза тегом — зламана розмітка, і він відхиляє все повідомлення. Бот мовчить, а користувач не розуміє чому. Тест перевіряв лише «звичайне» ім'я: даних, які ламають розмітку, у ньому не було.

    Виправлення — `esc(name)` (`html.escape`) для всього, що прийшло ззовні. Тест на це — `test_start_escapes_user_name`: ім'я `<Олена & Ко>`, а двійник, як Telegram, не пропустить невалідну розмітку.

    Друга проблема: `message.from_user` може бути `None` (повідомлення від імені каналу), і тоді `user.first_name` — `AttributeError`. У `news_hub` — `message.from_user.first_name if message.from_user else "друже"`; `mypy --strict` не пропустив би версію без перевірки.

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| `Bot` / `Dispatcher` / `Router` | клієнт Bot API / маршрутизація update / набір handler; роутер — новий на кожен диспетчер (`build_router()`) |
| Порядок handler | перший, чий фільтр підійшов; `F.text` — останній |
| Middleware | outer — до маршрутизації (ліміт 20 за 60 с), inner — перед handler (сесія бази, COMMIT) |
| Залежності в handler | за іменем параметра з `data`: `news`, `subscriptions`, `redis`, `llm`, `admin_ids` |
| HTML | усе ззовні — `esc` / `link`; ділити між рядками, ≤ 4096 |
| Сповіщення | лише нові новини (`insert_new` + `RETURNING`); після COMMIT; 403 → видалити підписки; 429 → `retry_after` |
| Polling / webhook | розробка / сервер; одночасно — ні (`409`); webhook: `https`, секрет у заголовку, `compare_digest`, `200` одразу |
| Тести | двійник Bot API: записує виклики, відтворює правила; справжній токен не потрібен |

## Самоперевірка { #self-check }

1. Чому `F.text` реєструють останнім, а порядок решти команд не важливий?
2. Що станеться з update, якщо webhook відповідатиме Telegram через 2 хвилини?
3. Навіщо розсилці `insert_new`, якщо є `add_many`?
4. Користувач заблокував бота. Що буде після наступного збору, а що — після ще одного?
5. Чому бот у режимі webhook не видаляє webhook при зупинці?
6. Чому `POST /api/telegram/webhook` у `PUBLIC`, а не під `AdminDep`? Що його захищає?
7. Що перевіряє двійник Telegram, а чого він перевірити не може?
8. Чому `BOT_ADMIN_IDS` читає `load_admin_settings`, а не `load_bot_settings`?

??? success "Відповіді"

    1. aiogram бере перший handler, чий фільтр підійшов. `F.text` підходить до будь-якого тексту, зокрема до `/start`. Фільтри команд між собою не перетинаються, тому їхній порядок не важливий.
    2. Telegram вважатиме доставку невдалою і надсилатиме update повторно — бот відповів би кілька разів. Тому `200` — одразу, а обробка — у фоні (`BackgroundTasks`).
    3. `add_many` повертає лише кількість. Для розсилки потрібно знати, **які саме** новини нові, інакше повторний збір тих самих новин знову сповістив би всіх.
    4. Перший збір: `sendMessage` → `403` → підписки чату видалено (`remove_chat`). Другий: чату немає серед підписок, запитів до нього немає.
    5. Під час перезапуску новий процес уже зареєстрував webhook. Старий, видаляючи його при зупинці, лишив би бота без update.
    6. У Telegram немає нашого JWT. Захист — секретний заголовок `X-Telegram-Bot-Api-Secret-Token`, який ми самі передали в `setWebhook`; порівняння — `compare_digest`, до розбору тіла. Тест `test_wrong_secret_is_401` перевіряє, що JWT адміна тут нічого не дає.
    7. Перевіряє формат викликів бота: метод, чат, текст, HTML за правилами документації, ліміт 4096, реакцію на `401` / `403` / `429` / `409`. Не перевіряє справжню поведінку Telegram поза цими правилами: доставку на пристрої, реальні ліміти, нові зміни API. Для цього — справжній токен і окремий тестовий бот.
    8. Щоб правило «хто адмін» було одне. Коли бот мав свій список, `/scrape` працював і без адмін-доступу API (де запис — `503`), а помилку в списку видно було лише як `ValueError`. Тепер адмін-доступ не налаштовано — адмінів немає ніде; `BOT_ADMIN_IDS` без нього або з не числовим id — `RuntimeError` при старті. А ліміт збору бот бере з тієї ж `LIMITS`, що й API.

## Що далі { #next }

[Крок 10. Docker-образ](../10_docker/index.md) — `news_hub` в образі: API, бот і міграції запускаються однаково на будь-якій машині, а `BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` та інші секрети приходять змінними середовища, не з образу.
