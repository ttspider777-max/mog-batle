from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["⚔️ Бросить вызов"],
        ["👤 Мой профиль", "🏆 Рейтинг"],
        ["🔒 Приватность"],
    ],
    resize_keyboard=True
)


def challenge_keyboard(battle_id: int, with_share: bool = True):
    rows = [[InlineKeyboardButton("⚔️ Принять вызов", callback_data=f"battle:accept:{battle_id}")]]
    if with_share:
        # switch_inline_query открывает выбор чата и отправляет сообщение ОТ ИМЕНИ БОТА
        # (не форвард) — поэтому кнопка "Принять вызов" не пропадает, в отличие от
        # обычного пересылания сообщений в Telegram.
        rows.append([
            InlineKeyboardButton("📤 Отправить в чат / другу", switch_inline_query=str(battle_id))
        ])
    return InlineKeyboardMarkup(rows)


def inline_challenge_keyboard(challenger_id: int, target_username: str = ""):
    """Кнопка под вызовом, брошенным через @бот в любом чате. Баттл создаётся в момент
    нажатия (одно inline-сообщение = один баттл), поэтому в callback — ID автора и цель."""
    label = "⚔️ Принять вызов"
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        label, callback_data=f"iv:{challenger_id}:{(target_username or '').lower()}"
    )]])


def result_keyboard(battle_id: int):
    """Кнопка под карточкой результата баттла."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Реванш", callback_data=f"battle:rematch:{battle_id}")]
    ])


def rematch_keyboard(battle_id: int):
    """Кнопка под запросом реванша — принять его может только соперник."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Принять реванш", callback_data=f"battle:accept:{battle_id}")]
    ])


def admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Изменить приветствие", callback_data="admin:set_welcome")],
        [InlineKeyboardButton("📢 Написать от имени бота", callback_data="admin:broadcast")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin:users")],
        [InlineKeyboardButton("🚫 Забанить по ID", callback_data="admin:ban")],
        [InlineKeyboardButton("✅ Разбанить по ID", callback_data="admin:unban")],
        [InlineKeyboardButton("📨 Разослать баттл в чат", callback_data="admin:send_battle")],
        [InlineKeyboardButton("🏆 Рейтинг игроков", callback_data="admin:leaderboard")],
        [InlineKeyboardButton("📢 Обязательная подписка", callback_data="admin:set_required_channel")],
    ])


def admin_cancel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data="admin:cancel")]
    ])
