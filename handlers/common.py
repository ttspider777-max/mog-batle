import asyncio
import html
import logging

from telegram.ext import ContextTypes

import db

logger = logging.getLogger(__name__)

async def get_avatar_bytes(context: ContextTypes.DEFAULT_TYPE, user_id: int, timeout: float = 6):
    avatar, _count = await _with_timeout(get_avatar_info(context, user_id), timeout, (None, 0))
    return avatar


async def get_avatar_info(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Возвращает (avatar_bytes|None, кол-во фото в профиле)."""
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count == 0:
            return None, 0
        file_id = photos.photos[0][-1].file_id
        file = await context.bot.get_file(file_id)
        data = bytes(await file.download_as_bytearray())
        return data, photos.total_count
    except Exception:
        return None, 0


async def _get_chat_info(context, user_id: int):
    """(bio, официальный уровень аккаунта или None) из getChat."""
    try:
        chat = await context.bot.get_chat(user_id)
        rating = getattr(chat, "rating", None)
        return getattr(chat, "bio", None), (rating.level if rating else None)
    except Exception:
        return None, None


async def _get_gifts(context, user_id: int):
    """(всего подарков, из них NFT, суммарная цена обычных подарков в звёздах)."""
    total, nft, stars = 0, 0, 0
    offset = None
    try:
        for _ in range(5):  # до 500 подарков — больше для карточки не нужно
            page = await context.bot.get_user_gifts(user_id, offset=offset, limit=100)
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
        pass
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
    (avatar, photo_count), (bio, level), (gifts_total, nft_count, stars_value) = await asyncio.gather(
        _with_timeout(get_avatar_info(context, user_id), timeout, (None, 0)),
        _with_timeout(_get_chat_info(context, user_id), timeout, (None, None)),
        _with_timeout(_get_gifts(context, user_id), timeout, (0, 0, 0)),
    )
    return {
        "avatar": avatar,
        "photo_count": photo_count,
        "bio": bio,
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
        lines.append(f"• {label}: {html.escape(subtitle)} — <b>{score:.2f}</b>")
    total = sum(score for _, _, score in categories) / len(categories)
    lines.append(f"Итого по профилю: <b>{total:.2f}</b> / 10")
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
