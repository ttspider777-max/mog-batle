"""
Альтернативный дизайн карточек — "Neon Arena": неоновая киберспортивная тема
(тёмно-фиолетовый фон, свечение вокруг аватаров и текста, циан/маджента акценты).

Использует те же данные (challenger/opponent dict), что и images.py, поэтому
подключается в battle.py и admin.py простой заменой импорта.
"""

import io
import os
import math
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

from images import _circular_avatar, _dashed_circle  # переиспользуем готовые куски

W, H = 1400, 910

BG_TOP = (24, 10, 46)
BG_BOTTOM = (6, 4, 14)
CYAN = (70, 235, 235)
MAGENTA = (235, 70, 200)
ORANGE = (255, 150, 60)
WHITE = (248, 248, 252)
GREY = (165, 160, 185)
PANEL_BG = (22, 14, 40)
PANEL_BORDER_A = (100, 60, 160)

# Шрифты лежат прямо в проекте (assets/fonts) — не зависят от системных шрифтов ОС.
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
F_BLACK = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
F_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")


def _font(path, size):
    return ImageFont.truetype(path, size)


def _vertical_gradient(size, top, bottom):
    w, h = size
    base = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        base.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return base.resize((w, h))


def _text_width(draw, text, font, tracking=0):
    widths = [draw.textlength(ch, font=font) for ch in text]
    return sum(widths) + tracking * max(len(text) - 1, 0)


def _text_tracked(draw, x, y, text, font, fill, tracking=0):
    cx = x
    for ch in text:
        draw.text((cx, y), ch, font=font, fill=fill)
        cx += draw.textlength(ch, font=font) + tracking


def _glow_text_centered(base_img, cx, y, text, font, color, tracking=0, glow_radius=10, glow_alpha=190):
    """Рисует текст со свечением: размытая цветная подложка + чёткий текст сверху."""
    draw_probe = ImageDraw.Draw(base_img)
    total_w = _text_width(draw_probe, text, font, tracking)
    x0 = cx - total_w / 2

    glow_layer = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    _text_tracked(gd, x0, y, text, font, color + (glow_alpha,), tracking)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(glow_radius))
    base_img.alpha_composite(glow_layer) if base_img.mode == "RGBA" else base_img.paste(
        Image.alpha_composite(base_img.convert("RGBA"), glow_layer).convert(base_img.mode)
    )

    draw = ImageDraw.Draw(base_img)
    _text_tracked(draw, x0, y, text, font, WHITE, tracking)
    return total_w


def _neon_ring(base_img, cx, cy, r, color, width=6, glow_radius=14):
    glow_layer = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color + (255,), width=width)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(glow_radius))
    merged = Image.alpha_composite(base_img.convert("RGBA"), glow_layer)
    base_img.paste(merged.convert(base_img.mode))
    draw = ImageDraw.Draw(base_img)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=max(2, width // 2))


def _panel(draw, box, radius=16, border=CYAN):
    draw.rounded_rectangle(box, radius=radius, fill=PANEL_BG, outline=PANEL_BORDER_A, width=2)
    draw.rounded_rectangle(box, radius=radius, outline=border, width=1)


def _score_panel(img, draw, cx, top, label, value, accent, w_=190, h_=104):
    box = [cx - w_ / 2, top, cx + w_ / 2, top + h_]
    _panel(draw, box, border=accent)
    tw = draw.textlength(label, font=_font(F_REGULAR, 18))
    draw.text((cx - tw / 2, top + 14), label, font=_font(F_REGULAR, 18), fill=accent)
    tw2 = draw.textlength(value, font=_font(F_BLACK, 36))
    draw.text((cx - tw2 / 2, top + 42), value, font=_font(F_BLACK, 36), fill=WHITE)


def _base_canvas(season_label="SEASON 1"):
    img = _vertical_gradient((W, H), BG_TOP, BG_BOTTOM).convert("RGB")

    # лёгкое виньетирование по краям для глубины
    vign = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vign)
    vd.ellipse([-W * 0.25, -H * 0.25, W * 1.25, H * 1.25], fill=40)
    vign = vign.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(img, dark, vign)

    draw = ImageDraw.Draw(img)

    # двойная неоновая рамка (циан снаружи, маджента внутри)
    draw.rounded_rectangle([14, 14, W - 14, H - 14], radius=28, outline=CYAN, width=3)
    draw.rounded_rectangle([24, 24, W - 24, H - 24], radius=24, outline=MAGENTA, width=1)

    # плашка SEASON
    tag_font = _font(F_BLACK, 22)
    tag_text = season_label
    tw = draw.textlength(tag_text, font=tag_font)
    pad = 16
    box = [40, 36, 40 + tw + pad * 2, 36 + 40]
    draw.rounded_rectangle(box, radius=20, fill=(50, 20, 70), outline=MAGENTA, width=2)
    draw.text((40 + pad, 46), tag_text, font=tag_font, fill=ORANGE)

    _glow_text_centered(img, W / 2, 54, "MOG BATTLE", _font(F_BLACK, 78), MAGENTA, tracking=4, glow_radius=14)
    d2 = ImageDraw.Draw(img)
    sub = "OPEN CHALLENGE"
    subf = _font(F_REGULAR, 24)
    stw = _text_width(d2, sub, subf, tracking=8)
    _text_tracked(d2, W / 2 - stw / 2, 156, sub, subf, CYAN, tracking=8)

    d2.text((W - 260, H - 44), "@mogbattle_robot", font=_font(F_REGULAR, 20), fill=GREY)
    return img


def render_challenge_card_neon(challenger, avatar_bytes, season_label="SEASON 1"):
    img = _base_canvas(season_label)
    draw = ImageDraw.Draw(img)

    left_cx, right_cx = 420, 980
    circle_cy = 400
    diameter = 260
    r = diameter / 2

    _neon_ring(img, left_cx, circle_cy, r + 10, CYAN)
    draw = ImageDraw.Draw(img)

    avatar = _circular_avatar(avatar_bytes, diameter, (18, 12, 30))
    img.paste(avatar, (int(left_cx - avatar.width / 2), int(circle_cy - avatar.height / 2)), avatar)

    _glow_text_centered(img, W / 2, circle_cy - 44, "VS", _font(F_BLACK, 64), ORANGE, glow_radius=12)
    draw = ImageDraw.Draw(img)

    _dashed_circle(draw, right_cx, circle_cy, r + 6, (110, 100, 140), width=4)
    tw = draw.textlength("?", font=_font(F_BLACK, 90))
    draw.text((right_cx - tw / 2, circle_cy - 50), "?", font=_font(F_BLACK, 90), fill=(150, 140, 175))

    name_y = circle_cy + r + 30
    name = f"@{challenger['username']}" if challenger.get("username") else challenger.get("name", "")
    tw = draw.textlength(name, font=_font(F_BLACK, 34))
    draw.text((left_cx - tw / 2, name_y), name, font=_font(F_BLACK, 34), fill=WHITE)

    label_r = "ЛЮБОЙ ИГРОК"
    tw = draw.textlength(label_r, font=_font(F_BLACK, 30))
    draw.text((right_cx - tw / 2, name_y), label_r, font=_font(F_BLACK, 30), fill=WHITE)
    label_r2 = "МЕСТО СВОБОДНО"
    tw = draw.textlength(label_r2, font=_font(F_REGULAR, 19))
    draw.text((right_cx - tw / 2, name_y + 42), label_r2, font=_font(F_REGULAR, 19), fill=GREY)

    _score_panel(img, draw, left_cx, name_y + 82, "LTN", f"{challenger['rating']:.2f}", CYAN)
    _score_panel(img, draw, right_cx, name_y + 82, "БАЛЛ", "?", (110, 100, 140))

    bar_box = [60, H - 150, W - 60, H - 70]
    _panel(draw, bar_box, radius=18, border=ORANGE)
    txt = "ACCEPT THE CHALLENGE"
    tf = _font(F_BLACK, 32)
    tw = draw.textlength(txt, font=tf)
    draw.text((W / 2 - tw / 2, H - 128), txt, font=tf, fill=ORANGE)
    sub2 = "ПЕРВЫЙ НАЖАВШИЙ ПРИМЕТ БАТТЛ"
    stw = _text_width(draw, sub2, _font(F_REGULAR, 18), tracking=2)
    _text_tracked(draw, W / 2 - stw / 2, H - 90, sub2, _font(F_REGULAR, 18), GREY, tracking=2)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=93)
    buf.seek(0)
    return buf


def render_result_card_neon(challenger, opponent, winner_side, season_label="SEASON 1"):
    img = _base_canvas(season_label)
    draw = ImageDraw.Draw(img)

    left_cx, right_cx = 420, 980
    circle_cy = 400
    diameter = 260
    r = diameter / 2

    left_glow = ORANGE if winner_side == "left" else (90, 80, 110)
    right_glow = ORANGE if winner_side == "right" else (90, 80, 110)

    _neon_ring(img, left_cx, circle_cy, r + 10, left_glow)
    _neon_ring(img, right_cx, circle_cy, r + 10, right_glow)
    draw = ImageDraw.Draw(img)

    left_avatar = _circular_avatar(challenger.get("avatar"), diameter, (18, 12, 30))
    right_avatar = _circular_avatar(opponent.get("avatar"), diameter, (18, 12, 30))
    img.paste(left_avatar, (int(left_cx - left_avatar.width / 2), int(circle_cy - left_avatar.height / 2)), left_avatar)
    img.paste(right_avatar, (int(right_cx - right_avatar.width / 2), int(circle_cy - right_avatar.height / 2)), right_avatar)

    draw = ImageDraw.Draw(img)
    winner_cx = left_cx if winner_side == "left" else right_cx
    crown_font = _font(F_BLACK, 40)
    tw = draw.textlength("★", font=crown_font)
    draw.text((winner_cx - tw / 2, circle_cy - r - 52), "★", font=crown_font, fill=ORANGE)

    _glow_text_centered(img, W / 2, circle_cy - 44, "VS", _font(F_BLACK, 64), MAGENTA, glow_radius=12)
    draw = ImageDraw.Draw(img)

    name_y = circle_cy + r + 30

    def _name(u):
        return f"@{u['username']}" if u.get("username") else u.get("name", "")

    for cx_, u in ((left_cx, challenger), (right_cx, opponent)):
        n = _name(u)
        tw = draw.textlength(n, font=_font(F_BLACK, 32))
        draw.text((cx_ - tw / 2, name_y), n, font=_font(F_BLACK, 32), fill=WHITE)

    _score_panel(img, draw, left_cx, name_y + 48, "LTN", f"{challenger['rating']:.2f}", CYAN)
    _score_panel(img, draw, right_cx, name_y + 48, "LTN", f"{opponent['rating']:.2f}", CYAN)

    winner = challenger if winner_side == "left" else opponent
    loser = opponent if winner_side == "left" else challenger

    bar_box = [60, H - 150, W - 60, H - 70]
    _panel(draw, bar_box, radius=18, border=ORANGE)
    result_text = f"{_name(winner).upper()} МОГНУЛ {_name(loser).upper()}"
    tf = _font(F_BLACK, 27)
    tw = draw.textlength(result_text, font=tf)
    draw.text((W / 2 - tw / 2, H - 128), result_text, font=tf, fill=ORANGE)
    sub2 = "БАТТЛ ЗАВЕРШЁН"
    stw = _text_width(draw, sub2, _font(F_REGULAR, 18), tracking=2)
    _text_tracked(draw, W / 2 - stw / 2, H - 90, sub2, _font(F_REGULAR, 18), GREY, tracking=2)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=93)
    buf.seek(0)
    return buf
