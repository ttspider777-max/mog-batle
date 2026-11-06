import asyncio
import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

import db
from images_ny import render_welcome_card
from keyboards import MAIN_MENU
from handlers.common import ensure_registered
from subscription import require_subscription

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024  # Telegram не даёт подпись к фото длиннее этого

_banner_bytes = None  # новогодний баннер рисуется один раз и переиспользуется


async def _welcome_photo():
    """Фото приветствия: загруженное админом (file_id) или новогодний баннер — тогда
    сначала пробуем file_id, который Telegram уже выдал, иначе рисуем картинку."""
    global _banner_bytes
    file_id = db.get_setting("welcome_photo_file_id", "") or db.get_setting("welcome_banner_file_id", "")
    if file_id:
        return file_id, False
    if _banner_bytes is None:
        _banner_bytes = (await asyncio.to_thread(render_welcome_card, 0)).getvalue()
    return _banner_bytes, True


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
    try:
        photo_id, is_new = await _welcome_photo()
    except Exception:
        logger.exception("Не удалось подготовить карточку приветствия")
        photo_id, is_new = "", False

    async def send(text: str, parse_mode):
        if photo_id and len(text) <= CAPTION_LIMIT:
            msg = await update.message.reply_photo(
                photo=photo_id, caption=text, parse_mode=parse_mode, reply_markup=MAIN_MENU
            )
            if is_new and msg.photo:  # запоминаем file_id — следующим людям уйдёт мгновенно
                db.set_setting("welcome_banner_file_id", msg.photo[-1].file_id)
            return
        if photo_id:  # текст длиннее лимита подписи — фото и текст отдельно
            msg = await update.message.reply_photo(photo=photo_id)
            if is_new and msg.photo:
                db.set_setting("welcome_banner_file_id", msg.photo[-1].file_id)
        await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=MAIN_MENU)

    if rich:
        try:
            await send(rich, "HTML")
            return
        except Exception:
            # например, Telegram не разрешил какое-то оформление — шлём обычным текстом
            logger.exception("Не удалось отправить приветствие с оформлением")
    await send(plain, None)
