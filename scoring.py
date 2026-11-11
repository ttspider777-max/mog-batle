"""
Подсчёт "категорий" для детальной карточки результата (аватар, юзернейм,
о себе, подарки, стоимость, регистрация, уровень TG).

Всё считается по НАСТОЯЩИМ данным из Telegram (см. handlers/common.get_tg_stats),
никаких случайных чисел — у одного и того же профиля всегда одинаковый результат,
пока человек сам что-то не поменяет (фото, ник, био, подарки).

Единственное приближение — дата регистрации: Telegram её вообще никому не отдаёт,
поэтому она оценивается по ID аккаунта ("чем больше ID — тем позже создан
аккаунт"), точность — плюс-минус несколько месяцев. На карточке помечена знаком ≈.
"""

import math
from datetime import datetime, timedelta

RU_MONTHS = [
    "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]

# Опорные точки "user_id -> примерная дата создания аккаунта".
_ANCHORS = [
    (1_000_000, datetime(2013, 8, 1)),
    (100_000_000, datetime(2015, 12, 1)),
    (250_000_000, datetime(2017, 3, 1)),
    (450_000_000, datetime(2018, 9, 1)),
    (700_000_000, datetime(2019, 3, 1)),
    (1_000_000_000, datetime(2019, 12, 1)),
    (1_300_000_000, datetime(2020, 7, 1)),
    (1_600_000_000, datetime(2021, 4, 1)),
    (2_000_000_000, datetime(2022, 2, 1)),
    (3_000_000_000, datetime(2022, 10, 1)),
    (5_000_000_000, datetime(2023, 8, 1)),
    (6_500_000_000, datetime(2024, 8, 1)),
    (7_500_000_000, datetime(2025, 6, 1)),
    (8_800_000_000, datetime(2026, 6, 1)),
]


def _clamp(x: float) -> float:
    return round(max(0.0, min(9.9, x)), 2)


def _interp_date(user_id: int) -> datetime:
    if user_id <= _ANCHORS[0][0]:
        return _ANCHORS[0][1]
    if user_id >= _ANCHORS[-1][0]:
        return _ANCHORS[-1][1]
    for (x0, d0), (x1, d1) in zip(_ANCHORS, _ANCHORS[1:]):
        if x0 <= user_id <= x1:
            t = (user_id - x0) / (x1 - x0)
            return d0 + timedelta(days=int((d1 - d0).days * t))
    return _ANCHORS[-1][1]


def estimate_registration(user_id: int):
    """Возвращает (текст '≈ мес год', балл 0-10: чем старше аккаунт — тем выше)."""
    d = _interp_date(user_id)
    text = f"≈ {RU_MONTHS[d.month - 1]} {d.year}"
    age_years = max(0, (datetime.now() - d).days) / 365
    return text, _clamp(0.5 + age_years * 0.9)


# Статусы игроков по рейтингу (шкала 0-10), от низшего к высшему:
# (нижняя граница рейтинга, название, эмодзи для текста)
TIERS = [
    (0.00, "SUB 3", "🪨"),
    (3.00, "SUB 5", "🥉"),
    (5.00, "LTN", "🙂"),
    (6.50, "MTN", "😎"),
    (7.00, "HTN", "🔥"),
    (8.00, "CHADLITE", "😼"),
    (9.00, "CHAD", "🗿"),
    (9.60, "TRUE ADAM", "👑"),
]


def _tier(rating: float):
    current = TIERS[0]
    for tier in TIERS:
        if rating >= tier[0]:
            current = tier
    return current


def tier_label(rating: float) -> str:
    """SUB 3 / SUB 5 / LTN / MTN / HTN / CHAD / TRUE ADAM."""
    return _tier(rating)[1]


def tier_emoji(rating: float) -> str:
    return _tier(rating)[2]


def verdict(score: float) -> str:
    if score >= 9:
        return "топ"
    if score >= 7.5:
        return "отлично"
    if score >= 6:
        return "хорошо"
    if score >= 4:
        return "норм"
    return "слабо"


# Вес категории в итоговом балле: подарки и их стоимость — самое «дорогое» в профиле,
# остальное — поровну.
WEIGHTS = {
    "Аватар": 1.0,
    "@username": 1.0,
    "О себе": 1.0,
    "Подарки": 1.5,
    "Стоимость": 1.5,
    "Регистрация": 1.0,
    "Уровень TG": 1.0,
}


def known(categories):
    """Категории, по которым данные РЕАЛЬНО получены (score не None)."""
    return {c[0]: c[2] for c in categories if c[2] is not None}


def total_score(categories, other=None) -> float:
    """Итоговый балл профиля (0-10) — взвешенное среднее по категориям.

    Категории без данных (Telegram не ответил / человек скрыл) НЕ считаются нулём — они
    просто выпадают из подсчёта. Если передан `other` (категории соперника), считаем только
    по категориям, известным у ОБОИХ: так оба игрока сравниваются по одинаковому набору,
    и сбой Telegram у одного не даёт ему проигрыш. Именно этот балл решает, кто победил."""
    mine = known(categories)
    if other is not None:
        theirs = known(other)
        mine = {k: v for k, v in mine.items() if k in theirs}
    if not mine:
        return 0.0
    wsum = sum(WEIGHTS.get(k, 1.0) for k in mine)
    return round(sum(v * WEIGHTS.get(k, 1.0) for k, v in mine.items()) / wsum, 2)


def avatar_score(photo_count):
    if photo_count is None:
        return None, "нет данных"
    if photo_count <= 0:
        return 0.0, "нет фото"
    score = _clamp(4.5 + min(photo_count, 10) * 0.54)
    return score, f"{photo_count} фото · {verdict(score)}"


def username_score(username: str):
    if not username:
        return 0.0, "не задан"
    length = len(username)
    letters_only = username.replace("_", "").isalpha()
    # короткий "красивый" ник ценится выше длинного с цифрами
    base = 10.0 - max(0, length - 4) * 0.35 + (0.4 if letters_only else -0.6)
    subtitle = f"{length} букв · {'слово' if letters_only else 'с цифрами'}"
    return _clamp(max(2.0, base)), subtitle


def bio_score(bio, known=True):
    if not known:
        return None, "нет данных"
    if not bio:
        return 0.0, "пусто"
    return _clamp(3.5 + len(bio) * 0.09), f"{len(bio)} симв."


def gifts_score(gifts_total, nft_count: int):
    if gifts_total is None:
        return None, "нет данных"
    if gifts_total <= 0:
        return 0.0, "нет подарков"
    subtitle = f"{gifts_total} шт"
    if nft_count:
        subtitle += f" · {nft_count} NFT"
    return _clamp(2.0 + gifts_total * 0.5 + nft_count * 1.5), subtitle


def value_score(stars_value, nft_count: int):
    """Стоимость = сумма цен обычных подарков в звёздах. У NFT-подарков цены в API нет,
    поэтому они показываются отдельно (+N NFT) и дают бонус к баллу."""
    # "зв." вместо эмодзи звезды — в шрифте карточки (DejaVu) нет символа ⭐
    if stars_value is None:
        return None, "нет данных"
    if stars_value <= 0 and nft_count <= 0:
        return 0.0, "0 зв."
    subtitle = f"{stars_value:,} зв.".replace(",", " ")
    if nft_count:
        subtitle += f" + {nft_count} NFT"
    return _clamp(math.log10(stars_value + 1) * 2.5 + nft_count * 2.0), subtitle


def tg_level_score(level, is_premium: bool, known=True):
    """level — официальный уровень аккаунта Telegram. None = скрыт или не удалось
    получить: это «нет данных», а не плохой уровень, поэтому в баллы не идёт."""
    if level is None or not known:
        return None, "скрыт · Premium" if is_premium else "скрыт"
    subtitle = f"Уровень {level}" + (" · Premium" if is_premium else "")
    return _clamp(2.0 + level * 0.4 + (1.5 if is_premium else 0)), subtitle


def compute_categories(user_id: int, username: str, stats: dict, is_premium: bool,
                       custom_status: str = None):
    """Возвращает список категорий в фиксированном порядке для карточки результата:
    [(label, subtitle, score|None), ...] (None — данных нет). stats — результат common.get_tg_stats().
    custom_status (заданный через /me) имеет приоритет над Telegram-био в «О себе»."""
    a_score, a_sub = avatar_score(stats["photo_count"])
    u_score, u_sub = username_score(username)
    if custom_status:
        b_score, b_sub = bio_score(custom_status)
    else:
        b_score, b_sub = bio_score(stats["bio"], known=stats.get("bio_known", True))
    g_score, g_sub = gifts_score(stats["gifts_total"], stats["nft_count"])
    v_score, v_sub = value_score(stats["stars_value"], stats["nft_count"])
    r_sub, r_score = estimate_registration(user_id)
    t_score, t_sub = tg_level_score(stats["level"], is_premium, known=stats.get("bio_known", True))

    return [
        ("Аватар", a_sub, a_score),
        ("@username", u_sub, u_score),
        ("О себе", b_sub, b_score),
        ("Подарки", g_sub, g_score),
        ("Стоимость", v_sub, v_score),
        ("Регистрация", r_sub, r_score),
        ("Уровень TG", t_sub, t_score),
    ]
