import html
import time

from telegram import Update
from telegram.ext import ContextTypes

import db
from handlers.common import ensure_registered, display_name, get_tg_stats, tg_stats_block
from subscription import require_subscription

WEEK_SECONDS = 7 * 24 * 3600


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, banned = await ensure_registered(update, context)
    if banned:
        await update.message.reply_text("🚫 Вы забанены в этом боте.")
        return
    if not await require_subscription(update, context):
        return

    # /profile @username или /profile 123456 — профиль другого игрока,
    # ответ командой /profile на чьё-то сообщение — профиль его автора,
    # просто /profile — свой профиль.
    target = row
    reply = update.message.reply_to_message
    if context.args:
        arg = context.args[0].strip()
        if arg.lstrip("-").isdigit():
            target = db.get_user(int(arg))
        else:
            target = db.get_user_by_username(arg.lstrip("@"))
        if not target:
            await update.message.reply_text(
                "Игрок не найден 🤷 Смотреть можно только профили тех, кто уже запускал бота."
            )
            return
    elif reply and reply.from_user and not reply.from_user.is_bot:
        target = db.get_user(reply.from_user.id)
        if not target:
            await update.message.reply_text("Этот человек ещё не запускал бота 🤷")
            return

    stats = await get_tg_stats(context, target["user_id"])
    rank = db.user_rank(target["user_id"])
    text = (
        f"👤 <b>Профиль {html.escape(display_name(target))}</b>\n\n"
        f"⭐ Рейтинг (LTN): <b>{target['rating']:.2f}</b>\n"
        f"📈 Место в рейтинге: <b>#{rank}</b>\n"
        f"✅ Побед: <b>{target['wins']}</b>   ❌ Поражений: <b>{target['losses']}</b>\n\n"
        f"{tg_stats_block(target, stats)}"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, banned = await ensure_registered(update, context)
    if banned:
        await update.message.reply_text("🚫 Вы забанены в этом боте.")
        return
    if not await require_subscription(update, context):
        return

    top = db.leaderboard(10)
    if not top:
        await update.message.reply_text("Пока в рейтинге никого нет.")
        return

    medals = ["🥇", "🥈", "🥉"]
    week = db.top_wins_since(int(time.time()) - WEEK_SECONDS, 10)
    lines = ["🔥 <b>Топ недели</b> — победы за последние 7 дней\n"]
    if week:
        for i, u in enumerate(week):
            prefix = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"{prefix} {html.escape(display_name(u))} — <b>{u['period_wins']}</b> побед")
    else:
        lines.append("За эту неделю побед ещё нет — брось вызов первым ⚔️")

    lines.append("\n🏆 <b>Общий рейтинг MOG BATTLE</b>\n")
    for i, u in enumerate(top):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} {html.escape(display_name(u))} — <b>{u['rating']:.2f}</b> (W:{u['wins']} L:{u['losses']})")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
