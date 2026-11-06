import html

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import db
from handlers.common import ensure_registered, display_name, get_tg_stats, tg_stats_block
from subscription import require_subscription


def me_keyboard(card_style: str):
    style = card_style or "neon"
    classic_label = "⚪ Classic ✅" if style == "classic" else "⚪ Classic"
    neon_label = "🎄 New Year ✅" if style == "neon" else "🎄 New Year"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Изменить статус", callback_data="me:edit_status")],
        [
            InlineKeyboardButton(classic_label, callback_data="me:style:classic"),
            InlineKeyboardButton(neon_label, callback_data="me:style:neon"),
        ],
    ])


def _profile_text(row: dict, stats: dict) -> str:
    rank = db.user_rank(row["user_id"])
    status = html.escape(row.get("custom_status") or "не указан")
    style = "🎄 New Year" if (row.get("card_style") or "neon") == "neon" else "⚪ Classic"
    return (
        f"👤 <b>{html.escape(display_name(row))}</b>\n\n"
        f"⭐ Рейтинг (LTN): <b>{row['rating']:.2f}</b>\n"
        f"📈 Место в рейтинге: <b>#{rank}</b>\n"
        f"✅ Побед: <b>{row['wins']}</b>   ❌ Поражений: <b>{row['losses']}</b>\n\n"
        f"{tg_stats_block(row, stats)}\n\n"
        f"📝 Статус: {status}\n"
        f"🎨 Дизайн карточки вызова: {style}\n\n"
        f"<i>Статус виден в этом профиле и учитывается в категории «О себе» на карточке "
        f"результата баттла.</i>"
    )


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, banned = await ensure_registered(update, context)
    if banned:
        await update.message.reply_text("🚫 Вы забанены в этом боте.")
        return
    if not await require_subscription(update, context):
        return
    stats = await get_tg_stats(context, row["user_id"])
    await update.message.reply_text(
        _profile_text(row, stats), parse_mode="HTML", reply_markup=me_keyboard(row.get("card_style"))
    )


async def me_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data.split(":", 1)[1]

    row, banned = await ensure_registered(update, context)
    if banned:
        await query.answer("🚫 Вы забанены в этом боте.", show_alert=True)
        return
    if not await require_subscription(update, context):
        return

    if action == "edit_status":
        context.user_data["awaiting_status"] = True
        db.set_admin_state(row["user_id"], "")  # чтобы статус не ушёл в админ-режим
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Пришли новый текст статуса (до 60 символов).",
        )
        return

    if action.startswith("style:"):
        style = action.split(":", 1)[1]
        if style not in ("classic", "neon"):
            await query.answer()
            return
        db.set_card_style(row["user_id"], style)
        row = db.get_user(row["user_id"])
        stats = await get_tg_stats(context, row["user_id"])
        await query.edit_message_text(
            _profile_text(row, stats), parse_mode="HTML", reply_markup=me_keyboard(row.get("card_style"))
        )
        await query.answer("Дизайн обновлён ✅")
        return

    await query.answer()


async def me_status_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Вызывается из общего текстового роутера. Возвращает True, если сообщение
    было обработано (пользователь как раз вводит новый статус)."""
    if not context.user_data.get("awaiting_status"):
        return False
    if not update.message or not update.message.text:
        return False

    text = update.message.text.strip()[:60]
    db.set_custom_status(update.effective_user.id, text)
    context.user_data.pop("awaiting_status", None)
    await update.message.reply_text(f"✅ Статус обновлён: {text}")
    return True
