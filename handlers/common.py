import asyncio
import html
import logging

from telegram.ext import ContextTypes

import db

logger = logging.getLogger(__name__)

async def get_avatar_bytes(context: ContextTypes.DEFAULT_TYPE, user_id: int, timeout: float = 6):
    avatar, _count = await _with_timeout(get_avatar_info(context, user_id), timeout, (None, None))
    return avatar


async def get_avatar_info(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Возвращает (avatar_bytes|None, кол-во фото в профиле | None, если узнать не удалось)."""
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
    except Exception:
        return None, None
    if photos.total_count == 0:
        return None, 0
    try:
        file = await context.bot.get_file(photos.photos[0][-1].file_id)
        return bytes(await file.download_as_bytearray()), photos.total_count
    except Exception:
        return None, photos.total_count


async def _get_chat_info(context, user_id: int):
    """(bio, официальный уровень аккаунта или None, получилось ли вообще) из getChat."""
    try:
        chat = await context.bot.get_chat(user_id)
        rating = getattr(chat, "rating", None)
        return getattr(chat, "bio", None), (rating.level if rating else None), True
    except Exception:
        return None, None, False


async def _get_gifts(context, user_id: int):
    """(всего подарков, из них NFT, суммарная цена обычных подарков в звёздах);
    None, если запрос не удался — это «нет данных», а не «подарков нет»."""
    total, nft, stars = 0, 0, 0
    got_any = False
    offset = None
    try:
        for _ in range(5):  # до 500 подарков — больше для карточки не нужно
            page = await context.bot.get_user_gifts(user_id, offset=offset, limit=100)
            got_any = True
            total = page.total_count
            for owned in page.gifts:
                if owned.type == "unique":
                    nft += 1
                else:
                    stars += owned.gift.star_count or 0
            offset = page.next_offset
            if not offset:
                break
    except Exception:
        if not got_any:
            return None
    return total, nft, stars


async def _with_timeout(coro, timeout: float, default):
    """Не даём одному медленному запросу к Telegram подвесить весь баттл:
    если ответа нет за timeout секунд — берём значение по умолчанию."""
    try:
        return await asyncio.wait_for(coro, timeout)
    except Exception:
        logger.warning("Запрос статистики Telegram не уложился в %s с — пропускаю", timeout)
        return default


async def get_tg_stats(context: ContextTypes.DEFAULT_TYPE, user_id: int, timeout: float = 8) -> dict:
    """Настоящая статистика профиля Telegram — всё, что Bot API реально отдаёт боту.
    Запросы идут параллельно, каждый ограничен по времени."""
    (avatar, photo_count), (bio, level, bio_known), gifts = await asyncio.gather(
        _with_timeout(get_avatar_info(context, user_id), timeout, (None, None)),
        _with_timeout(_get_chat_info(context, user_id), timeout, (None, None, False)),
        _with_timeout(_get_gifts(context, user_id), timeout, None),
    )
    gifts_total, nft_count, stars_value = gifts if gifts else (None, 0, None)
    return {
        "avatar": avatar,
        "photo_count": photo_count,
        "bio": bio,
        "bio_known": bio_known,
        "level": level,
        "gifts_total": gifts_total,
        "nft_count": nft_count,
        "stars_value": stars_value,
    }


def tg_stats_block(user_row: dict, stats: dict) -> str:
    """HTML-блок «Статистика Telegram» для профиля — те же категории и баллы,
    что и на карточке результата баттла."""
    import scoring  # локальный импорт, чтобы не было циклических зависимостей
    categories = scoring.compute_categories(
        user_row["user_id"], user_row.get("username"), stats,
        bool(user_row.get("is_premium")), custom_status=user_row.get("custom_status"),
    )
    lines = ["📊 <b>Статистика Telegram</b>"]
    for label, subtitle, score in categories:
        shown = "—" if score is None else f"{score:.2f}"
        lines.append(f"• {label}: {html.escape(subtitle)} — <b>{shown}</b>")
    total = scoring.total_score(categories)
    lines.append(f"Итого по профилю: <b>{total:.2f}</b> / 10")
    if any(c[2] is None for c in categories):
        lines.append("<i>«—» — данных нет (скрыто или Telegram не ответил), в итог не входит.</i>")
    return "\n".join(lines)


def display_name(user_row: dict) -> str:
    if user_row.get("username"):
        return f"@{user_row['username']}"
    return user_row.get("first_name") or "Игрок"


async def ensure_registered(update, context):
    """Регистрирует пользователя при любом взаимодействии, возвращает (user_row, banned: bool)."""
    tg_user = update.effective_user
    row, _created = db.get_or_create_user(
        tg_user.id, tg_user.username, tg_user.first_name,
        is_premium=bool(getattr(tg_user, "is_premium", False))
    )
    return row, bool(row["banned"])
