import logging
import traceback

from telegram import Update
from telegram.error import Conflict
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, InlineQueryHandler, ContextTypes, filters
)

import db
from config import BOT_TOKEN, ADMIN_IDS
from handlers.start import start_command
from handlers.profile import profile_command, leaderboard_command
from handlers.battle import (
    battle_command, battle_accept_callback, battle_inline_query, battle_rematch_callback,
    inline_accept_callback, mog_command, mog_text,
)
from handlers.admin import admin_command, admin_callback, admin_text_router, is_admin, clear_photo_command
from handlers.me import me_command, me_callback, me_status_text_router
from handlers.privacy import privacy_command
from handlers.season import season_command
from subscription import is_subscribed
from keyboards import MAIN_MENU

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
# httpx пишет в лог каждый запрос вместе с токеном бота — оставляем только проблемы
logging.getLogger("httpx").setLevel(logging.WARNING)

# меняется при каждом обновлении — по логу/сообщениям видно, что на хостинге новая версия
BOT_VERSION = "2026-11-11 v3 seasons"


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Единый обработчик обычного текста/фото вне команд. Порядок важен:
    1) если человек сейчас вводит новый статус профиля (/me) — ловим это первым;
    2) если это админ и он сейчас в одном из режимов админ-панели — обрабатываем это;
    3) иначе — обычные кнопки главного меню.
    Слово «мог» (.мог, !мог, мог @ник) работает везде — и в личке, и в группах."""
    if await mog_text(update, context):
        return

    private = update.effective_chat and update.effective_chat.type == "private"
    if private:
        handled = await me_status_text_router(update, context)
        if handled:
            return

    if private and update.effective_user and is_admin(update.effective_user.id):
        handled = await admin_text_router(update, context)
        if handled:
            return

    text = (update.message.text or "").strip() if update.message and update.message.text else ""

    if text == "⚔️ Бросить вызов":
        await battle_command(update, context)
    elif text == "👤 Мой профиль":
        await me_command(update, context)
    elif text == "🏆 Рейтинг":
        await leaderboard_command(update, context)
    elif text == "🏅 Сезон":
        await season_command(update, context)
    elif text == "🔒 Приватность":
        await privacy_command(update, context)
    elif update.effective_user and is_admin(update.effective_user.id) \
            and update.effective_chat and update.effective_chat.type == "private":
        # админ что-то прислал, но бот ничего от него не ждёт — не молчим, а подсказываем
        await update.message.reply_text(
            "🤔 Сейчас я не жду от тебя текста. Если хотел изменить приветствие, сделать "
            "рассылку и т.п. — открой /admin и нажми нужную кнопку ещё раз, потом пришли текст."
        )
    # иначе просто игнорируем произвольный текст


async def subscription_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка «✅ Я подписался» под сообщением с просьбой подписаться на канал."""
    query = update.callback_query
    if await is_subscribed(context, query.from_user.id):
        await query.edit_message_text("✅ Подписка подтверждена, спасибо!")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Теперь можешь пользоваться ботом — выбери действие в меню:",
            reply_markup=MAIN_MENU,
        )
        await query.answer("Спасибо за подписку!")
    else:
        await query.answer("Похоже, ты ещё не подписался 🙁", show_alert=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Ловит все необработанные ошибки: печатает полный traceback в терминал
    и (если возможно) сообщает пользователю, что что-то пошло не так, вместо
    того чтобы бот молча "не отвечал"."""
    if isinstance(context.error, Conflict):
        # Этот же токен сейчас использует ДРУГАЯ запущенная копия бота (например, на ПК
        # и на Amvera одновременно). Тогда сообщения делятся между копиями случайно:
        # кнопку ловит одна, текст — другая, у них разные базы, и бот "не реагирует".
        logger.error(
            "!!! КОНФЛИКТ: бот с этим токеном запущен где-то ещё (ПК / Amvera). "
            "Останови лишнюю копию, иначе бот будет вести себя непредсказуемо."
        )
        if not context.bot_data.get("conflict_warned"):
            context.bot_data["conflict_warned"] = True
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text="⚠️ Бот запущен в двух местах одновременно (например, на ПК и на "
                             "Amvera). Из-за этого он может не реагировать и терять настройки. "
                             "Останови лишнюю копию — оставь только Amvera.",
                    )
                except Exception:
                    pass
        return

    logger.error("Exception while handling an update:", exc_info=context.error)
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)

    # присылаем текст ошибки админам в личку — чтобы не искать его в логах хостинга
    tb = "".join(traceback.format_exception(
        type(context.error), context.error, context.error.__traceback__
    ))
    report = f"⚠️ Ошибка в боте (версия {BOT_VERSION}):\n\n{tb[-3500:]}"
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=report)
        except Exception:
            pass

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Произошла ошибка при обработке запроса. Попробуй ещё раз."
            )
        except Exception:
            pass


def main():
    db.init_db()

    # concurrent_updates=True: несколько сообщений/нажатий кнопок от разных людей
    # обрабатываются параллельно, а не строго по очереди — иначе, пока бот рисует
    # одну картинку, все остальные пользователи "зависают" в ожидании.
    # таймауты побольше стандартных: с хостинга загрузка фото в Telegram бывает медленной
    app: Application = (
        ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True)
        .connect_timeout(10).read_timeout(20).write_timeout(30).pool_timeout(10)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("battle", battle_command))
    app.add_handler(CommandHandler("mog", mog_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("top", leaderboard_command))
    app.add_handler(CommandHandler("season", season_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("clear_photo", clear_photo_command))

    app.add_handler(CallbackQueryHandler(battle_accept_callback, pattern=r"^battle:accept:\d+$"))
    app.add_handler(CallbackQueryHandler(battle_rematch_callback, pattern=r"^battle:rematch:\d+$"))
    app.add_handler(CallbackQueryHandler(inline_accept_callback, pattern=r"^iv:\d+:\w*$"))
    app.add_handler(CallbackQueryHandler(me_callback, pattern=r"^me:"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(subscription_check_callback, pattern=r"^sub:check$"))
    app.add_handler(InlineQueryHandler(battle_inline_query))

    # ловим и текст, и фото (для рассылок/приветствия с картинкой), кроме команд
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, text_router))

    app.add_error_handler(error_handler)

    logger.info("MOG BATTLE bot started, version %s", BOT_VERSION)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
