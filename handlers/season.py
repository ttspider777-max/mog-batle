import html
import time

from telegram import Update
from telegram.ext import ContextTypes

import db
from config import (
    SEASONS_TOTAL, POINTS_WIN, POINTS_UPSET, POINTS_STREAK_MAX, POINTS_CHAT, CHAT_COOLDOWN,
    CHAT_DAILY_CAP, PAIR_DAILY_FULL,
)
from handlers.common import ensure_registered, display_name
from subscription import require_subscription

MEDALS = ["🥇", "🥈", "🥉"]


def rules_text() -> str:
    return (
        "📜 <b>Как считаются очки сезона</b>\n"
        f"• Победа в баттле «мог»: <b>+{POINTS_WIN}</b> (проигравший очков не получает)\n"
        f"• Победил соперника с рейтингом выше: <b>+{POINTS_UPSET}</b>\n"
        f"• Винстрик: <b>+1</b> за каждую победу подряд сверх первой (максимум +{POINTS_STREAK_MAX})\n"
        f"• Написал «мог» в группе, где есть бот: <b>+{POINTS_CHAT}</b> "
        f"(не чаще раза в {CHAT_COOLDOWN} с, максимум {CHAT_DAILY_CAP} очк. в сутки)\n"
        f"• Победы над одним и тем же соперником дают очки только первые {PAIR_DAILY_FULL} раза за сутки\n"
        "🏆 Победитель сезона получает NFT."
    )


def season_text(user_id=None) -> str:
    season = db.active_season()
    lines = []
    if season:
        lines.append(f"🏅 <b>Сезон {season['number']} из {SEASONS_TOTAL}</b> — идёт")
        if season.get("prize"):
            lines.append(f"🎁 Приз: <b>{html.escape(season['prize'])}</b>")
        top = db.season_standings(season["id"], 10)
        lines.append("")
        if top:
            for i, u in enumerate(top):
                prefix = MEDALS[i] if i < 3 else f"{i + 1}."
                lines.append(
                    f"{prefix} {html.escape(display_name(u))} — <b>{u['season_points']}</b> очк. "
                    f"(побед: {u['season_wins']})"
                )
        else:
            lines.append("Очков пока ни у кого нет — «мог» первым! ⚔️")
        if user_id:
            place = db.season_place(season["id"], user_id)
            lines.append("")
            lines.append(
                f"📍 Ты: #{place[0]} — <b>{place[1]}</b> очк., побед {place[2]}" if place
                else "📍 У тебя пока нет очков в этом сезоне."
            )
    else:
        nxt = db.next_season_number()
        lines.append("🏅 <b>Сезоны MOG BATTLE</b>")
        lines.append(
            f"Сейчас сезон не идёт. Следующий — сезон {nxt} из {SEASONS_TOTAL}, ждём запуска! ⏳"
            if nxt else f"Все {SEASONS_TOTAL} сезона сыграны."
        )
    done = db.finished_seasons()
    if done:
        lines.append("")
        lines.append("🏆 <b>Победители прошлых сезонов</b>")
        for s in done:
            w = db.get_user(s["winner_id"]) if s["winner_id"] else None
            lines.append(f"Сезон {s['number']}: {html.escape(display_name(w)) if w else '—'}")
    lines.append("")
    lines.append(rules_text())
    return "\n".join(lines)


async def season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, banned = await ensure_registered(update, context)
    if banned:
        await update.message.reply_text("🚫 Вы забанены в этом боте.")
        return
    if not await require_subscription(update, context):
        return
    await update.message.reply_text(season_text(row["user_id"]), parse_mode="HTML")


async def finish_and_announce(context: ContextTypes.DEFAULT_TYPE, season: dict) -> str:
    """Завершает сезон: определяет победителя, пишет победителю и админам, рассылает итоги
    всем игрокам. Возвращает текст итогов. NFT бот выдать не может — выдаёт админ вручную."""
    from config import ADMIN_IDS

    winner, top = db.finish_season(season["id"])
    lines = [f"🏁 <b>Сезон {season['number']} завершён!</b>", ""]
    if winner:
        for i, u in enumerate(top):
            lines.append(f"{MEDALS[i]} {html.escape(display_name(u))} — <b>{u['season_points']}</b> очк.")
        lines.append("")
        lines.append(f"👑 Победитель: <b>{html.escape(display_name(winner))}</b> — он получает NFT!")
        if season.get("prize"):
            lines.append(f"🎁 Приз: {html.escape(season['prize'])}")
    else:
        lines.append("Никто не набрал очков — победителя нет.")
    summary = "\n".join(lines)

    if winner:
        try:
            await context.bot.send_message(
                chat_id=winner["user_id"],
                text=f"🎉 Поздравляем! Ты победил в сезоне {season['number']} MOG BATTLE!\n"
                     f"Администратор свяжется с тобой, чтобы передать NFT.",
            )
        except Exception:
            pass
    admin_note = summary + (
        f"\n\n⚠️ Передай NFT вручную: ID победителя <code>{winner['user_id']}</code>." if winner else ""
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_note, parse_mode="HTML")
        except Exception:
            pass
    for uid in db.all_user_ids():
        if uid in ADMIN_IDS:
            continue
        try:
            await context.bot.send_message(chat_id=uid, text=summary, parse_mode="HTML")
        except Exception:
            pass
    return summary
