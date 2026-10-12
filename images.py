"""
Генерация картинок баттла (карточка вызова / карточка результата) в стиле
приложенного примера: тёмный фон, двойная рамка, "MOG BATTLE" сверху,
два круглых аватара по бокам от "VS", рейтинг (LTN) под каждым игроком.
"""

import io
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

W, H = 1400, 910

BG_TOP = (18, 22, 34)
BG_BOTTOM = (10, 12, 20)
BORDER_COLOR = (70, 90, 130)
GOLD = (240, 190, 90)
WHITE = (245, 245, 248)
GREY = (150, 155, 165)
DARK_GREY = (90, 95, 105)
PANEL_BG = (28, 32, 45)
PANEL_BORDER = (60, 66, 84)
GREEN = (110, 220, 140)
RED = (230, 90, 90)

# Шрифты лежат прямо в проекте (assets/fonts) — так картинки рисуются одинаково
# на любой ОС (Windows/Mac/Linux), не завися от системных шрифтов.
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
F_BLACK = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
F_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")


def _font(path, size):
    return ImageFont.truetype(path, size)


def _vertical_gradient(size, top, bottom):
    w, h = size
    base = Image.new("RGB", (1, h), color=0)
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        base.putpixel((0, y), (r, g, b))
    return base.resize((w, h))


def _rounded_rect(draw, box, radius, outline=None, fill=None, width=1):
    draw.rounded_rectangle(box, radius=radius, outline=outline, fill=fill, width=width)


def _text_centered(draw, cx, y, text, font, fill, tracking=0):
    if tracking:
        text = (" " * 0).join(list(text))
        # emulate letter spacing manually
        widths = [draw.textlength(ch, font=font) for ch in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = cx - total / 2
        for ch, w_ in zip(text, widths):
            draw.text((x, y), ch, font=font, fill=fill)
            x += w_ + tracking
    else:
        w_ = draw.textlength(text, font=font)
        draw.text((cx - w_ / 2, y), text, font=font, fill=fill)


def _circular_avatar(avatar_bytes, diameter, border_color, border_width=6):
    """avatar_bytes: raw image bytes or None -> placeholder silhouette."""
    if avatar_bytes:
        try:
            im = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
        except Exception:
            im = None
    else:
        im = None

    if im is None:
        im = Image.new("RGB", (diameter, diameter), (35, 38, 50))
        d = ImageDraw.Draw(im)
        # простой силуэт-плейсхолдер
        d.ellipse(
            [diameter * 0.30, diameter * 0.16, diameter * 0.70, diameter * 0.56],
            fill=(70, 75, 92)
        )
        d.pieslice(
            [diameter * 0.12, diameter * 0.46, diameter * 0.88, diameter * 1.22],
            180, 360, fill=(70, 75, 92)
        )

    im = ImageOps.fit(im, (diameter, diameter), Image.LANCZOS)

    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
    im.putalpha(mask)

    ring_pad = border_width
    canvas = Image.new("RGBA", (diameter + ring_pad * 2, diameter + ring_pad * 2), (0, 0, 0, 0))
    cd = ImageDraw.Draw(canvas)
    cd.ellipse((0, 0, canvas.width, canvas.height), fill=border_color + (255,))
    canvas.paste(im, (ring_pad, ring_pad), im)
    return canvas


def _dashed_circle(draw, cx, cy, r, color, width=4, dash_len=14, gap_len=10):
    import math
    circumference = 2 * math.pi * r
    n = max(int(circumference / (dash_len + gap_len)), 8)
    angle_step = 360 / n
    dash_angle = angle_step * dash_len / (dash_len + gap_len)
    for i in range(n):
        start = i * angle_step
        end = start + dash_angle
        draw.arc(
            [cx - r, cy - r, cx + r, cy + r], start=start, end=end, fill=color, width=width
        )


def _draw_crown(draw, cx, base_y, width=76, height=48, color=GOLD):
    """Рисует простую корону примитивами (без эмодзи-глифов)."""
    hw = width / 2
    top = base_y - height
    pts = [
        (cx - hw, base_y),
        (cx - hw, base_y - height * 0.35),
        (cx - hw * 0.55, base_y - height * 0.75),
        (cx - hw * 0.22, base_y - height * 0.35),
        (cx, top),
        (cx + hw * 0.22, base_y - height * 0.35),
        (cx + hw * 0.55, base_y - height * 0.75),
        (cx + hw, base_y - height * 0.35),
        (cx + hw, base_y),
    ]
    draw.polygon(pts, fill=color)
    draw.rectangle([cx - hw, base_y, cx + hw, base_y + height * 0.16], fill=color)
    # три маленькие "жемчужины" на зубцах
    for dx in (-hw * 0.55, 0, hw * 0.55):
        r = 6
        draw.ellipse([cx + dx - r, base_y - height * 0.75 - r if dx != 0 else top - r,
                      cx + dx + r, base_y - height * 0.75 + r if dx != 0 else top + r],
                     fill=(255, 255, 255) if dx == 0 else color)


def _score_panel(draw, cx, top, label, value, w_=180, h_=100):
    box = [cx - w_ / 2, top, cx + w_ / 2, top + h_]
    _rounded_rect(draw, box, radius=14, fill=PANEL_BG, outline=PANEL_BORDER, width=2)
    _text_centered(draw, cx, top + 16, label, _font(F_REGULAR, 20), GREY, tracking=2)
    _text_centered(draw, cx, top + 46, value, _font(F_BLACK, 34), WHITE)


def _base_canvas(season_label="SEASON 1"):
    img = _vertical_gradient((W, H), BG_TOP, BG_BOTTOM).convert("RGB")
    draw = ImageDraw.Draw(img)

    # тройная рамка
    for i, alpha_w in enumerate([3, 2, 1]):
        pad = 10 + i * 8
        _rounded_rect(
            draw, [pad, pad, W - pad, H - pad], radius=26,
            outline=BORDER_COLOR, width=alpha_w
        )

    draw.text((48, 40), season_label, font=_font(F_BLACK, 26), fill=GOLD)

    _text_centered(draw, W / 2, 60, "MOG BATTLE", _font(F_BLACK, 76), WHITE, tracking=4)
    _text_centered(draw, W / 2, 158, "OPEN CHALLENGE", _font(F_REGULAR, 26), GREY, tracking=8)

    draw.text(
        (W - 250, H - 44), "@mogbattle_robot", font=_font(F_REGULAR, 20), fill=GREY
    )
    return img, draw


def render_challenge_card(challenger, avatar_bytes, season_label="SEASON 1"):
    """
    challenger: dict с ключами name, username, rating
    avatar_bytes: байты фото профиля (может быть None)
    """
    img, draw = _base_canvas(season_label)

    left_cx, right_cx = 420, 980
    circle_cy = 400
    diameter = 260

    avatar = _circular_avatar(avatar_bytes, diameter, (210, 214, 222))
    img.paste(avatar, (int(left_cx - avatar.width / 2), int(circle_cy - avatar.height / 2)), avatar)

    _text_centered(draw, W / 2, circle_cy - 40, "VS", _font(F_BLACK, 60), WHITE)

    # правый круг — пунктир "?"
    _dashed_circle(draw, right_cx, circle_cy, diameter / 2 + 6, DARK_GREY, width=4)
    _text_centered(draw, right_cx, circle_cy - 46, "?", _font(F_BLACK, 90), GREY)

    name_y = circle_cy + diameter / 2 + 30
    _text_centered(draw, left_cx, name_y, f"@{challenger['username']}" if challenger['username'] else challenger['name'],
                   _font(F_BLACK, 34), WHITE)
    _text_centered(draw, left_cx, name_y + 44, f"@{challenger['username']}" if challenger['username'] else "",
                   _font(F_REGULAR, 22), GREY)

    _text_centered(draw, right_cx, name_y, "ЛЮБОЙ ИГРОК", _font(F_BLACK, 32), WHITE)
    _text_centered(draw, right_cx, name_y + 44, "МЕСТО СВОБОДНО", _font(F_REGULAR, 20), GREY)

    _score_panel(draw, left_cx, name_y + 90, "LTN", f"{challenger['rating']:.2f}")
    _score_panel(draw, right_cx, name_y + 90, "БАЛЛ", "?")

    # нижняя плашка
    bar_box = [60, H - 150, W - 60, H - 70]
    _rounded_rect(draw, bar_box, radius=18, fill=PANEL_BG, outline=PANEL_BORDER, width=2)
    _text_centered(draw, W / 2, H - 128, "ACCEPT THE CHALLENGE", _font(F_BLACK, 32), WHITE)
    _text_centered(draw, W / 2, H - 90, "ПЕРВЫЙ НАЖАВШИЙ ПРИМЕТ БАТТЛ", _font(F_REGULAR, 18), GREY, tracking=2)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return buf


def render_result_card(challenger, opponent, winner_side, season_label="SEASON 1"):
    """
    challenger / opponent: dict name, username, rating (уже ОБНОВЛЁННЫЙ рейтинг)
    winner_side: 'left' или 'right'
    avatar_bytes хранится в самих словарях под ключом 'avatar'
    """
    img, draw = _base_canvas(season_label)

    left_cx, right_cx = 420, 980
    circle_cy = 400
    diameter = 260

    left_border = GOLD if winner_side == "left" else (90, 95, 108)
    right_border = GOLD if winner_side == "right" else (90, 95, 108)

    left_avatar = _circular_avatar(challenger.get("avatar"), diameter, left_border)
    right_avatar = _circular_avatar(opponent.get("avatar"), diameter, right_border)

    img.paste(left_avatar, (int(left_cx - left_avatar.width / 2), int(circle_cy - left_avatar.height / 2)), left_avatar)
    img.paste(right_avatar, (int(right_cx - right_avatar.width / 2), int(circle_cy - right_avatar.height / 2)), right_avatar)

    winner_cx = left_cx if winner_side == "left" else right_cx
    _draw_crown(draw, winner_cx, circle_cy - diameter / 2 - 18)

    _text_centered(draw, W / 2, circle_cy - 40, "VS", _font(F_BLACK, 60), WHITE)

    name_y = circle_cy + diameter / 2 + 30

    def _name(u):
        return f"@{u['username']}" if u.get("username") else u.get("name", "")

    _text_centered(draw, left_cx, name_y, _name(challenger), _font(F_BLACK, 32), WHITE)
    _text_centered(draw, right_cx, name_y, _name(opponent), _font(F_BLACK, 32), WHITE)

    _score_panel(draw, left_cx, name_y + 50, "LTN", f"{challenger['rating']:.2f}")
    _score_panel(draw, right_cx, name_y + 50, "LTN", f"{opponent['rating']:.2f}")

    winner_name = challenger if winner_side == "left" else opponent
    loser_name = opponent if winner_side == "left" else challenger

    bar_box = [60, H - 150, W - 60, H - 70]
    _rounded_rect(draw, bar_box, radius=18, fill=PANEL_BG, outline=GOLD, width=2)
    result_text = f"{_name(winner_name).upper()} МОГНУЛ {_name(loser_name).upper()}"
    _text_centered(draw, W / 2, H - 128, result_text, _font(F_BLACK, 28), GOLD)
    _text_centered(draw, W / 2, H - 90, "БАТТЛ ЗАВЕРШЁН", _font(F_REGULAR, 18), GREY, tracking=2)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return buf
