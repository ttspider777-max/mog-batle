import asyncio
import html
import logging
import re
import time

from telegram import Update, InputMediaPhoto, InlineQueryResultCachedPhoto, InlineQueryResultsButton
from telegram.ext import ContextTypes

import db
import scoring
from images import render_challenge_card
from images_ny import render_challenge_card_ny
from images_result import render_detailed_result_card
from keyboards import challenge_keyboard, result_keyboard, rematch_keyboard, inline_challenge_keyboard
from handlers.common import ensure_registered, get_avatar_bytes, get_tg_stats, display_name
from subscription import require_subscription

logger = logging.getLogger(__name__)

# "мог", ".мог", "!мог", "/мог", "мог @ник" (регистр не важен)
MOG_RE = re.compile(r"^[.!/]?мог(?:\s+@([A-Za-z0-9_]{4,32}))?\s*$", re.IGNORECASE)
# "@ник" в inline-запросе (@mogggbattle_robot @ник)
USERNAME_RE = re.compile(r"^@([A-Za-z0-9_]{4,32})$")


# ---------- Карточка вызова ----------

async def _render_challenge(context, row: dict, seed=None, target_name=None):
    avatar = await get_avatar_bytes(context, row["user_id"])
    challenger = {
        "name": row["first_name"] or "Игрок",
        "username": row["username"] or "",
        "rating": row["rating"],
    }
    if (row.get("card_style") or "neon") != "classic":
        # «neon» — это теперь новогодний стиль; тема зависит от seed (ID баттла / игрока)
        return await asyncio.to_thread(
            render_challenge_card_ny, challenger, avatar,
            row["user_id"] if seed is None else seed, target_name)
    return await asyncio.to_thread(render_challenge_card, challenger, avatar)


async def _card_file_id(context, row: dict):
    """file_id карточки вызова игрока для inline-режима. Inline-ответ может содержать
    только уже загруженное в Telegram фото, поэтому карточка один раз загружается в личку
    игрока (и сразу удаляется оттуда), а file_id кэшируется, пока не поменяются рейтинг,
    ник или дизайн. Возвращает None, если человек ни разу не запускал бота."""
    key = f"ny2|{row.get('card_style') or 'neon'}|{row['rating']:.2f}|{row['username']}|{row['first_name']}"
    if row.get("card_file_id") and row.get("card_key") == key:
        return row["card_file_id"]
    try:
        buf = await _render_challenge(context, row)
        msg = await context.bot.send_photo(
            chat_id=row["user_id"], photo=buf, disable_notification=True
        )
        file_id = msg.photo[-1].file_id
        try:
            await msg.delete()
        except Exception:
            pass
    except Exception:
        logger.info("Не удалось загрузить карточку вызова для %s", row["user_id"])
        return None
    db.set_user_card(row["user_id"], file_id, key)
    return file_id


async def _post_challenge(update: Update, context, row: dict, target_row=None, target_username=None):
    """Публикует карточку вызова в текущий чат (личка с ботом или группа)."""
    battle_id = db.create_battle(
        row["user_id"],
        target_id=target_row["user_id"] if target_row else None,
        target_username=None if target_row else target_username,
    )
    private = update.effective_chat.type == "private"
    name = display_name(row)
    photo_buf = await _render_challenge(
        context, row, seed=battle_id,
        target_name=(display_name(target_row) if target_row else
                     (f"@{target_username}" if target_username else None)),
    )

    if target_row or target_username:
        target_name = display_name(target_row) if target_row else f"@{target_username}"
        caption = f"⚔️ {name} вызывает {target_name} на баттл!\nПринять вызов может только {target_name}."
    elif private:
        caption = (
            "⚔️ Вызов создан!\n"
            "Нажми «📤 Отправить в чат / другу» и выбери, куда отправить — так кнопка «Принять "
            "вызов» сохранится. Обычная пересылка (\"Переслать\") её стирает — это ограничение "
            "самого Telegram, а не бага бота."
        )
    else:
        caption = f"⚔️ {name} бросает вызов! Кто первый нажмёт «Принять вызов» — тот и соперник."
    caption += f"\n\nID вызова: {battle_id}"

    sent = await update.message.reply_photo(
        photo=photo_buf, caption=caption,
        reply_markup=challenge_keyboard(battle_id, with_share=private),
    )
    if sent.photo:
        db.set_battle_photo_file_id(battle_id, sent.photo[-1].file_id)


async def battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, banned = await ensure_registered(update, context)
    if banned:
        await update.message.reply_text("🚫 Вы забанены в этом боте.")
        return
    if not await require_subscription(update, context):
        return
    await _post_challenge(update, context, row)


# ---------- «мог» / /mog ----------

async def mog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mog, /mog @ник, /mog ответом на сообщение."""
    target = None
    if context.args:
        m = USERNAME_RE.match(context.args[0])
        target = m.group(1) if m else None
    await mog(update, context, target)


async def mog_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Вызывается из текстового роутера. True — сообщение было триггером «мог»."""
    text = (update.message.text or "").strip() if update.message else ""
    m = MOG_RE.match(text)
    if not m:
        return False
    await mog(update, context, m.group(1))
    return True


async def mog(update: Update, context: ContextTypes.DEFAULT_TYPE, target_username=None):
    row, banned = await ensure_registered(update, context)
    if banned:
        await update.message.reply_text("🚫 Вы забанены в этом боте.")
        return
    if not await require_subscription(update, context):
        return

    # ответом на сообщение — баттл сразу, без ожидания
    reply = update.message.reply_to_message
    if reply and reply.from_user and not reply.from_user.is_bot and not target_username:
        await _instant_battle(update, context, row, reply.from_user)
        return

    if target_username:
        if row["username"] and target_username.lower() == row["username"].lower():
            await update.message.reply_text("Нельзя вызвать самого себя 😅")
            return
        target_row = db.get_user_by_username(target_username)
        await _post_challenge(update, context, row, target_row=target_row, target_username=target_username)
        return

    await _post_challenge(update, context, row)


async def _instant_battle(update: Update, context, challenger_row: dict, opp_user):
    if opp_user.id == challenger_row["user_id"]:
        await update.message.reply_text("Нельзя сразиться с самим собой 😅")
        return
    opponent_row, _ = db.get_or_create_user(
        opp_user.id, opp_user.username, opp_user.first_name,
        is_premium=bool(getattr(opp_user, "is_premium", False)),
    )
    if opponent_row["banned"]:
        await update.message.reply_text("🚫 Этот игрок забанен в боте.")
        return

    battle_id = db.create_battle(challenger_row["user_id"], target_id=opponent_row["user_id"])
    db.claim_battle(battle_id, opponent_row["user_id"])

    caption, _winner_id, card_args = await resolve_battle(context, battle_id, challenger_row, opponent_row)
    msg = await update.message.reply_text(
        caption, parse_mode="HTML", reply_markup=result_keyboard(battle_id)
    )
    # картинку догружаем следом: если Telegram тормозит, результат уже виден текстом
    try:
        result_bytes = await asyncio.wait_for(_build_result_card(context, *card_args), CARD_TIMEOUT)
        await update.message.reply_photo(
            photo=result_bytes, caption=caption, parse_mode="HTML",
            reply_markup=result_keyboard(battle_id), write_timeout=60,
        )
        await msg.delete()
    except Exception:
        logger.exception("Карточка результата баттла %s не отправлена — остался текст", battle_id)


# ---------- Inline-режим: @mogggbattle_robot в любом чате ----------

async def battle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """@mogggbattle_robot — открытый вызов; @mogggbattle_robot @ник — вызов конкретному
    человеку; число — отправить уже созданный вызов с таким ID (кнопка «📤 Отправить»).
    Сообщение уходит ОТ ИМЕНИ БОТА, поэтому кнопка «Принять вызов» сохраняется."""
    inline_query = update.inline_query
    query_text = (inline_query.query or "").strip()
    user = inline_query.from_user

    if query_text.isdigit():
        battle = db.get_battle(int(query_text))
        if battle and battle.get("status") == "open" and battle.get("photo_file_id"):
            result = InlineQueryResultCachedPhoto(
                id=f"{battle['id']}-{int(time.time())}",
                photo_file_id=battle["photo_file_id"],
                caption=f"⚔️ Открытый вызов! ID вызова: {battle['id']}",
                reply_markup=challenge_keyboard(battle["id"], with_share=False),
            )
            await inline_query.answer([result], cache_time=1, is_personal=True)
            return

    row = db.get_user(user.id)
    if row:  # обновим ник/имя, чтобы карточка была актуальной
        row, _ = db.get_or_create_user(user.id, user.username, user.first_name,
                                       is_premium=bool(getattr(user, "is_premium", False)))
    file_id = None
    if row and not row["banned"]:
        if row.get("card_file_id"):
            # Отвечаем СРАЗУ уже загруженной карточкой (пусть даже с чуть устаревшим
            # рейтингом), а свежую рисуем в фоне — иначе Telegram не дождётся ответа
            # и у человека будет бесконечная загрузка в поле ввода.
            file_id = row["card_file_id"]
            context.application.create_task(_card_file_id(context, row))
        else:
            try:
                file_id = await asyncio.wait_for(_card_file_id(context, row), 7)
            except Exception:
                logger.warning("Карточка вызова для %s не успела загрузиться", user.id)
                context.application.create_task(_card_file_id(context, row))
    if not file_id and row and not row["banned"]:
        await inline_query.answer(
            [], cache_time=1, is_personal=True,
            button=InlineQueryResultsButton(
                text="⏳ Готовлю карточку — попробуй ещё раз через пару секунд",
                start_parameter="inline",
            ),
        )
        return
    if not file_id:
        await inline_query.answer(
            [], cache_time=1, is_personal=True,
            button=InlineQueryResultsButton(
                text="Сначала запусти бота, чтобы бросать вызовы ⚔️", start_parameter="inline"
            ),
        )
        return

    m = USERNAME_RE.match(query_text)
    target = m.group(1) if m else ""
    if target and user.username and target.lower() == user.username.lower():
        target = ""
    name = display_name(row)
    if target:
        title = f"⚔️ Вызвать @{target} на баттл"
        caption = f"⚔️ {name} вызывает @{target} на баттл!\nПринять вызов может только @{target}."
    else:
        title = "⚔️ Бросить вызов"
        caption = f"⚔️ {name} бросает вызов! Кто первый нажмёт «Принять вызов» — тот и соперник."

    result = InlineQueryResultCachedPhoto(
        id=f"iv-{user.id}-{int(time.time())}",
        photo_file_id=file_id,
        title=title,
        description="Сравнить профили Telegram — победитель получит рейтинг",
        caption=caption,
        reply_markup=inline_challenge_keyboard(user.id, target),
    )
    await inline_query.answer([result], cache_time=1, is_personal=True)


async def inline_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Нажатие «Принять вызов» под вызовом, брошенным через @бот. Баттл создаётся прямо
    сейчас; уникальность по inline_message_id гарантирует, что его примет только один."""
    query = update.callback_query
    tg_user = update.effective_user
    _, challenger_id, target = query.data.split(":", 2)
    challenger_id = int(challenger_id)

    if tg_user.id == challenger_id:
        await query.answer("Нельзя принять собственный вызов 😅", show_alert=True)
        return
    if target and (tg_user.username or "").lower() != target:
        await query.answer("Этот вызов адресован другому игроку 🙅", show_alert=True)
        return
    # проверки ДО создания баттла — иначе вызов "застрянет" за тем, кто не может его принять
    _, banned = await ensure_registered(update, context)
    if banned:
        await query.answer("🚫 Вы забанены в этом боте.", show_alert=True)
        return
    if not await require_subscription(update, context):
        return
    if not db.get_user(challenger_id):
        await query.answer("Автор вызова не найден.", show_alert=True)
        return

    battle_id = db.create_battle(
        challenger_id, target_username=target or None,
        inline_message_id=query.inline_message_id,
    )
    if battle_id is None:
        await query.answer("Кто-то уже принял этот вызов чуть раньше ⏱", show_alert=True)
        return
    await _accept(update, context, db.get_battle(battle_id))


# ---------- Принятие вызова ----------

async def _send_private_photo(context, chat_id: int, photo: bytes, caption: str):
    """Отправляет фото в личку игроку и возвращает file_id (или None, если нельзя —
    например, человек ни разу не запускал бота или заблокировал его)."""
    try:
        msg = await context.bot.send_photo(
            chat_id=chat_id, photo=photo, caption=caption, parse_mode="HTML", write_timeout=60,
        )
        return msg.photo[-1].file_id if msg.photo else None
    except Exception:
        return None


async def battle_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    battle_id = int(query.data.split(":")[2])
    battle = db.get_battle(battle_id)
    if not battle or battle["status"] != "open":
        await query.answer("Этот вызов уже недействителен ⛔️", show_alert=True)
        return
    await _accept(update, context, battle)


async def _accept(update: Update, context: ContextTypes.DEFAULT_TYPE, battle: dict):
    query = update.callback_query
    tg_user = update.effective_user
    battle_id = battle["id"]

    opponent_row, banned = await ensure_registered(update, context)
    if banned:
        await query.answer("🚫 Вы забанены в этом боте.", show_alert=True)
        return
    if not await require_subscription(update, context):
        return

    if battle["challenger_id"] == tg_user.id:
        await query.answer("Нельзя принять собственный вызов 😅", show_alert=True)
        return

    # вызов адресован конкретному игроку (реванш / мог @ник) — остальным принять его нельзя
    if (battle.get("target_id") and battle["target_id"] != tg_user.id) or \
            (battle.get("target_username") and (tg_user.username or "").lower() != battle["target_username"]):
        await query.answer("Этот вызов адресован другому игроку 🙅", show_alert=True)
        return

    challenger_row = db.get_user(battle["challenger_id"])
    if not challenger_row:
        await query.answer("Автор вызова не найден.", show_alert=True)
        return

    # атомарно "забираем" вызов — если кто-то другой уже успел принять его секундой
    # раньше, claim_battle вернёт False, и мы это честно покажем, а не молча перезапишем.
    if not db.claim_battle(battle_id, opponent_row["user_id"]):
        await query.answer("Кто-то уже принял этот вызов чуть раньше ⏱", show_alert=True)
        return

    # сразу отвечаем на нажатие (убирает "часики" на кнопке у пользователя) —
    # дальше можно спокойно тратить время на подсчёт и отрисовку картинки.
    await query.answer("⚔️ Вызов принят! Считаю результат…")

    try:
        caption, winner_id, card_args = await resolve_battle(context, battle_id, challenger_row, opponent_row)
    except Exception:
        # не оставляем людей с вечным "считаю результат" — пишем прямо в карточке
        try:
            await query.edit_message_caption(
                caption=f"⚠️ Не удалось подсчитать результат баттла {battle_id}. "
                        f"Ошибка уже отправлена админу — попробуйте бросить вызов ещё раз."
            )
        except Exception:
            pass
        raise

    # 1) Результат ТЕКСТОМ — сразу, без ожидания картинки. Даже если Telegram тормозит
    #    с загрузкой фото, люди моментально видят, кто победил.
    try:
        await query.edit_message_caption(
            caption=caption, parse_mode="HTML", reply_markup=result_keyboard(battle_id)
        )
    except Exception:
        logger.exception("Не удалось показать результат баттла %s текстом", battle_id)

    # 2) Картинку догружаем следом, с ограничением по времени.
    opponent_notified = False
    chat_id = query.message.chat.id if query.message else None
    try:
        opponent_notified = await asyncio.wait_for(
            _attach_result_card(context, query, battle_id, caption, challenger_row,
                                opponent_row, card_args),
            CARD_TIMEOUT,
        )
    except Exception:
        logger.exception("Карточка результата баттла %s не загрузилась — остался текст", battle_id)

    # уведомим принявшего вызов лично, если баттл был не в его личке с ботом
    if not opponent_notified and chat_id != tg_user.id:
        try:
            you_won = (winner_id == tg_user.id)
            note = "🎉 Ты выиграл этот баттл!" if you_won else "😢 Ты проиграл этот баттл. Жми «🔁 Реванш»!"
            await context.bot.send_message(chat_id=tg_user.id, text=note)
        except Exception:
            pass


# сколько максимум ждём отрисовку и загрузку картинки результата (сек)
CARD_TIMEOUT = 45


async def _attach_result_card(context, query, battle_id, caption, challenger_row,
                              opponent_row, card_args) -> bool:
    """Рисует карточку результата и ставит её в сообщение баттла.
    Возвращает True, если принявшему вызов уже отправили результат в личку."""
    result_bytes = await _build_result_card(context, *card_args)

    # Сообщение, отправленное через inline-режим, — это inline-сообщение. В него Telegram
    # НЕ даёт загрузить новую картинку напрямую (только по file_id уже загруженного фото).
    is_inline = query.inline_message_id is not None
    chat_id = query.message.chat.id if query.message else None
    opponent_notified = False

    media = None
    # Шлём результат автору вызова в личку: это и уведомление для него, и способ
    # получить file_id картинки для inline-сообщения.
    if chat_id != challenger_row["user_id"]:
        media = await _send_private_photo(
            context, challenger_row["user_id"], result_bytes,
            f"🔔 Твой вызов принял {html.escape(display_name(opponent_row))}!\n\n{caption}",
        )
    if media is None and is_inline:
        media = await _send_private_photo(context, opponent_row["user_id"], result_bytes, caption)
        opponent_notified = media is not None
    if media is None and not is_inline:
        media = result_bytes  # обычное сообщение — можно загрузить картинку напрямую

    if media is not None:
        await query.edit_message_media(
            media=InputMediaPhoto(media=media, caption=caption, parse_mode="HTML"),
            reply_markup=result_keyboard(battle_id),
            write_timeout=60,
        )
    return opponent_notified


def _result_caption(winner_row, loser_row, w_old, w_new, l_old, l_new, w_streak, l_lost_streak,
                    w_score=None, l_score=None):
    w_name = html.escape(display_name(winner_row))
    l_name = html.escape(display_name(loser_row))
    w_tier, l_tier = scoring.tier_label(w_new), scoring.tier_label(l_new)
    w_emoji, l_emoji = scoring.tier_emoji(w_new), scoring.tier_emoji(l_new)

    fire = "🔥" * min(w_streak, 5)
    streak_line = f"🔥 Винстрик: <b>{w_streak}</b> {fire}"
    if l_lost_streak >= 2:
        l_streak_line = f"💔 Винстрик прерван: <s>{l_lost_streak}</s> → 0"
    else:
        l_streak_line = "💔 Винстрик: 0"

    return (
        "🏁 <b>MOG BATTLE — РЕЗУЛЬТАТ</b>\n\n"
        f"👑 <b>ПОБЕДИТЕЛЬ:</b> {w_name}\n"
        f"├ Статус: {w_emoji} <b>{w_tier}</b>\n"
        f"├ Рейтинг: {w_old:.2f} → <b>{w_new:.2f}</b> (+{w_new - w_old:.2f})\n"
        f"└ {streak_line}\n\n"
        f"💀 <b>ПРОИГРАВШИЙ:</b> {l_name}\n"
        f"├ Статус: {l_emoji} <b>{l_tier}</b>\n"
        f"├ Рейтинг: {l_old:.2f} → <b>{l_new:.2f}</b> ({l_new - l_old:+.2f})\n"
        f"└ {l_streak_line}\n\n"
        f"⚔️ <b>{w_name}</b> могнул <b>{l_name}</b>"
        + (f"\n📊 Счёт по профилям: <b>{w_score:.2f}</b> : {l_score:.2f}" if w_score is not None else "")
    )


async def _profile_dict(context, row: dict, rating_for_tag=None) -> dict:
    """Настоящая статистика профиля Telegram → категории и итоговый балл."""
    stats = await get_tg_stats(context, row["user_id"])
    categories = scoring.compute_categories(
        row["user_id"], row["username"], stats, bool(row.get("is_premium")),
        custom_status=row.get("custom_status"),
    )
    total = scoring.total_score(categories)
    return {
        "user_id": row["user_id"],
        "display_name": display_name(row),
        "username": row["username"] or "",
        "avatar": stats["avatar"],
        "categories": categories,
        "total": total,
        "tag": scoring.tier_label(total),
        "streak": 0,
    }


async def resolve_battle(context, battle_id: int, challenger_row: dict, opponent_row: dict):
    """Считает баллы обоих профилей по настоящим данным Telegram, определяет победителя
    (у кого итоговый балл выше; при равенстве — у кого выше рейтинг), обновляет рейтинг и
    готовит текст результата. Возвращает (подпись HTML, id победителя, card_args)."""
    ch, op = await asyncio.gather(
        _profile_dict(context, challenger_row), _profile_dict(context, opponent_row)
    )
    if ch["total"] != op["total"]:
        winner_is_challenger = ch["total"] > op["total"]
    elif challenger_row["rating"] != opponent_row["rating"]:
        winner_is_challenger = challenger_row["rating"] > opponent_row["rating"]
    else:
        winner_is_challenger = challenger_row["user_id"] < opponent_row["user_id"]

    winner_row = challenger_row if winner_is_challenger else opponent_row
    loser_row = opponent_row if winner_is_challenger else challenger_row
    winner_id, loser_id = winner_row["user_id"], loser_row["user_id"]

    loser_lost_streak = db.win_streak(loser_id)  # винстрик, который сейчас прервётся
    new_winner_rating, new_loser_rating = db.apply_battle_result(winner_id, loser_id)
    db.finish_battle(battle_id, opponent_row["user_id"], winner_id)
    winner_streak = db.win_streak(winner_id)

    w_p, l_p = (ch, op) if winner_is_challenger else (op, ch)
    caption = _result_caption(
        winner_row, loser_row, winner_row["rating"], new_winner_rating,
        loser_row["rating"], new_loser_rating, winner_streak, loser_lost_streak,
        w_p["total"], l_p["total"],
    )
    ch["streak"] = winner_streak if winner_is_challenger else 0
    op["streak"] = 0 if winner_is_challenger else winner_streak
    payload = {
        "battle_id": battle_id,
        "left": ch, "right": op,
        "winner_side": "left" if winner_is_challenger else "right",
    }
    return caption, winner_id, (payload,)


async def _build_result_card(context, payload) -> bytes:
    # рисование картинки — тяжёлая CPU-операция; уносим её в отдельный поток,
    # чтобы она не блокировала обработку остальных сообщений бота.
    result_buf = await asyncio.to_thread(
        render_detailed_result_card, payload["left"], payload["right"],
        payload["winner_side"], payload["battle_id"],
    )
    return result_buf.getvalue()


# ---------- Реванш ----------

async def battle_rematch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка «🔁 Реванш» под карточкой результата. Создаёт новый вызов, который может
    принять только соперник из прошлого баттла, и превращает карточку в запрос реванша."""
    query = update.callback_query
    tg_user = update.effective_user
    battle_id = int(query.data.split(":")[2])

    old = db.get_battle(battle_id)
    if not old or old["status"] != "done":
        await query.answer("Этот баттл недоступен для реванша ⛔️", show_alert=True)
        return

    if tg_user.id not in (old["challenger_id"], old["opponent_id"]):
        await query.answer("Реванш могут запросить только участники баттла 🙅", show_alert=True)
        return

    me_row, banned = await ensure_registered(update, context)
    if banned:
        await query.answer("🚫 Вы забанены в этом боте.", show_alert=True)
        return
    if not await require_subscription(update, context):
        return

    target_id = old["opponent_id"] if tg_user.id == old["challenger_id"] else old["challenger_id"]
    target_row = db.get_user(target_id)
    if not target_row:
        await query.answer("Соперник не найден.", show_alert=True)
        return

    new_id = db.create_battle(tg_user.id, target_id=target_id, rematch_of=battle_id)
    if new_id is None:
        await query.answer("Реванш уже запрошен ⏱", show_alert=True)
        return

    await query.answer("🔁 Реванш запрошен!")

    me_name = display_name(me_row)
    target_name = display_name(target_row)
    caption = (
        f"🔁 {me_name} требует реванш у {target_name}!\n\n"
        f"Принять вызов может только {target_name}.\n"
        f"ID вызова: {new_id}"
    )
    # картинку оставляем прежней (результат прошлого баттла), меняем подпись и кнопку
    await query.edit_message_caption(caption=caption, reply_markup=rematch_keyboard(new_id))

    # напомним сопернику в личку (если карточка не у него в личке и он запускал бота)
    chat_id = query.message.chat.id if query.message else None
    if chat_id != target_id:
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🔁 {me_name} вызывает тебя на реванш! Нажми «⚔️ Принять реванш» под карточкой баттла.",
            )
        except Exception:
            pass
