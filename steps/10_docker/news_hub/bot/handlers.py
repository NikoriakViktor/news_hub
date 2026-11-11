"""Команди бота агрегатора. Урок 47.

Основа — `app/handlers/commands.py` зі стартового `ai_bot`: `Router`, `CommandStart()`, `Command(...)`,
залежності в параметрах handler (з `InjectMiddleware`). Рефакторинг:
- замість розмови з LLM — команди новинного агрегатора над тим самим `NewsRepository`, що в API;
- кожен рядок, що прийшов ззовні (ім'я, заголовок, слово), — через `esc` / `link` (formatting.py);
- `/scrape` — лише для `BOT_ADMIN_IDS`: бот — ще один вхід у застосунок, і правило «хто може
  змінювати» (урок 46) діє й тут.

Порядок у роутері важливий: aiogram перевіряє handlers згори донизу, тому «будь-який текст» — останній.
Роутер будує функція `build_router()`, а не змінна модуля: aiogram прив'язує Router лише до одного
Dispatcher, а диспетчерів у процесі буває кілька (API, тести, ноутбук).
"""
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from redis.asyncio import Redis

from ..analysis import AnalysisCache, analyze_news
from ..llm import LLMClient, LLMError
from ..models import validate_news
from ..notify import notify_subscribers
from ..repository import NewsRepository, SubscriptionRepository
from ..scraper import scrape_all_async
from ..snapshot import load_snapshot
from .formatting import esc, link, normalize_keyword, split_message

logger = logging.getLogger("news_hub")

NEWS_DEFAULT, NEWS_MAX = 5, 10
DIGEST_NEWS, DIGEST_ANALYZE = 10, 3          # у дайджесті 10 новин; нових аналізів LLM — не більше 3
MAX_SUBSCRIPTIONS = 10

HELP = (
    "<b>Команди</b>\n"
    "/news [N] — останні новини (до 10)\n"
    "/digest — дайджест: тема й тональність за аналізом LLM\n"
    "/subscribe &lt;слово&gt; — сповіщати про новини з цим словом\n"
    "/unsubscribe &lt;слово&gt; — скасувати\n"
    "/subscriptions — мої підписки\n"
    "/help — ця довідка"
)


async def answer_lines(message: Message, lines: list[str]) -> None:
    for part in split_message(lines):
        await message.answer(part, disable_web_page_preview=True)


async def cmd_start(message: Message) -> None:
    name = message.from_user.first_name if message.from_user else "друже"
    await message.answer(f"Привіт, <b>{esc(name)}</b>! Я бот новинного агрегатора news_hub.\n\n{HELP}")


async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


async def cmd_news(message: Message, command: CommandObject, news: NewsRepository) -> None:
    count = NEWS_DEFAULT
    if command.args:
        if not command.args.strip().isdigit():
            await message.answer(f"Використання: /news [1–{NEWS_MAX}]")
            return
        count = max(1, min(int(command.args), NEWS_MAX))
    rows = await news.latest(count)
    if not rows:
        await message.answer("Новин поки немає.")
        return
    await answer_lines(message, [f"📰 <b>Останні новини</b> ({len(rows)})", ""] +
                       [f"• {link(row.url, row.title)} <i>{esc(row.category)}</i>" for row in rows])


async def cmd_digest(message: Message, news: NewsRepository, llm: LLMClient | None, redis: Redis) -> None:
    rows = await news.latest(DIGEST_NEWS)
    if not rows:
        await message.answer("Новин поки немає.")
        return
    note = ""
    pending = [row for row in rows if row.analyzed_at is None][:DIGEST_ANALYZE]
    if pending and llm is None:
        note = "LLM не налаштовано — у дайджесті лише вже проаналізовані новини."
        pending = []
    for row in pending:
        assert llm is not None
        try:
            result = await analyze_news(row.title, llm, AnalysisCache(redis))
        except LLMError as error:
            note = f"Частину новин не проаналізовано: {esc(str(error))[:200]}"
            break
        await news.save_analysis(row, result.analysis)
    analyzed = [row for row in rows if row.analyzed_at is not None]
    if not analyzed:
        await message.answer(note or "Ще немає проаналізованих новин.")
        return
    moods: dict[str, int] = {}
    for row in analyzed:
        moods[row.sentiment or "?"] = moods.get(row.sentiment or "?", 0) + 1
    lines = [f"🧭 <b>Дайджест</b>: {len(analyzed)} з {len(rows)} останніх новин",
             "Тональність: " + ", ".join(f"{esc(mood)} — {count}" for mood, count in sorted(moods.items())), ""]
    lines += [f"• <b>{esc(row.ai_category or '')}</b>: {esc(row.summary or row.title)} — {link(row.url, 'джерело')}"
              for row in analyzed]
    if note:
        lines += ["", f"<i>{note}</i>"]
    await answer_lines(message, lines)


async def cmd_subscribe(message: Message, command: CommandObject, subscriptions: SubscriptionRepository) -> None:
    keyword = normalize_keyword(command.args or "")
    if keyword is None:
        await message.answer("Використання: /subscribe &lt;слово&gt; — одне слово, 2–40 літер")
        return
    current = await subscriptions.for_chat(message.chat.id)
    if keyword not in current and len(current) >= MAX_SUBSCRIPTIONS:
        await message.answer(f"Не більше {MAX_SUBSCRIPTIONS} підписок. Скасуй якусь: /unsubscribe &lt;слово&gt;")
        return
    added = await subscriptions.subscribe(message.chat.id, keyword)
    await message.answer(f"✅ Підписка на «{esc(keyword)}»" if added else f"Підписка на «{esc(keyword)}» уже є")


async def cmd_unsubscribe(message: Message, command: CommandObject, subscriptions: SubscriptionRepository) -> None:
    keyword = normalize_keyword(command.args or "")
    removed = keyword is not None and await subscriptions.unsubscribe(message.chat.id, keyword)
    await message.answer(f"Підписку на «{esc(keyword or '')}» скасовано" if removed else "Такої підписки немає")


async def cmd_subscriptions(message: Message, subscriptions: SubscriptionRepository) -> None:
    keywords = await subscriptions.for_chat(message.chat.id)
    await message.answer("Твої підписки: " + ", ".join(f"«{esc(k)}»" for k in keywords) if keywords
                         else "Підписок немає. Додай: /subscribe &lt;слово&gt;")


async def cmd_scrape(message: Message, command: CommandObject, bot: Bot, news: NewsRepository,
                     subscriptions: SubscriptionRepository, admin_ids: frozenset[int]) -> None:
    """Адмін-команда: зібрати новини (`/scrape snapshot` — зі знімка) і сповістити підписників."""
    if message.from_user is None or message.from_user.id not in admin_ids:
        logger.warning("/scrape від не-адміна %s", message.from_user.id if message.from_user else None)
        await message.answer("Ця команда — лише для адміністратора.")
        return
    raw = load_snapshot() if (command.args or "").strip() == "snapshot" else (await scrape_all_async()).news
    valid, rejected = validate_news(raw)
    new = await news.insert_new(valid)
    report = await notify_subscribers(bot, subscriptions, new)
    await message.answer(f"Зібрано: {len(raw)}, нових: {len(new)}, відхилено: {len(rejected)}; "
                         f"сповіщено чатів: {report.chats}")


async def unknown(message: Message) -> None:
    await message.answer("Не знаю такої команди. /help — що я вмію")


def build_router() -> Router:
    """Новий Router з усіма командами. Порядок реєстрації = порядок перевірки."""
    router = Router(name="news_hub")
    router.message(CommandStart())(cmd_start)
    router.message(Command("help"))(cmd_help)
    router.message(Command("news"))(cmd_news)
    router.message(Command("digest"))(cmd_digest)
    router.message(Command("subscribe"))(cmd_subscribe)
    router.message(Command("unsubscribe"))(cmd_unsubscribe)
    router.message(Command("subscriptions"))(cmd_subscriptions)
    router.message(Command("scrape"))(cmd_scrape)
    router.message(F.text)(unknown)
    return router
