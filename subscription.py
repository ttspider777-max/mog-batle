"""
Обязательная подписка на канал/чат. Администратор задаёт канал через админ-панель;
пока пользователь не подписан, использовать бота нельзя — вместо ответа на кнопку/команду
показывается сообщение с предложением подписаться и кнопкой повторной проверки.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import db

logger = logging.getLogger(__name__)

KEY_CHANNEL = "required_channel"        # @username или numeric chat id — для проверки через API
KEY_CHANNEL_LINK = "required_channel_link"    # ссылка для кнопки "Перейти в канал"
KEY_CHANNEL_TITLE = "required_channel_title"  # человекочитаемое название для текста


def get_required_channel() -> str:
    return db.get_setting(KEY_CHANNEL, "")


def set_required_channel(channel: str, title: str = "", link: str = ""):
    db.set_setting(KEY_CHANNEL, channel)
    db.set_setting(KEY_CHANNEL_TITLE, title or channel)
    db.set_setting(KEY_CHANNEL_LINK, link)


def clear_required_channel():
    db.set_setting(KEY_CHANNEL, "")
    db.set_setting(KEY_CHANNEL_TITLE, "")
    db.set_setting(KEY_CHANNEL_LINK, "")


def _is_member(member) -> bool:
    if member.status in ("creator", "administrator", "member"):
        return True
    # "restricted" — участник с ограничениями; он подписан, только если is_member=True
    return member.status == "restricted" and bool(getattr(member, "is_member", False))


async def check_bot_access(context, channel) -> str:
    """Проверяет, может ли бот видеть подписчиков канала. Возвращает "" если всё ок,
    иначе текст проблемы. Для проверки подписки Telegram требует, чтобы бот был
    АДМИНИСТРАТОРОМ канала — без этого он получает ошибку "Member list is inaccessible"."""
    try:
        me = await context.bot.get_chat_member(chat_id=channel, user_id=context.bot.id)
    except Exception as e:
        return f"бот не может получить список участников ({e})"
    if me.status not in ("administrator", "creator"):
        return "бот не является администратором этого канала/чата"
    return ""


async def is_subscribed(context, user_id: int) -> bool:
    channel = get_required_channel()
    if not channel:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
        return _is_member(member)
    except Exception as e:
        # Если проверка сломалась (бот перестал быть админом канала и т.п.) — не блокируем
        # всех пользователей из-за ошибки настройки, но громко пишем об этом в лог.
        # Состояние проверки видно в /admin.
        logger.warning("Проверка подписки на %s не работает: %s", channel, e)
        return True


def subscription_keyboard() -> InlineKeyboardMarkup:
    link = db.get_setting(KEY_CHANNEL_LINK, "")
    rows = []
    if link:
        rows.append([InlineKeyboardButton("📢 Перейти в канал", url=link)])
    rows.append([InlineKeyboardButton("✅ Я подписался", callback_data="sub:check")])
    return InlineKeyboardMarkup(rows)


async def send_subscription_gate(update, context):
    title = db.get_setting(KEY_CHANNEL_TITLE, "") or "наш канал"
    text = (
        f"📢 Чтобы пользоваться ботом, подпишись на {title}.\n\n"
        f"После подписки нажми «✅ Я подписался»."
    )
    if update.callback_query:
        await update.callback_query.answer("Сначала подпишись на канал 📢", show_alert=True)
        # у inline-сообщений (отправленных через «📤 Отправить в чат») нет message —
        # тогда пишем человеку в личку (сработает, если он хоть раз запускал бота)
        msg = update.callback_query.message
        chat_id = msg.chat_id if msg else update.callback_query.from_user.id
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=subscription_keyboard())
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(text, reply_markup=subscription_keyboard())


async def require_subscription(update, context) -> bool:
    """True — можно продолжать выполнение хендлера как обычно.
    False — уже отправили пользователю просьбу подписаться, дальше обрабатывать не нужно."""
    user = update.effective_user
    if not user:
        return True
    if await is_subscribed(context, user.id):
        return True
    await send_subscription_gate(update, context)
    return False
