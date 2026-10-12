import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

import db
from keyboards import MAIN_MENU
from handlers.common import ensure_registered
from subscription import require_subscription

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024  # Telegram не даёт подпись к фото длиннее этого


def _fill_name(text: str, name: str, escaped: bool) -> str:
    """Подставляет имя вместо <ник> / {ник} / {name} в тексте приветствия."""
    # в HTML-версии "<ник>" хранится как "&lt;ник&gt;"
    placeholders = ["&lt;ник&gt;"] if escaped else ["<ник>"]
    placeholders += ["{ник}", "{name}"]
    value = html.escape(name) if escaped else name
    for p in placeholders:
        text = text.replace(p, value)
    return text


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, banned = await ensure_registered(update, context)
    if banned:
        await update.message.reply_text("🚫 Вы забанены в этом боте.")
        return

    if not await require_subscription(update, context):
        return

    name = update.effective_user.first_name or "друг"
    plain = _fill_name(db.get_setting("welcome_text", "Добро пожаловать в MOG BATTLE!"), name, False)
    rich = db.get_setting("welcome_html", "")
    rich = _fill_name(rich, name, True) if rich else ""
    photo_id = db.get_setting("welcome_photo_file_id", "")

    async def send(text: str, parse_mode):
        if photo_id and len(text) <= CAPTION_LIMIT:
            await update.message.reply_photo(
                photo=photo_id, caption=text, parse_mode=parse_mode, reply_markup=MAIN_MENU
            )
            return
        if photo_id:  # текст длиннее лимита подписи — фото и текст отдельно
            await update.message.reply_photo(photo=photo_id)
        await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=MAIN_MENU)

    if rich:
        try:
            await send(rich, "HTML")
            return
        except Exception:
            # например, Telegram не разрешил какое-то оформление — шлём обычным текстом
            logger.exception("Не удалось отправить приветствие с оформлением")
    await send(plain, None)
