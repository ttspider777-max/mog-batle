"""
Карточка результата баттла в новогоднем стиле: два «стеклянных» профиля с разбивкой по
семи категориям, корона у победителя, штамп MOGGED, котик и подарки. Тема (цвета, котик,
раскладка) выбирается по ID баттла — каждая игра выглядит по-своему.
"""

import random

from PIL import Image, ImageDraw

import ny_art as ny
from images import _circular_avatar

W, H = 1600, 1000

WIN_NOTES = ["подарочек)", "ёлочка)", "молодец)", "мандаринка)", "снежок)", "топ)"]
LOSE_NOTES = ["уголёк)", "носок)", "сосулька)", "в следующий раз)", "ничего)", "сугроб)"]


def _mogged_stamp(img, box, theme):
    x0, y0, x1, y1 = box
    w, h = 520, 190
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = ny.font(96, 900)
    tw = d.textlength("MOGGED", font=f)
    d.text(((w - tw) / 2 + 6, 40 + 7), "MOGGED", font=f, fill=(0, 0, 0, 120))
    d.text(((w - tw) / 2, 40), "MOGGED", font=f, fill=(255, 255, 255, 250),
           stroke_width=7, stroke_fill=(14, 14, 20, 255))
    layer = layer.rotate(-9, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(layer, (int(x0 + 50), int((y0 + y1) / 2 - layer.height / 2 + 30)))


def _side_panel(img, box, user, is_winner, theme, note):
    x0, y0, x1, y1 = box
    ny.shadow(img, box, radius=32)
    ny.glass(img, box, radius=32, strength=40 if is_winner else 30,
             border=120 if is_winner else 70)
    d = ImageDraw.Draw(img)

    pad = 34
    av_d = 104
    ax, ay = x0 + pad, y0 + pad + 6
    ring = theme["gold"] if is_winner else (170, 176, 190)
    avatar = _circular_avatar(user.get("avatar"), av_d, ring, border_width=4)
    img.alpha_composite(avatar, (int(ax), int(ay)))
    if is_winner:
        ny.crown(img, ax + av_d / 2 - 4, ay + 12, theme)

    d = ImageDraw.Draw(img)
    nx = ax + av_d + 30
    score_txt = f"{user['total']:.2f}"
    sf = ny.font(60, 800)
    sw = d.textlength(score_txt, font=sf)
    name_max = (x1 - pad) - sw - 20 - nx
    name = user.get("display_name", "")
    name_font = ny.fit_text(d, name, lambda s: ny.font(s, 800), name_max, 38, 22)
    d.text((nx, ay - 8), name, font=name_font, fill=(255, 255, 255))
    sub = f"@{user['username']}" if user.get("username") else "без юзернейма"
    d.text((nx, ay + 38), sub, font=ny.font(21, 500), fill=(205, 212, 228))
    d.text((x1 - pad - sw, ay - 10), score_txt, font=sf,
           fill=(255, 255, 255) if is_winner else (205, 210, 222))

    # чипы: статус и винстрик
    cy = ay + 70
    cw = ny.chip(img, nx, cy, user.get("tag", "LTN"), ny.font(18, 800), (255, 255, 255),
                 (230, 236, 250), fill=(255, 255, 255, 28))
    if user.get("streak", 0) >= 1:
        sx = nx + cw + 12
        txt = str(user["streak"])
        f = ny.font(18, 800)
        w = d.textlength(txt, font=f) + 54
        ny.rrect_a(img, [sx, cy, sx + w, cy + 34], 17, outline=(255, 190, 110),
                   width=2, fill=(255, 140, 60, 50))
        d = ImageDraw.Draw(img)
        ny.flame(d, sx + 14, cy + 3, 1.0)
        d.text((sx + 40, cy + 6), txt, font=f, fill=(255, 226, 170))

    div_y = ay + av_d + 28
    ny.line_a(img, (x0 + pad, div_y), (x1 - pad, div_y), (255, 255, 255, 70), 2)
    d = ImageDraw.Draw(img)

    status = "WINNER" if is_winner else "MOGGED"
    sfont = ny.font(30, 900)
    d.text((x0 + pad, div_y + 12), status, font=sfont,
           fill=(255, 255, 255) if is_winner else (190, 196, 210))
    sw_ = d.textlength(status, font=sfont)
    d.text((x0 + pad + sw_ + 18, div_y + 8), note, font=ny.hand(34, 700),
           fill=theme["accent"] if is_winner else (170, 200, 235))

    rows_top = div_y + 64
    cats = user["categories"]
    row_h = (y1 - 22 - rows_top) / len(cats)
    lf, sf2, scf = ny.font(23, 700), ny.font(15, 500), ny.font(27, 800)
    for i, (label, subtitle, score) in enumerate(cats):
        ry = rows_top + i * row_h
        d.text((x0 + pad, ry), label, font=lf, fill=(255, 255, 255))
        d.text((x0 + pad, ry + 28), subtitle, font=sf2, fill=(190, 198, 214))
        txt = "—" if score is None else f"{score:.2f}"
        tw = d.textlength(txt, font=scf)
        d.text((x1 - pad - tw, ry + 2), txt, font=scf, fill=(255, 255, 255))
        by = ry + row_h - 6
        ny.line_a(img, (x0 + pad, by), (x1 - pad, by), (255, 255, 255, 55), 4)
        d = ImageDraw.Draw(img)
        frac = max(0.02, min(1.0, (score or 0) / 10))
        fillc = theme["accent"] if is_winner else (225, 230, 240)
        d.line([(x0 + pad, by), (x0 + pad + (x1 - x0 - 2 * pad) * frac, by)], fill=fillc, width=4)


def render_detailed_result_card(left, right, winner_side, seed=0, season=None):
    """left / right: dict(display_name, username, total, avatar, tag, streak, categories).
    seed — ID баттла: по нему выбирается тема и подписи-«рукописи»."""
    theme = ny.pick_theme(seed)
    rnd = random.Random(seed * 13 + 7)
    img = ny.background(theme, seed, (W, H))
    ny.snow(img, seed)
    ny.garland(img, theme, seed)
    mirror = theme["mirror"]

    ny.glow_text(img, W / 2, 62, "MOG BATTLE", ny.font(92, 900), (255, 255, 255),
                 glow_color=theme["glow"], tracking=4, radius=18)
    d = ImageDraw.Draw(img)
    ny.text_c(d, W / 2, 168, "DIVINE CARD", ny.font(20, 600), theme["accent"], tracking=14)
    sx = W - 44 if mirror else 44
    for txt, fnt, col, yy in ((f"SEASON {season}" if season else "MOG", ny.font(22, 800), theme["gold"], 74),
                              ("NEW YEAR EDITION", ny.font(13, 600), (210, 216, 232), 102)):
        tw = d.textlength(txt, font=fnt)
        d.text((sx - tw if mirror else sx, yy), txt, font=fnt, fill=col)

    top, bottom = 232, H - 118
    lb = [48, top, 48 + 700, bottom]
    rb = [W - 48 - 700, top, W - 48, bottom]

    win = left if winner_side == "left" else right
    lose = right if winner_side == "left" else left
    wnote, lnote = rnd.choice(WIN_NOTES), rnd.choice(LOSE_NOTES)

    # котик и подарки сидят на верхней кромке панелей
    cat_w = 268
    gifts_x = 205 if not mirror else W - 205 - 246
    cat_x = W - 48 - cat_w - 40 if not mirror else 185

    _side_panel(img, lb, left, winner_side == "left", theme,
                wnote if winner_side == "left" else lnote)
    _side_panel(img, rb, right, winner_side == "right", theme,
                wnote if winner_side == "right" else lnote)
    # котик и подарки — поверх панелей: котик держится лапками за край, подарки стоят на нём
    ny.paste_cat(img, theme, cat_x, ny.cat_top(top, cat_w), cat_w, flip=mirror)
    ny.gifts(img, gifts_x, top + 4, theme, scale=0.9, flip=mirror)
    d = ImageDraw.Draw(img)

    ny.glow_text(img, W / 2, (top + bottom) / 2 - 36, "VS", ny.font(64, 900), (255, 255, 255),
                 glow_color=theme["glow"], radius=12)

    loser_box = rb if winner_side == "left" else lb
    _mogged_stamp(img, loser_box, theme)

    # нижняя плашка
    bar = [48, H - 92, W - 48, H - 30]
    ny.shadow(img, bar, radius=20, blur=14, alpha=90, dy=6)
    ny.glass(img, bar, radius=20, strength=44, border=100)
    d = ImageDraw.Draw(img)
    wname = f"@{win['username']}" if win.get("username") else win["display_name"]
    wf = ny.fit_text(d, wname, lambda s: ny.font(s, 800), 420, 28, 18)
    d.text((76, H - 74), "WINNER", font=ny.font(15, 700), fill=theme["gold"])
    d.text((76 + 82, H - 82), wname, font=wf, fill=(255, 255, 255))
    ny.text_c(d, W / 2, H - 83, f"{left['total']:.2f}  :  {right['total']:.2f}",
              ny.font(32, 900), (255, 255, 255))
    diff = abs(win["total"] - lose["total"])
    dt = f"разница +{diff:.2f}"
    df = ny.font(22, 600)
    d.text((W - 76 - d.textlength(dt, font=df), H - 77), dt, font=df, fill=(205, 212, 228))
    tf = ny.font(14, 500)
    d.text((W - 48 - d.textlength(ny.BOT_TAG, font=tf) - 8, H - 26), ny.BOT_TAG, font=tf,
           fill=(190, 198, 214))
    return ny.finish(img)
