"""
Слой работы с базой данных SQLite.

Таблицы:
  users     — игроки бота
  battles   — созданные баттлы (вызовы)
  settings  — произвольные настройки (приветствие и т.п.), key/value
"""

import sqlite3
import random
import time
import os
from contextlib import contextmanager

from config import DB_PATH, RATING_MIN, RATING_MAX, RATING_K

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                rating      REAL DEFAULT 5.00,
                wins        INTEGER DEFAULT 0,
                losses      INTEGER DEFAULT 0,
                banned      INTEGER DEFAULT 0,
                is_premium  INTEGER DEFAULT 0,
                custom_status TEXT,
                card_style  TEXT DEFAULT 'neon',
                joined_at   INTEGER
            )
        """)
        # на случай апгрейда базы, созданной до появления этих колонок
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "is_premium" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0")
        if "custom_status" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN custom_status TEXT")
        if "card_style" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN card_style TEXT DEFAULT 'neon'")
        # кэш карточки вызова для inline-режима (file_id + "отпечаток" данных на карточке)
        if "card_file_id" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN card_file_id TEXT")
        if "card_key" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN card_key TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS battles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                challenger_id   INTEGER,
                opponent_id     INTEGER,
                winner_id       INTEGER,
                status          TEXT DEFAULT 'open',   -- open | done | cancelled
                photo_file_id   TEXT,
                created_at      INTEGER
            )
        """)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(battles)").fetchall()]
        if "photo_file_id" not in cols:
            conn.execute("ALTER TABLE battles ADD COLUMN photo_file_id TEXT")
        # target_id — если задан, принять вызов может только этот игрок (реванш)
        if "target_id" not in cols:
            conn.execute("ALTER TABLE battles ADD COLUMN target_id INTEGER")
        # rematch_of — ID баттла, реваншем которого является этот вызов
        if "rematch_of" not in cols:
            conn.execute("ALTER TABLE battles ADD COLUMN rematch_of INTEGER")
        # target_username — вызов по @нику человеку, который ещё не запускал бота
        if "target_username" not in cols:
            conn.execute("ALTER TABLE battles ADD COLUMN target_username TEXT")
        # inline_message_id — вызов, брошенный через @бот в чужом чате (одно сообщение = один баттл)
        if "inline_message_id" not in cols:
            conn.execute("ALTER TABLE battles ADD COLUMN inline_message_id TEXT")
        if "finished_at" not in cols:
            conn.execute("ALTER TABLE battles ADD COLUMN finished_at INTEGER")
        # уникальный индекс: на один баттл — максимум один реванш (защита от двойного нажатия)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_battles_rematch_of ON battles(rematch_of)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_battles_inline ON battles(inline_message_id)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # значения приветствия по умолчанию
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', ?)",
            ("Добро пожаловать в MOG BATTLE! ⚔️\n\nНажми «Бросить вызов», чтобы создать баттл "
             "и разошли его в чаты — первый, кто примет вызов, сразится с тобой.",)
        )
        # приветствие из welcome.py — записывается один раз на каждую новую ревизию
        from welcome import WELCOME_REVISION, WELCOME_TEXT, WELCOME_HTML
        row = conn.execute("SELECT value FROM settings WHERE key='welcome_revision'").fetchone()
        if not row or row["value"] != WELCOME_REVISION:
            for key, value in (("welcome_text", WELCOME_TEXT), ("welcome_html", WELCOME_HTML),
                               ("welcome_revision", WELCOME_REVISION)):
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value)
                )


# ---------- Пользователи ----------

def get_or_create_user(user_id: int, username: str, first_name: str, is_premium: bool = False):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            # обновим ник/имя/премиум-статус на случай изменений
            conn.execute(
                "UPDATE users SET username=?, first_name=?, is_premium=? WHERE user_id=?",
                (username, first_name, 1 if is_premium else 0, user_id)
            )
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            return dict(row), False
        rating = round(random.uniform(RATING_MIN, RATING_MAX), 2)
        conn.execute(
            "INSERT INTO users (user_id, username, first_name, rating, is_premium, joined_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, first_name, rating, 1 if is_premium else 0, int(time.time()))
        )
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row), True


def get_user(user_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        return dict(row) if row else None


def is_banned(user_id: int) -> bool:
    u = get_user(user_id)
    return bool(u and u["banned"])


def set_banned(user_id: int, banned: bool):
    with get_conn() as conn:
        conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id))


def set_custom_status(user_id: int, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET custom_status=? WHERE user_id=?", (status, user_id))


def set_card_style(user_id: int, style: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET card_style=? WHERE user_id=?", (style, user_id))


def all_users_full(limit: int = 50):
    """Полный список пользователей (включая забаненных) для админ-панели,
    новые сверху — в отличие от leaderboard() (тот сортирует по рейтингу)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY joined_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def total_users() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def leaderboard(limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE banned=0 ORDER BY rating DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def user_rank(user_id: int):
    """Место игрока в общем рейтинге (1 = первый)."""
    with get_conn() as conn:
        me = conn.execute("SELECT rating FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not me:
            return None
        higher = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE rating > ? AND banned=0", (me["rating"],)
        ).fetchone()["c"]
        return higher + 1


# ---------- Баттлы ----------

def create_battle(challenger_id: int, target_id: int = None, rematch_of: int = None,
                  target_username: str = None, inline_message_id: str = None):
    """Создаёт открытый вызов. Возвращает None, если такой баттл уже был создан раньше
    (реванш на этот баттл уже запрошен / это inline-сообщение уже кто-то принял)."""
    try:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO battles (challenger_id, target_id, rematch_of, target_username, "
                "inline_message_id, status, created_at) VALUES (?, ?, ?, ?, ?, 'open', ?)",
                (challenger_id, target_id, rematch_of,
                 target_username.lower() if target_username else None,
                 inline_message_id, int(time.time()))
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def set_battle_photo_file_id(battle_id: int, file_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE battles SET photo_file_id=? WHERE id=?", (file_id, battle_id))


def get_battle(battle_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM battles WHERE id=?", (battle_id,)).fetchone()
        return dict(row) if row else None


def claim_battle(battle_id: int, opponent_id: int) -> bool:
    """Атомарно 'забирает' открытый вызов под конкретного оппонента.
    Возвращает True, только если вызов ДЕЙСТВИТЕЛЬНО был открыт (status='open')
    и именно этот запрос успел его забрать первым — защищает от ситуации, когда
    два человека жмут «Принять вызов» почти одновременно."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE battles SET status='claimed', opponent_id=? WHERE id=? AND status='open'",
            (opponent_id, battle_id)
        )
        return cur.rowcount > 0


def finish_battle(battle_id: int, opponent_id: int, winner_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE battles SET opponent_id=?, winner_id=?, status='done', finished_at=? WHERE id=?",
            (opponent_id, winner_id, int(time.time()), battle_id)
        )


def top_wins_since(since_ts: int, limit: int = 10):
    """Топ игроков по числу побед в баттлах, завершённых после since_ts."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT u.*, COUNT(*) AS period_wins FROM battles b "
            "JOIN users u ON u.user_id = b.winner_id "
            "WHERE b.status='done' AND COALESCE(b.finished_at, b.created_at) >= ? AND u.banned=0 "
            "GROUP BY b.winner_id ORDER BY period_wins DESC, u.rating DESC LIMIT ?",
            (since_ts, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def win_streak(user_id: int) -> int:
    """Текущий винстрик: сколько последних завершённых баттлов игрок выиграл подряд.
    Считается по истории баттлов, поэтому верен и для старых игроков."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT winner_id FROM battles WHERE status='done' "
            "AND (challenger_id=? OR opponent_id=?) "
            "ORDER BY COALESCE(finished_at, created_at) DESC, id DESC LIMIT 500",
            (user_id, user_id)
        ).fetchall()
    streak = 0
    for r in rows:
        if r["winner_id"] != user_id:
            break
        streak += 1
    return streak


def set_user_card(user_id: int, file_id: str, key: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET card_file_id=?, card_key=? WHERE user_id=?", (file_id, key, user_id)
        )


def last_battle_of(user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM battles WHERE challenger_id=? AND rematch_of IS NULL "
            "ORDER BY id DESC LIMIT 1", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def apply_battle_result(winner_id: int, loser_id: int):
    """Простое Elo-подобное обновление рейтинга по шкале 0-10."""
    with get_conn() as conn:
        w = conn.execute("SELECT rating FROM users WHERE user_id=?", (winner_id,)).fetchone()
        l = conn.execute("SELECT rating FROM users WHERE user_id=?", (loser_id,)).fetchone()
        rw, rl = w["rating"], l["rating"]

        expected_w = 1 / (1 + 10 ** ((rl - rw) / 4))
        expected_l = 1 - expected_w

        new_rw = rw + RATING_K * (1 - expected_w) * 2
        new_rl = rl - RATING_K * (1 - expected_l) * 2

        new_rw = max(0.01, min(9.99, round(new_rw, 2)))
        new_rl = max(0.01, min(9.99, round(new_rl, 2)))

        conn.execute(
            "UPDATE users SET rating=?, wins=wins+1 WHERE user_id=?", (new_rw, winner_id)
        )
        conn.execute(
            "UPDATE users SET rating=?, losses=losses+1 WHERE user_id=?", (new_rl, loser_id)
        )
        return new_rw, new_rl


def win_probability(rating_a: float, rating_b: float) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 4))


# ---------- Настройки ----------

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )


def get_admin_state(user_id: int) -> str:
    """Режим админ-панели ("жду текст приветствия" и т.п.). Хранится в базе, а не в
    памяти — чтобы не терялся при перезапуске бота (например, после сборки на Amvera)."""
    return get_setting(f"admin_state:{user_id}", "")


def set_admin_state(user_id: int, state: str = ""):
    set_setting(f"admin_state:{user_id}", state or "")


def all_user_ids():
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users WHERE banned=0").fetchall()
        return [r["user_id"] for r in rows]
