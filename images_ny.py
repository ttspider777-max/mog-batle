"""
Новогодние карточки MOG BATTLE: вызов (открытый / адресный) и приветствие в главном меню.
Рисуются кодом через ny_art — разные темы по seed, чтобы карточки не были одинаковыми.
"""

from PIL import Image, ImageDraw

import ny_art as ny
from images import _circular_avatar

W, H = 1600, 1000


def _dashed_ring(img, cx, cy, r, color, width=5, n=46):
    import math
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(n):
        a0 = i * 360 / n
        d.arc([cx - r, cy - r, cx + r, cy + r], a0, a0 + 360 / n * 0.58, fill=color, width=width)
    img.alpha_composite(layer)


def _ring(img, cx, cy, r, color, width=6):
    ny.glow_dot(img, cx, cy, r, color, alpha=70, blur=26)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=width)


def render_challenge_card_ny(challenger, avatar_bytes, seed=0, target_name=None):
    """challenger: dict(name, username, rating). target_name — если вызов адресный."""
    theme = ny.pick_theme(seed)
    mirror = theme["mirror"]
    img = ny.background(theme, seed, (W, H))
    ny.snow(img, seed)
    ny.garland(img, theme, seed)

    ny.glow_text(img, W / 2, 62, "MOG BATTLE", ny.font(92, 900), (255, 255, 255),
                 glow_color=theme["glow"], tracking=4, radius=18)
    d = ImageDraw.Draw(img)
    sub = "ЛИЧНЫЙ ВЫЗОВ" if target_name else "OPEN CHALLENGE"
    ny.text_c(d, W / 2, 168, sub, ny.font(20, 600), theme["accent"], tracking=14)

    # главная стеклянная панель
    box = [64, 232, W - 64, 800]
    ny.shadow(img, box, radius=36)
    ny.glass(img, box, radius=36, strength=36, border=100)

    lcx, rcx, cy = 430, 1170, 470
    r = 150
    _ring(img, lcx, cy, r + 12, theme["gold"], 6)
    av = _circular_avatar(avatar_bytes, r * 2, (20, 24, 40), border_width=4)
    img.alpha_composite(av, (int(lcx - av.width / 2), int(cy - av.height / 2)))
    ny.crown(img, lcx - 70, cy - r + 14, theme, w=64, h=42)

    _dashed_ring(img, rcx, cy, r + 8, (255, 255, 255, 150))
    d = ImageDraw.Draw(img)
    qf = ny.font(150, 900)
    d.text((rcx - d.textlength("?", font=qf) / 2, cy - 100), "?", font=qf, fill=(255, 255, 255, 235))

    ny.glow_text(img, W / 2, cy - 54, "VS", ny.font(78, 900), (255, 255, 255),
                 glow_color=theme["glow"], radius=14)
    d = ImageDraw.Draw(img)

    name = f"@{challenger['username']}" if challenger.get("username") else challenger.get("name", "")
    nf = ny.fit_text(d, name, lambda s: ny.font(s, 800), 480, 40, 22)
    ny.text_c(d, lcx, cy + r + 36, name, nf, (255, 255, 255))
    ny.text_c(d, lcx, cy + r + 90, f"LTN  {challenger['rating']:.2f}", ny.font(26, 700), theme["accent"],
              tracking=2)

    rt = (target_name or "ЛЮБОЙ ИГРОК").upper() if not target_name else target_name
    rf = ny.fit_text(d, rt, lambda s: ny.font(s, 800), 480, 40, 22)
    ny.text_c(d, rcx, cy + r + 36, rt, rf, (255, 255, 255))
    ny.text_c(d, rcx, cy + r + 90, "ЖДЁМ СОПЕРНИКА" if not target_name else "ЖДЁМ ОТВЕТА",
              ny.font(22, 600), (200, 208, 226), tracking=4)

    # нижняя кнопка-плашка
    bar = [64, 826, W - 64, 940]
    ny.shadow(img, bar, radius=28, blur=16, alpha=100, dy=6)
    ny.glass(img, bar, radius=28, strength=60, border=140, tint=theme["gold"])
    d = ImageDraw.Draw(img)
    ny.text_c(d, W / 2, 846, "ACCEPT THE CHALLENGE", ny.font(40, 900), (255, 255, 255), tracking=3)
    ny.text_c(d, W / 2, 898, "ПЕРВЫЙ НАЖАВШИЙ ПРИМЕТ БАТТЛ", ny.font(18, 600), (235, 238, 248),
              tracking=5)

    cat_w = 268
    cat_x = W - 64 - cat_w - 30 if not mirror else 64 + 30
    ny.paste_cat(img, theme, cat_x, ny.cat_top(232, cat_w), cat_w, flip=mirror)
    gx = 220 if not mirror else W - 220 - 246
    ny.gifts(img, gx, 236, theme, scale=0.9, flip=mirror)

    d = ImageDraw.Draw(img)
    tf = ny.font(15, 500)
    d.text((W / 2 - d.textlength(ny.BOT_TAG, font=tf) / 2, H - 38), ny.BOT_TAG, font=tf,
           fill=(200, 208, 226))
    return ny.finish(img)


def render_welcome_card(seed=0):
    """Баннер для /start: заголовок, котик, подарки и три коротких «преимущества»."""
    theme = ny.pick_theme(seed)
    w, h = 1600, 900
    img = ny.background(theme, seed, (w, h))
    ny.snow(img, seed, count=110)
    ny.garland(img, theme, seed)

    ny.glow_text(img, 560, 190, "MOG", ny.font(190, 900), (255, 255, 255),
                 glow_color=theme["glow"], radius=26)
    ny.glow_text(img, 560, 372, "BATTLE", ny.font(150, 900), theme["gold"],
                 glow_color=theme["gold"], radius=22, alpha=120)
    d = ImageDraw.Draw(img)
    ny.text_c(d, 560, 548, "НОВОГОДНИЙ СЕЗОН", ny.font(26, 700), theme["accent"], tracking=10)

    chips = ["7 метрик профиля", "честный счёт", "реванш"]
    x = 130
    for t in chips:
        x += ny.chip(img, x, 640, t, ny.font(24, 700), (255, 255, 255), (255, 255, 255, 190),
                     pad=22, height=52, fill=(255, 255, 255, 38)) + 16

    d = ImageDraw.Draw(img)
    d.text((130, 730), "бросай вызов — забирай подарки", font=ny.hand(52, 700), fill=theme["accent"])

    # справа: большой котик на подарках
    ny.gifts(img, 1030, 860, theme, scale=1.5)
    ny.paste_cat(img, theme, 1090, 80, 440)
    d = ImageDraw.Draw(img)
    tf = ny.font(16, 500)
    d.text((w - 30 - d.textlength(ny.BOT_TAG, font=tf), h - 36), ny.BOT_TAG, font=tf, fill=(200, 208, 226))
    return ny.finish(img)
