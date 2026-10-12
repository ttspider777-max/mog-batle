"""
Детальная карточка результата баттла: два "профиля" с разбивкой по
категориям (Аватар, @username, О себе, Подарки, Стоимость, Регистрация,
Уровень TG), полоски прогресса, корона у победителя, штамп "MOGGED"
у проигравшего снизу — общий баннер с разницей очков.
"""

import io
import os
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from images import _circular_avatar  # переиспользуем готовую функцию аватара

W, H = 1600, 1000

BG_TOP = (20, 24, 34)
BG_BOTTOM = (9, 11, 16)
CARD_BG = (26, 30, 40)
CARD_BORDER = (55, 60, 74)
WHITE = (245, 245, 248)
GREY = (150, 155, 165)
LIGHT_GREY = (190, 193, 200)
GOLD = (235, 190, 100)
TRACK = (55, 60, 72)
BAR_FILL = (235, 237, 240)

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


def _text_centered(draw, cx, y, text, font, fill, tracking=0):
    if tracking:
        widths = [draw.textlength(ch, font=font) for ch in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = cx - total / 2
        for ch, wch in zip(text, widths):
            draw.text((x, y), ch, font=font, fill=fill)
            x += wch + tracking
    else:
        wtot = draw.textlength(text, font=font)
        draw.text((cx - wtot / 2, y), text, font=font, fill=fill)


def _draw_crown(draw, cx, base_y, width=64, height=42, color=GOLD):
    hw = width / 2
    top = base_y - height
    pts = [
        (cx - hw, base_y), (cx - hw, base_y - height * 0.35),
        (cx - hw * 0.55, base_y - height * 0.75), (cx - hw * 0.22, base_y - height * 0.35),
        (cx, top), (cx + hw * 0.22, base_y - height * 0.35),
        (cx + hw * 0.55, base_y - height * 0.75), (cx + hw, base_y - height * 0.35),
        (cx + hw, base_y),
    ]
    draw.polygon(pts, fill=color)
    draw.rectangle([cx - hw, base_y, cx + hw, base_y + height * 0.16], fill=color)


def _mogged_stamp(base_img, box):
    """Диагональный полупрозрачный штамп 'MOGGED' поверх панели проигравшего."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    font = _font(F_BLACK, 92)
    text = "MOGGED"
    tw = ld.textlength(text, font=font)
    # тень
    ld.text((w / 2 - tw / 2 + 6, h / 2 - 46 + 6), text, font=font, fill=(0, 0, 0, 140))
    ld.text((w / 2 - tw / 2, h / 2 - 46), text, font=font, fill=(255, 255, 255, 235))
    layer = layer.rotate(-10, expand=False, resample=Image.BICUBIC, center=(w / 2, h / 2))
    base_img.paste(layer, (int(x0), int(y0)), layer)


def _panel(draw, box, radius=22):
    draw.rounded_rectangle(box, radius=radius, fill=CARD_BG, outline=CARD_BORDER, width=2)


def _score_bar(draw, x0, x1, y, score, max_score=10.0):
    draw.line([(x0, y), (x1, y)], fill=TRACK, width=3)
    frac = max(0.02, min(1.0, score / max_score))
    draw.line([(x0, y), (x0 + (x1 - x0) * frac, y)], fill=BAR_FILL, width=3)


def _side_panel(base_img, draw, box, user, is_winner):
    x0, y0, x1, y1 = box
    _panel(draw, box)

    pad = 34
    avatar_d = 96
    ax, ay = x0 + pad, y0 + pad

    if is_winner:
        _draw_crown(draw, ax + avatar_d / 2, ay - 14, width=52, height=34)

    avatar = _circular_avatar(user.get("avatar"), avatar_d, (140, 145, 158), border_width=4)
    base_img.paste(avatar, (int(ax), int(ay)), avatar)

    name_x = ax + avatar_d + 34
    name = user.get("display_name", "")
    draw.text((name_x, ay - 4), name, font=_font(F_BLACK, 34), fill=WHITE)
    sub = f"@{user['username']}" if user.get("username") else "без юзернейма"
    draw.text((name_x, ay + 40), sub, font=_font(F_REGULAR, 20), fill=GREY)

    rating_text = f"{user['rating']:.2f}"
    rf = _font(F_BLACK, 50)
    rw = draw.textlength(rating_text, font=rf)
    draw.text((x1 - pad - rw, ay - 6), rating_text, font=rf, fill=WHITE)

    tag = user.get("tag", "LTN")
    tag_font = _font(F_BLACK, 18)
    tw = draw.textlength(tag, font=tag_font)
    tag_box = [name_x, ay + 74, name_x + tw + 28, ay + 74 + 32]
    draw.rounded_rectangle(tag_box, radius=14, outline=(120, 125, 140), width=2)
    draw.text((name_x + 14, ay + 80), tag, font=tag_font, fill=LIGHT_GREY)

    divider_y = ay + 130
    draw.line([(x0 + pad, divider_y), (x1 - pad, divider_y)], fill=CARD_BORDER, width=2)

    status = "WINNER" if is_winner else "MOGGED"
    status_color = LIGHT_GREY if is_winner else (110, 114, 124)
    draw.text((x0 + pad, divider_y + 14), status, font=_font(F_BLACK, 26), fill=status_color)

    rows_top = divider_y + 62
    row_h = (y1 - pad - rows_top) / len(user["categories"])
    label_font = _font(F_BLACK, 22)
    sub_font = _font(F_REGULAR, 15)
    score_font = _font(F_BLACK, 26)

    for i, (label, subtitle, score) in enumerate(user["categories"]):
        ry = rows_top + i * row_h
        draw.text((x0 + pad, ry), label, font=label_font, fill=WHITE)
        draw.text((x0 + pad, ry + 30), subtitle, font=sub_font, fill=GREY)

        score_text = f"{score:.2f}"
        sw = draw.textlength(score_text, font=score_font)
        draw.text((x1 - pad - sw, ry + 2), score_text, font=score_font, fill=WHITE)

        bar_y = ry + row_h - 14
        _score_bar(draw, x0 + pad, x1 - pad, bar_y, score)


def render_detailed_result_card(challenger, opponent, winner_side, season_label="SEASON 1"):
    """
    challenger / opponent: dict с ключами:
      display_name, username, rating, avatar (bytes|None), tag (str),
      categories: [(label, subtitle, score), ...] — см. scoring.compute_categories
    winner_side: 'left' | 'right'
    """
    img = _vertical_gradient((W, H), BG_TOP, BG_BOTTOM).convert("RGB")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([12, 12, W - 12, H - 12], radius=26, outline=(70, 76, 96), width=2)
    draw.text((40, 34), season_label, font=_font(F_BLACK, 24), fill=GOLD)

    _text_centered(draw, W / 2, 44, "MOG BATTLE", _font(F_BLACK, 58), WHITE, tracking=3)
    _text_centered(draw, W / 2, 118, "RESULT", _font(F_REGULAR, 20), GREY, tracking=10)

    panel_top = 180
    panel_bottom = H - 110
    left_box = [48, panel_top, 48 + 700, panel_bottom]
    right_box = [W - 48 - 700, panel_top, W - 48, panel_bottom]

    _side_panel(img, draw, left_box, challenger, winner_side == "left")
    draw = ImageDraw.Draw(img)
    _side_panel(img, draw, right_box, opponent, winner_side == "right")
    draw = ImageDraw.Draw(img)

    _text_centered(draw, W / 2, (panel_top + panel_bottom) / 2 - 30, "VS", _font(F_BLACK, 46), WHITE)

    loser_box = right_box if winner_side == "left" else left_box
    _mogged_stamp(img, loser_box)
    draw = ImageDraw.Draw(img)

    bar_box = [48, H - 88, W - 48, H - 30]
    draw.rounded_rectangle(bar_box, radius=16, fill=CARD_BG, outline=CARD_BORDER, width=2)

    winner_user = challenger if winner_side == "left" else opponent
    loser_user = opponent if winner_side == "left" else challenger
    winner_name = f"@{winner_user['username']}" if winner_user.get("username") else winner_user["display_name"]

    draw.text((72, H - 74), f"WINNER {winner_name}", font=_font(F_BLACK, 26), fill=WHITE)

    mid_text = f"{challenger['rating']:.2f}   VS   {opponent['rating']:.2f}"
    mf = _font(F_BLACK, 26)
    mw = draw.textlength(mid_text, font=mf)
    draw.text((W / 2 - mw / 2, H - 74), mid_text, font=mf, fill=WHITE)

    diff = abs(winner_user["rating"] - loser_user["rating"])
    diff_text = f"Difference +{diff:.2f}"
    df = _font(F_REGULAR, 22)
    dw = draw.textlength(diff_text, font=df)
    draw.text((W - 72 - dw, H - 70), diff_text, font=df, fill=GREY)

    draw.text((W - 250, H - 26), "@mogbattle_robot", font=_font(F_REGULAR, 18), fill=GREY)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=93)
    buf.seek(0)
    return buf
