import asyncio
import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

import db
import subscription
from config import ADMIN_IDS
from keyboards import admin_menu_keyboard, admin_cancel_keyboard, challenge_keyboard
from images import render_challenge_card, render_result_card
from handlers.common import display_name, get_avatar_bytes


logger = logging.getLogger(__name__)

# меняй при каждом обновлении — видно в /admin, так легко понять, что Amvera
# действительно запустила новую версию, а не старую
BOT_VERSION = "2026-09-27 v5"


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def clear_photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/clear_photo — убрать фото приветствия. Отдельная команда, потому что
    команды не доходят до текстового роутера админки (раньше она не работала)."""
    if not is_admin(update.effective_user.id):
        return
    db.set_setting("welcome_photo_file_id", "")
    db.set_admin_state(update.effective_user.id, "")
    await update.message.reply_text("✅ Фото приветствия убрано.")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return  # для всех остальных команда как будто не существует
    db.set_admin_state(update.effective_user.id, "")
    total = db.total_users()
    channel = subscription.get_required_channel()
    if channel:
        title = html.escape(db.get_setting(subscription.KEY_CHANNEL_TITLE, "") or channel)
        problem = await subscription.check_bot_access(context, channel)
        if problem:
            sub_line = (
                f"📢 Обязательная подписка: <b>{title}</b>\n"
                f"⚠️ <b>НЕ РАБОТАЕТ</b>: {html.escape(problem)}. Сделай бота администратором "
                f"канала — до этого бот пускает всех без проверки."
            )
        else:
            sub_line = f"📢 Обязательная подписка: <b>{title}</b> ✅ проверка работает"
    else:
        sub_line = "📢 Обязательная подписка: выключена"
    await update.message.reply_text(
        f"🛠 <b>Админ-панель MOG BATTLE</b>\n\n"
        f"👥 Пользователей запустило бота: <b>{total}</b>\n"
        f"{sub_line}\n\n"
        f"<i>Версия бота: {BOT_VERSION}</i>",
        parse_mode="HTML",
        reply_markup=admin_menu_keyboard(),
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(update.effective_user.id):
        await query.answer("Недоступно", show_alert=True)
        return

    action = query.data.split(":", 1)[1]

    if action == "cancel":
        db.set_admin_state(update.effective_user.id, "")
        await query.edit_message_text("Отменено.")
        return

    if action == "stats":
        total = db.total_users()
        top = db.leaderboard(5)
        lines = [f"👥 Всего пользователей: <b>{total}</b>", "", "🏆 Топ-5:"]
        for i, u in enumerate(top, 1):
            lines.append(f"{i}. {display_name(u)} — {u['rating']:.2f} (W:{u['wins']} L:{u['losses']})")
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")
        return

    if action == "users":
        users = db.all_users_full(50)
        if not users:
            await query.edit_message_text("Пользователей пока нет.")
            return
        lines = ["👥 <b>Пользователи</b> (последние 50, новые сверху)\n"]
        for u in users:
            banned = " 🚫забанен" if u["banned"] else ""
            uname = f"@{u['username']}" if u["username"] else (u["first_name"] or "—")
            lines.append(f"<code>{u['user_id']}</code> — {uname} — {u['rating']:.2f}{banned}")
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")
        return

    if action == "leaderboard":
        top = db.leaderboard(20)
        if not top:
            await query.edit_message_text("Рейтинг пуст.")
            return
        lines = ["🏆 <b>Полный рейтинг</b>\n"]
        for i, u in enumerate(top, 1):
            banned = " 🚫" if u["banned"] else ""
            lines.append(f"{i}. {display_name(u)} (id {u['user_id']}) — {u['rating']:.2f}{banned}")
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")
        return

    prompts = {
        "set_welcome": (
            "Пришли новый текст приветствия.\n"
            "Можно прислать текст, или фото с подписью (фото станет картинкой приветствия, "
            "подпись — текстом). Чтобы убрать текущее фото приветствия — пришли команду /clear_photo."
        ),
        "broadcast": "Пришли текст (или фото с подписью), который нужно разослать всем пользователям бота от имени бота.",
        "ban": "Пришли Telegram ID пользователя, которого нужно забанить (число).",
        "unban": "Пришли Telegram ID пользователя, которого нужно разбанить (число).",
        "send_battle": "Пришли ID вызова (число, из подписи под карточкой), который нужно разослать всем пользователям бота.",
        "set_required_channel": (
            "Пришли юзернейм канала/чата (например @mychannel) или его числовой ID.\n\n"
            "⚠️ Бот должен быть добавлен в этот канал/чат как АДМИНИСТРАТОР — иначе "
            "проверка подписки работать не будет.\n\n"
            "Чтобы ВЫКЛЮЧИТЬ обязательную подписку — пришли слово off."
        ),
    }
    if action in prompts:
        db.set_admin_state(update.effective_user.id, f"awaiting_{action}")
        # если до этого начинал менять статус в /me — отменяем, иначе текст уйдёт туда
        context.user_data.pop("awaiting_status", None)
        await query.answer()
        await query.edit_message_text(prompts[action], reply_markup=admin_cancel_keyboard())
        return

    await query.answer()


async def admin_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ответ администратора на один из режимов admin_state.
    Возвращает True, если сообщение было обработано (и дальнейшие хендлеры звать не нужно)."""
    if not is_admin(update.effective_user.id):
        return False

    admin_id = update.effective_user.id
    state = db.get_admin_state(admin_id)
    message = update.message
    logger.info("admin %s прислал сообщение, режим админки: %r", admin_id, state or None)
    if not state or not message:
        return False

    if state == "awaiting_set_welcome":
        # сохраняем вместе с оформлением (жирный, цитаты, эмодзи) в виде HTML
        if message.photo:
            db.set_setting("welcome_photo_file_id", message.photo[-1].file_id)
            if message.caption:
                db.set_setting("welcome_text", message.caption)
                db.set_setting("welcome_html", message.caption_html)
            await message.reply_text("✅ Приветствие обновлено (фото). Проверь через /start.")
        elif message.text:
            db.set_setting("welcome_text", message.text)
            db.set_setting("welcome_html", message.text_html)
            await message.reply_text("✅ Текст приветствия обновлён. Проверь через /start.")
        else:
            await message.reply_text("Пришли текст или фото с подписью.")
            return True
        db.set_admin_state(admin_id, "")
        return True

    if state == "awaiting_broadcast":
        ids = db.all_user_ids()
        sent, failed = 0, 0
        for uid in ids:
            try:
                if message.photo:
                    await context.bot.send_photo(
                        chat_id=uid, photo=message.photo[-1].file_id, caption=message.caption or ""
                    )
                else:
                    await context.bot.send_message(chat_id=uid, text=message.text)
                sent += 1
            except Exception:
                failed += 1
        await message.reply_text(f"📢 Рассылка завершена. Доставлено: {sent}, ошибок: {failed}.")
        db.set_admin_state(admin_id, "")
        return True

    if state in ("awaiting_ban", "awaiting_unban"):
        text = (message.text or "").strip()
        if not text.isdigit():
            await message.reply_text("Нужно прислать числовой Telegram ID. Попробуй ещё раз.")
            return True
        user_id = int(text)
        ban = state == "awaiting_ban"
        db.set_banned(user_id, ban)
        await message.reply_text(
            f"{'🚫 Пользователь ' + str(user_id) + ' забанен.' if ban else '✅ Пользователь ' + str(user_id) + ' разбанен.'}"
        )
        db.set_admin_state(admin_id, "")
        return True

    if state == "awaiting_send_battle":
        text = (message.text or "").strip()
        if not text.isdigit():
            await message.reply_text("Нужно прислать числовой ID вызова. Попробуй ещё раз.")
            return True
        battle_id = int(text)
        battle = db.get_battle(battle_id)
        if not battle:
            await message.reply_text("Вызов с таким ID не найден.")
            db.set_admin_state(admin_id, "")
            return True

        challenger_row = db.get_user(battle["challenger_id"])
        ids = db.all_user_ids()
        sent, failed = 0, 0

        if battle["status"] == "open":
            avatar = await get_avatar_bytes(context, challenger_row["user_id"])
            challenger = {
                "name": challenger_row["first_name"] or "Игрок",
                "username": challenger_row["username"] or "",
                "rating": challenger_row["rating"],
            }
            for uid in ids:
                try:
                    buf = await asyncio.to_thread(render_challenge_card, challenger, avatar)
                    await context.bot.send_photo(
                        chat_id=uid, photo=buf,
                        caption=f"⚔️ Открытый вызов от {display_name(challenger_row)}!\nID вызова: {battle_id}",
                        reply_markup=challenge_keyboard(battle_id)
                    )
                    sent += 1
                except Exception:
                    failed += 1
        else:
            opponent_row = db.get_user(battle["opponent_id"])
            winner_side = "left" if battle["winner_id"] == challenger_row["user_id"] else "right"
            c_avatar = await get_avatar_bytes(context, challenger_row["user_id"])
            o_avatar = await get_avatar_bytes(context, opponent_row["user_id"])
            challenger = {"name": challenger_row["first_name"], "username": challenger_row["username"],
                          "rating": challenger_row["rating"], "avatar": c_avatar}
            opponent = {"name": opponent_row["first_name"], "username": opponent_row["username"],
                        "rating": opponent_row["rating"], "avatar": o_avatar}
            for uid in ids:
                try:
                    buf = await asyncio.to_thread(render_result_card, challenger, opponent, winner_side)
                    await context.bot.send_photo(chat_id=uid, photo=buf, caption="🏁 Результат баттла")
                    sent += 1
                except Exception:
                    failed += 1

        await message.reply_text(f"📨 Разослано. Доставлено: {sent}, ошибок: {failed}.")
        db.set_admin_state(admin_id, "")
        return True

    if state == "awaiting_set_required_channel":
        text = (message.text or "").strip()
        # принимаем и ссылку вида https://t.me/mychannel
        for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
            if text.lower().startswith(prefix):
                text = "@" + text[len(prefix):].strip("/")
        db.set_admin_state(admin_id, "")

        if text.lower() == "off":
            subscription.clear_required_channel()
            await message.reply_text("✅ Обязательная подписка отключена.")
            return True

        try:
            chat = await context.bot.get_chat(text)
        except Exception as e:
            await message.reply_text(
                f"⚠️ Не удалось получить этот канал/чат: {e}\n\n"
                "Проверь, что юзернейм/ID указан верно и что бот добавлен туда "
                "как администратор. Попробуй ещё раз через кнопку в меню."
            )
            return True

        # без прав администратора Telegram не даёт боту проверять подписчиков —
        # раньше канал всё равно сохранялся, и бот молча пускал всех
        problem = await subscription.check_bot_access(context, chat.id)
        if problem:
            await message.reply_text(
                f"⚠️ Подписка НЕ включена: {problem}.\n\n"
                f"Открой канал «{chat.title or text}» → Управление каналом → Администраторы → "
                f"Добавить администратора → найди этого бота и добавь (права можно оставить "
                f"по умолчанию). Потом снова нажми «📢 Обязательная подписка» в /admin."
            )
            return True

        link = ""
        if getattr(chat, "invite_link", None):
            link = chat.invite_link
        elif getattr(chat, "username", None):
            link = f"https://t.me/{chat.username}"

        # сохраняем числовой ID — он не меняется, даже если у канала сменят юзернейм
        subscription.set_required_channel(str(chat.id), title=chat.title or text, link=link)
        note = "" if link else "\n\n⚠️ Не нашёл публичную ссылку — кнопка «Перейти в канал» не покажется, но проверка подписки всё равно будет работать."
        await message.reply_text(f"✅ Обязательная подписка включена: {chat.title or text}{note}")
        return True

    return False
