"""
Новогодний арт для карточек MOG BATTLE — всё рисуется кодом (Pillow), без внешних
картинок: котик в шапке, подарки, гирлянда, снег, «стеклянные» панели.

Есть несколько тем (мороз, рубин, северное сияние, полночь) — тема выбирается по seed
(ID баттла), поэтому карточки разных игр выглядят по-разному: другие цвета, другой
котик (окрас и головной убор), подарки и зеркальная раскладка.
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
_MONT = os.path.join(FONT_DIR, "Montserrat.ttf")
_CAVEAT = os.path.join(FONT_DIR, "Caveat.ttf")
_FALLBACK = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

BOT_TAG = "@mogggbattle_robot"

_font_cache = {}


def font(size, weight=700):
    key = ("m", size, weight)
    if key not in _font_cache:
        try:
            f = ImageFont.truetype(_MONT, size)
            f.set_variation_by_axes([weight])
        except Exception:
            f = ImageFont.truetype(_FALLBACK, size)
        _font_cache[key] = f
    return _font_cache[key]


def hand(size, weight=600):
    key = ("c", size, weight)
    if key not in _font_cache:
        try:
            f = ImageFont.truetype(_CAVEAT, size)
            f.set_variation_by_axes([weight])
        except Exception:
            f = ImageFont.truetype(_FALLBACK, size)
        _font_cache[key] = f
    return _font_cache[key]


# ---------------------------------------------------------------- темы

THEMES = [
    dict(  # ❄️ мороз — серо-голубой, серый котик в красном колпаке
        name="frost",
        bg=((92, 106, 134), (38, 46, 70)),
        glow=(160, 200, 255),
        accent=(170, 215, 255),
        gold=(246, 208, 120),
        bulbs=[(255, 96, 96), (255, 213, 100), (110, 190, 255), (255, 255, 255)],
        fur=(150, 152, 160), fur2=(96, 98, 108), hat="santa", hat_color=(214, 48, 58),
        gifts=[(214, 48, 58), (60, 150, 230), (246, 208, 120)],
        mirror=False,
    ),
    dict(  # 🍒 рубин — красно-золотой, рыжий котик с оленьими рогами
        name="ruby",
        bg=((136, 30, 48), (48, 10, 24)),
        glow=(255, 150, 120),
        accent=(255, 214, 140),
        gold=(255, 218, 130),
        bulbs=[(255, 220, 120), (255, 255, 255), (120, 230, 150), (255, 140, 160)],
        fur=(238, 156, 84), fur2=(196, 104, 44), hat="antlers", hat_color=(120, 72, 40),
        gifts=[(40, 150, 90), (255, 218, 130), (236, 236, 242)],
        mirror=True,
    ),
    dict(  # 🌌 северное сияние — фиолетово-бирюзовый, белый котик в колпаке эльфа
        name="aurora",
        bg=((46, 34, 108), (10, 46, 70)),
        glow=(110, 255, 220),
        accent=(140, 255, 226),
        gold=(255, 226, 140),
        bulbs=[(120, 255, 220), (190, 140, 255), (255, 170, 220), (255, 244, 170)],
        fur=(244, 244, 250), fur2=(190, 192, 210), hat="elf", hat_color=(46, 170, 104),
        gifts=[(150, 100, 235), (110, 230, 210), (255, 170, 210)],
        mirror=False,
    ),
    dict(  # 🌙 полночь — тёмно-синий с золотом, чёрный котик в шарфе и шапке-звезде
        name="midnight",
        bg=((22, 34, 82), (6, 9, 28)),
        glow=(255, 224, 140),
        accent=(255, 228, 150),
        gold=(255, 224, 140),
        bulbs=[(255, 224, 140), (130, 180, 255), (255, 255, 255), (255, 130, 150)],
        fur=(64, 66, 82), fur2=(36, 38, 50), hat="beanie", hat_color=(60, 110, 220),
        gifts=[(60, 110, 220), (255, 224, 140), (214, 48, 58)],
        mirror=True,
    ),
]


def pick_theme(seed):
    return THEMES[abs(int(seed or 0)) % len(THEMES)]


# ---------------------------------------------------------------- примитивы

def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(size, top, bottom):
    w, h = size
    col = Image.new("RGB", (1, h))
    for y in range(h):
        col.putpixel((0, y), _lerp(top, bottom, y / max(h - 1, 1)))
    return col.resize((w, h))


def _rr_mask(size, box, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius=radius, fill=255)
    return m


def rrect_a(img, box, radius, fill=None, outline=None, width=2):
    """Скруглённый прямоугольник с ПОЛУПРОЗРАЧНОЙ заливкой/рамкой (честное смешивание)."""
    x0, y0, x1, y1 = [int(v) for v in box]
    layer = Image.new("RGBA", (x1 - x0 + 2, y1 - y0 + 2), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([0, 0, x1 - x0, y1 - y0], radius=radius,
                                            fill=fill, outline=outline, width=width)
    img.alpha_composite(layer, (x0, y0))


def line_a(img, p0, p1, color, width=2):
    x0, y0 = int(min(p0[0], p1[0])) - width, int(min(p0[1], p1[1])) - width
    x1, y1 = int(max(p0[0], p1[0])) + width, int(max(p0[1], p1[1])) + width
    layer = Image.new("RGBA", (x1 - x0 + 1, y1 - y0 + 1), (0, 0, 0, 0))
    ImageDraw.Draw(layer).line([(p0[0] - x0, p0[1] - y0), (p1[0] - x0, p1[1] - y0)],
                               fill=color, width=width)
    img.alpha_composite(layer, (x0, y0))


def glow_dot(img, cx, cy, r, color, alpha=200, blur=None):
    """Мягкое свечение (боке / лампочка)."""
    pad = int(r * 3)
    layer = Image.new("RGBA", (pad * 2, pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([pad - r, pad - r, pad + r, pad + r], fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur or r * 0.8))
    img.alpha_composite(layer, (int(cx - pad), int(cy - pad)))


def text_c(draw, cx, y, text, fnt, fill, tracking=0, anchor_w=None):
    if tracking:
        widths = [draw.textlength(ch, font=fnt) for ch in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = cx - total / 2
        for ch, w in zip(text, widths):
            draw.text((x, y), ch, font=fnt, fill=fill)
            x += w + tracking
    else:
        draw.text((cx - draw.textlength(text, font=fnt) / 2, y), text, font=fnt, fill=fill)


def glow_text(img, cx, y, text, fnt, color, glow_color=None, tracking=0, radius=14, alpha=170):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    text_c(d, cx, y, text, fnt, (glow_color or color) + (alpha,), tracking)
    layer = layer.filter(ImageFilter.GaussianBlur(radius))
    img.alpha_composite(layer)
    text_c(ImageDraw.Draw(img), cx, y, text, fnt, color, tracking)


def fit_text(draw, text, fnt_factory, max_w, size, min_size=18):
    """Подбирает размер шрифта, чтобы текст влез в max_w."""
    while size > min_size and draw.textlength(text, font=fnt_factory(size)) > max_w:
        size -= 2
    return fnt_factory(size)


def glass(img, box, radius=30, tint=(255, 255, 255), strength=34, border=90, blur=16):
    """Матовое «стекло»: размытая подложка + полупрозрачная заливка + светлая рамка."""
    x0, y0, x1, y1 = [int(v) for v in box]
    region = img.crop((x0, y0, x1, y1)).convert("RGB").filter(ImageFilter.GaussianBlur(blur))
    mask = _rr_mask((x1 - x0, y1 - y0), (0, 0, x1 - x0 - 1, y1 - y0 - 1), radius)
    region = Image.blend(region, Image.new("RGB", region.size, tint), strength / 255)
    img.paste(region, (x0, y0), mask)
    rrect_a(img, [x0, y0, x1 - 1, y1 - 1], radius, outline=tint + (border,), width=2)


def shadow(img, box, radius=30, blur=22, alpha=110, dy=10):
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([x0, y0 + dy, x1, y1 + dy], radius=radius,
                                            fill=(0, 0, 0, alpha))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


# ---------------------------------------------------------------- фон, снег, гирлянда

def background(theme, seed, size=(1600, 1000)):
    w, h = size
    img = gradient(size, *theme["bg"]).convert("RGBA")
    rnd = random.Random(seed * 7919 + 13)

    # мягкие цветные пятна света
    for _ in range(5):
        glow_dot(img, rnd.randint(0, w), rnd.randint(int(h * .15), h), rnd.randint(150, 260),
                 theme["glow"], alpha=rnd.randint(26, 52), blur=90)

    # северное сияние — только в теме aurora
    if theme["name"] == "aurora":
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for k, col in enumerate([(90, 255, 200), (150, 120, 255)]):
            pts = []
            for x in range(-40, w + 80, 40):
                y = 170 + k * 70 + math.sin(x / 210 + k * 1.7 + seed) * 70
                pts.append((x, y))
            for i in range(len(pts) - 1):
                d.polygon([pts[i], pts[i + 1], (pts[i + 1][0], pts[i + 1][1] + 300),
                           (pts[i][0], pts[i][1] + 300)], fill=col + (30,))
        img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(40)))

    # звёзды для полуночи
    if theme["name"] == "midnight":
        d = ImageDraw.Draw(img)
        for _ in range(60):
            x, y, r = rnd.randint(0, w), rnd.randint(0, int(h * .6)), rnd.choice([1, 1, 2, 3])
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 244, 200, rnd.randint(110, 230)))
    return img


def snow(img, seed, count=90):
    rnd = random.Random(seed * 31 + 5)
    w, h = img.size
    far = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(far)
    for _ in range(count):
        x, y, r = rnd.randint(0, w), rnd.randint(0, h), rnd.choice([2, 2, 3, 4, 5])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(70, 170)))
    img.alpha_composite(far.filter(ImageFilter.GaussianBlur(1.2)))
    # несколько снежинок-звёздочек покрупнее
    d = ImageDraw.Draw(img)
    for _ in range(9):
        cx, cy, r = rnd.randint(20, w - 20), rnd.randint(20, h - 20), rnd.randint(9, 16)
        a = rnd.randint(110, 190)
        for k in range(3):
            ang = k * math.pi / 3 + rnd.random() * .2
            dx, dy = math.cos(ang) * r, math.sin(ang) * r
            d.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=(255, 255, 255, a), width=2)


def garland(img, theme, seed, y0=18, sag=34, anchors=None):
    """Гирлянда через весь верх карточки: провод провисает дугами, на нём светятся лампочки."""
    w, _ = img.size
    rnd = random.Random(seed + 101)
    wire = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(wire)
    anchors = anchors or [0, w * .17, w * .36, w * .55, w * .74, w * .90, w + 10]
    pts = []
    for a, b in zip(anchors, anchors[1:]):
        for i in range(0, 41):
            t = i / 40
            x = a + (b - a) * t
            y = y0 + sag * math.sin(math.pi * t) + 4 * math.sin(x / 90)
            pts.append((x, y))
    d.line(pts, fill=(18, 20, 28, 230), width=4)
    img.alpha_composite(wire)

    cols = theme["bulbs"]
    for i in range(14, len(pts) - 10, 20):
        x, y = pts[i]
        col = cols[(i // 20 + rnd.randint(0, 1)) % len(cols)]
        glow_dot(img, x, y + 18, 17, col, alpha=215, blur=13)
        d2 = ImageDraw.Draw(img)
        d2.rectangle([x - 4, y + 1, x + 4, y + 8], fill=(30, 32, 40, 255))
        d2.ellipse([x - 7, y + 7, x + 7, y + 29], fill=col + (255,))
        d2.ellipse([x - 3, y + 11, x + 1, y + 17], fill=(255, 255, 255, 200))


# ---------------------------------------------------------------- подарки

def _bow(d, cx, cy, s, color):
    d.ellipse([cx - 22 * s, cy - 15 * s, cx - 2 * s, cy + 6 * s], fill=color, outline=(0, 0, 0, 60))
    d.ellipse([cx + 2 * s, cy - 15 * s, cx + 22 * s, cy + 6 * s], fill=color, outline=(0, 0, 0, 60))
    d.ellipse([cx - 6 * s, cy - 8 * s, cx + 6 * s, cy + 6 * s], fill=color, outline=(0, 0, 0, 80))


def gift_box(w, h, body, ribbon, bow=None):
    """Один подарок. Рисуется в 3× и уменьшается — гладкие края."""
    S = 3
    bow = bow or ribbon
    im = Image.new("RGBA", (w * S, (h + 34) * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = 34 * S
    hh = h * S
    lid_h = int(hh * .26)
    dark = _lerp(body, (0, 0, 0), .22)
    d.rounded_rectangle([0, top + lid_h - 4 * S, w * S, top + hh], radius=8 * S, fill=body)
    d.rounded_rectangle([int(w * S * .05), top + lid_h, int(w * S * .95), top + hh],
                        radius=6 * S, fill=body)
    d.rectangle([int(w * S * .05), top + hh - 14 * S, int(w * S * .95), top + hh], fill=dark)
    d.rounded_rectangle([0, top, w * S, top + lid_h], radius=8 * S, fill=_lerp(body, (255, 255, 255), .12))
    rw = int(w * S * .17)
    cx = w * S // 2
    d.rectangle([cx - rw // 2, top + lid_h, cx + rw // 2, top + hh], fill=ribbon)
    d.rectangle([cx - rw // 2, top, cx + rw // 2, top + lid_h], fill=_lerp(ribbon, (255, 255, 255), .15))
    # блик
    d.rounded_rectangle([int(w * S * .1), top + lid_h + 10 * S, int(w * S * .16), top + hh - 26 * S],
                        radius=4 * S, fill=(255, 255, 255, 55))
    _bow(d, cx, top - 4 * S, S * 1.5, bow)
    return im.resize((w, h + 34), Image.LANCZOS)


def gifts(img, x, y_bottom, theme, scale=1.0, flip=False):
    """Стопка из трёх подарков, стоящая на линии y_bottom."""
    c = theme["gifts"]
    specs = [  # (dx, w, h, body, ribbon)
        (0, int(120 * scale), int(86 * scale), c[0], (250, 250, 252)),
        (int(112 * scale), int(96 * scale), int(116 * scale), c[1], theme["gold"]),
        (int(196 * scale), int(78 * scale), int(64 * scale), c[2], (250, 250, 252)),
    ]
    items = []
    for dx, w, h, body, rib in specs:
        items.append((dx, gift_box(w, h, body, rib)))
    total_w = max(dx + g.width for dx, g in items)
    for dx, g in items:
        px = x + (total_w - dx - g.width if flip else dx)
        img.alpha_composite(g, (int(px), int(y_bottom - g.height)))
    return total_w


# ---------------------------------------------------------------- котик

def _pt(cx, cy, r, ang):
    return (cx + r * math.cos(ang), cy + r * math.sin(ang))


_EYE = {"frost": (88, 158, 226), "ruby": (96, 176, 86), "aurora": (96, 196, 232), "midnight": (244, 190, 64)}
_cat_cache = {}


def _dark(c, k=.5):
    return _lerp(c, (24, 14, 28), k)


def _shape(im, S, kind, geom, hi, lo, hi_pos=(.38, .28), outline=None, ow=3):
    """Объёмная фигура: радиальный градиент hi→lo внутри формы + тёмный контур."""
    W, H = im.size
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    if kind == "ellipse":
        md.ellipse(geom, fill=255)
        x0, y0, x1, y1 = geom
    else:
        md.polygon(geom, fill=255)
        xs, ys = [p[0] for p in geom], [p[1] for p in geom]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    x0, y0, x1, y1 = int(x0) - 1, int(y0) - 1, int(x1) + 2, int(y1) + 2
    w, h = x1 - x0, y1 - y0
    if outline:
        big = mask.filter(ImageFilter.GaussianBlur(ow * S)).point(lambda v: 255 if v > 24 else 0)
        im.paste(Image.new("RGBA", (W, H), outline + (255,)), (0, 0), big)
    g = Image.new("RGB", (w, h), lo)
    gd = ImageDraw.Draw(g)
    R = max(w, h) * 1.05
    cx, cy = hi_pos[0] * w, hi_pos[1] * h
    steps = 26
    for i in range(steps):
        t = i / (steps - 1)
        r = R * (1 - t) ** 1.15
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_lerp(lo, hi, t ** 0.9))
    g = g.filter(ImageFilter.GaussianBlur(max(2, S * 2)))
    im.paste(g, (x0, y0), mask.crop((x0, y0, x1, y1)))


def _glossy_eye(im, S, ex, ey, rx, ry, iris, dark_cat):
    d = ImageDraw.Draw(im)
    d.ellipse([ex - rx, ey - ry, ex + rx, ey + ry], fill=(26, 18, 34))
    # радужка
    ir_rx, ir_ry = rx * .82, ry * .84
    _shape(im, S, "ellipse", [ex - ir_rx, ey - ir_ry + ry * .06, ex + ir_rx, ey + ir_ry + ry * .06],
           _lerp(iris, (255, 255, 255), .35), _dark(iris, .35), hi_pos=(.5, .85))
    d = ImageDraw.Draw(im)
    pr = rx * .46
    d.ellipse([ex - pr, ey - pr * 1.25, ex + pr, ey + pr * 1.25], fill=(18, 12, 26))
    # блики
    d.ellipse([ex - rx * .58, ey - ry * .66, ex - rx * .1, ey - ry * .16], fill=(255, 255, 255))
    d.ellipse([ex + rx * .18, ey + ry * .22, ex + rx * .46, ey + ry * .5], fill=(255, 255, 255, 220))
    d.ellipse([ex + rx * .3, ey - ry * .5, ex + rx * .5, ey - ry * .3], fill=(255, 255, 255, 200))


def _fur_trim(im, S, x0, y0, x1, y1):
    """Меховая оторочка колпака: ряд пушистых «шариков» с градиентом."""
    n = 9
    rad = (y1 - y0) * .62
    for i in range(n):
        cx = x0 + (x1 - x0) * (i + .5) / n
        cy = (y0 + y1) / 2 + (S * 2 if i % 2 else -S * 2)
        _shape(im, S, "ellipse", [cx - rad, cy - rad, cx + rad, cy + rad],
               (255, 255, 255), (214, 222, 240), hi_pos=(.4, .3))
    _shape(im, S, "ellipse", [x0, y0 + (y1 - y0) * .12, x1, y1 - (y1 - y0) * .05],
           (255, 255, 255), (222, 228, 244), hi_pos=(.5, .2))


def _pompom(im, S, cx, cy, r):
    for k in range(7):
        a = k * math.pi * 2 / 7
        px, py = cx + math.cos(a) * r * .55, cy + math.sin(a) * r * .55
        rr = r * .6
        _shape(im, S, "ellipse", [px - rr, py - rr, px + rr, py + rr],
               (255, 255, 255), (212, 220, 240))
    _shape(im, S, "ellipse", [cx - r * .8, cy - r * .8, cx + r * .8, cy + r * .8],
           (255, 255, 255), (226, 232, 246))


def cat(theme, width=360, with_paws=True, tilt=0):
    """Милый котик-наклейка: объёмная голова с градиентами, пушистые щёки, глянцевые глаза,
    розовые ушки, колпак/рога/шапка, лапки с подушечками и белая обводка-«стикер»."""
    key = (theme["name"], int(width), with_paws, tilt)
    if key in _cat_cache:
        return _cat_cache[key].copy()

    S = 4
    W, H = 400 * S, 402 * S
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fur, dark_cat = theme["fur"], theme["name"] == "midnight"
    f_hi, f_lo = _lerp(fur, (255, 255, 255), .30), _lerp(fur, (0, 0, 0), .16)
    outline = _dark(fur, .62)
    light_hi, light_lo = _lerp(fur, (255, 255, 255), .78), _lerp(fur, (255, 255, 255), .45)
    pink, pink_d = (255, 176, 190), (236, 120, 150)
    cx, cy = 200 * S, 224 * S
    rx, ry = 148 * S, 118 * S

    # --- уши
    for side in (-1, 1):
        bx = cx + side * 92 * S
        tri = [(bx - side * 66 * S, cy - 34 * S), (bx + side * 18 * S, cy - 152 * S),
               (bx + side * 74 * S, cy - 16 * S)]
        _shape(im, S, "poly", tri, f_hi, f_lo, outline=outline, ow=3)
        inner = [(bx - side * 40 * S, cy - 42 * S), (bx + side * 16 * S, cy - 120 * S),
                 (bx + side * 52 * S, cy - 28 * S)]
        _shape(im, S, "poly", inner, (255, 196, 208) if not dark_cat else (176, 120, 150),
               pink_d if not dark_cat else (112, 70, 100), hi_pos=(.5, .8))

    # --- голова
    _shape(im, S, "ellipse", [cx - rx, cy - ry, cx + rx, cy + ry], f_hi, f_lo,
           hi_pos=(.40, .22), outline=outline, ow=3)

    # --- светлая мордочка (две «подушечки» щёк + подбородок)
    for side in (-1, 1):
        _shape(im, S, "ellipse", [cx + side * 34 * S - 56 * S, cy + 12 * S, cx + side * 34 * S + 56 * S, cy + 96 * S],
               light_hi, light_lo, hi_pos=(.5, .25))
    # --- полоски тэбби
    if theme["name"] in ("frost", "ruby"):
        sc = _lerp(theme["fur2"], fur, .25)
        d = ImageDraw.Draw(im)
        for dx, hh in ((-26, 26), (0, 38), (26, 26)):
            d.rounded_rectangle([cx + dx * S - 6 * S, cy - ry + 8 * S, cx + dx * S + 6 * S, cy - ry + (8 + hh) * S],
                                radius=6 * S, fill=sc)
        for side in (-1, 1):
            for k in range(2):
                yy = cy - 6 * S + k * 20 * S
                d.rounded_rectangle([cx + side * (rx - 6 * S) - (0 if side < 0 else 34 * S), yy,
                                     cx + side * (rx - 6 * S) + (34 * S if side < 0 else 0), yy + 8 * S],
                                    radius=4 * S, fill=sc)

    # --- глаза
    eye = _EYE.get(theme["name"], (90, 150, 220))
    for side in (-1, 1):
        _glossy_eye(im, S, cx + side * 60 * S, cy + 10 * S, 25 * S, 31 * S, eye, dark_cat)
    d = ImageDraw.Draw(im)
    # румянец
    blush = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blush)
    for side in (-1, 1):
        bx = cx + side * 100 * S
        bd.ellipse([bx - 26 * S, cy + 38 * S, bx + 26 * S, cy + 66 * S], fill=(255, 112, 150, 150))
    im.alpha_composite(blush.filter(ImageFilter.GaussianBlur(5 * S)))
    d = ImageDraw.Draw(im)
    # нос-«сердечко» и ротик
    nose = [(cx - 15 * S, cy + 30 * S), (cx + 15 * S, cy + 30 * S), (cx, cy + 47 * S)]
    _shape(im, S, "poly", nose, (255, 190, 204), (234, 112, 142), outline=_dark(pink_d, .35), ow=1)
    d = ImageDraw.Draw(im)
    d.ellipse([cx - 7 * S, cy + 32 * S, cx - 1 * S, cy + 36 * S], fill=(255, 255, 255))
    mc = (112, 64, 84) if not dark_cat else (214, 176, 196)
    d.line([(cx, cy + 47 * S), (cx, cy + 56 * S)], fill=mc, width=3 * S)
    d.arc([cx - 26 * S, cy + 44 * S, cx, cy + 70 * S], 10, 170, fill=mc, width=3 * S)
    d.arc([cx, cy + 44 * S, cx + 26 * S, cy + 70 * S], 10, 170, fill=mc, width=3 * S)
    # усы
    wc = (240, 242, 252) if dark_cat else (255, 255, 255)
    for side in (-1, 1):
        for dy, lift in ((0, -6), (15, 4), (30, 14)):
            x0 = cx + side * 108 * S
            d.line([(x0, cy + (48 + dy) * S), (x0 + side * 58 * S, cy + (44 + dy + lift) * S)],
                   fill=wc, width=2 * S)

    # --- головной убор
    hc = theme["hat_color"]
    hc_hi, hc_lo = _lerp(hc, (255, 255, 255), .28), _dark(hc, .3)
    if theme["hat"] in ("santa", "elf"):
        santa = theme["hat"] == "santa"
        tip_x = cx + (92 if santa else 74) * S
        tip_y = cy - ry - (46 if santa else 78) * S
        cone = [(cx - 118 * S, cy - ry + 40 * S), (cx - 46 * S, cy - ry - 62 * S),
                (tip_x - 10 * S, tip_y + 8 * S), (tip_x + 14 * S, tip_y + 20 * S),
                (cx + 120 * S, cy - ry + 42 * S)]
        _shape(im, S, "poly", cone, hc_hi, hc_lo, outline=_dark(hc, .6), ow=3, hi_pos=(.35, .35))
        _fur_trim(im, S, cx - 132 * S, cy - ry + 14 * S, cx + 134 * S, cy - ry + 58 * S)
        _pompom(im, S, tip_x + 6 * S, tip_y + 10 * S, 22 * S)
        if not santa:
            _shape(im, S, "ellipse", [tip_x - 4 * S, tip_y + 2 * S, tip_x + 16 * S, tip_y + 22 * S],
                   _lerp(theme["gold"], (255, 255, 255), .5), theme["gold"])
    elif theme["hat"] == "antlers":
        for side in (-1, 1):
            bx, by = cx + side * 70 * S, cy - ry + 18 * S
            d = ImageDraw.Draw(im)
            for w_, col in ((18, _dark(hc, .55)), (12, hc)):
                d.line([(bx, by), (bx + side * 24 * S, by - 78 * S)], fill=col, width=w_ * S)
                d.line([(bx + side * 12 * S, by - 36 * S), (bx + side * 56 * S, by - 60 * S)], fill=col, width=(w_ - 3) * S)
                d.line([(bx + side * 22 * S, by - 68 * S), (bx + side * 6 * S, by - 100 * S)], fill=col, width=(w_ - 4) * S)
        _shape(im, S, "ellipse", [cx - 17 * S, cy + 24 * S, cx + 17 * S, cy + 50 * S],
               (255, 120, 120), (200, 36, 52), outline=(120, 20, 32), ow=1)
        d = ImageDraw.Draw(im)
        d.ellipse([cx - 9 * S, cy + 28 * S, cx - 2 * S, cy + 35 * S], fill=(255, 255, 255, 230))
    else:  # шапка-бини с помпоном-звездой
        beanie = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        _shape(beanie, S, "ellipse", [cx - 124 * S, cy - ry - 70 * S, cx + 124 * S, cy - ry + 100 * S],
               hc_hi, hc_lo, outline=_dark(hc, .6), ow=3, hi_pos=(.4, .25))
        cut = Image.new("L", (W, H), 255)
        ImageDraw.Draw(cut).rectangle([0, cy - ry + 36 * S, W, H], fill=0)
        beanie.putalpha(Image.composite(beanie.getchannel("A"), Image.new("L", (W, H), 0), cut))
        im.alpha_composite(beanie)
        _shape(im, S, "ellipse", [cx - 134 * S, cy - ry + 12 * S, cx + 134 * S, cy - ry + 54 * S],
               _lerp(hc, (255, 255, 255), .45), _lerp(hc, (255, 255, 255), .1), outline=_dark(hc, .6), ow=3)
        d = ImageDraw.Draw(im)
        for k in range(-5, 6):
            d.line([(cx + k * 24 * S, cy - ry + 16 * S), (cx + k * 24 * S, cy - ry + 50 * S)],
                   fill=_dark(hc, .25), width=2 * S)
        sx, sy = cx, cy - ry - 66 * S
        star = [_pt(sx, sy, (28 if i % 2 == 0 else 12) * S, -math.pi / 2 + i * math.pi / 5) for i in range(10)]
        _shape(im, S, "poly", star, (255, 244, 170), theme["gold"], outline=_dark(theme["gold"], .6), ow=2)

    # --- лапки с подушечками
    if with_paws:
        for side in (-1, 1):
            px, py = cx + side * 80 * S, cy + ry + 4 * S
            _shape(im, S, "ellipse", [px - 44 * S, py - 36 * S, px + 44 * S, py + 38 * S], f_hi, f_lo,
                   outline=outline, ow=3, hi_pos=(.4, .25))
            _shape(im, S, "ellipse", [px - 22 * S, py - 2 * S, px + 22 * S, py + 28 * S],
                   (255, 190, 204), (236, 128, 156))
            d = ImageDraw.Draw(im)
            for k in (-1, 0, 1):
                tx = px + k * 17 * S
                d.ellipse([tx - 6 * S, py - 20 * S, tx + 6 * S, py - 6 * S], fill=(255, 190, 204))

    # --- шарф у midnight
    if theme["hat"] == "beanie":
        sc = (214, 48, 58)
        _shape(im, S, "poly", [(cx - 112 * S, cy + ry - 36 * S), (cx + 112 * S, cy + ry - 36 * S),
                               (cx + 100 * S, cy + ry + 8 * S), (cx - 100 * S, cy + ry + 8 * S)],
               (255, 110, 110), _dark(sc, .15), outline=_dark(sc, .6), ow=3)
        d = ImageDraw.Draw(im)
        for k in range(-3, 4):
            d.line([(cx + k * 30 * S, cy + ry - 32 * S), (cx + k * 30 * S + 8 * S, cy + ry + 4 * S)],
                   fill=(255, 255, 255, 150), width=5 * S)

    # --- «стикер»: светлая обводка вокруг всего котика + мягкая тень
    alpha = im.getchannel("A")
    halo = alpha.filter(ImageFilter.GaussianBlur(6 * S)).point(lambda v: 255 if v > 18 else 0)
    halo = halo.filter(ImageFilter.GaussianBlur(S * .8))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (W, H), (246, 249, 255, 255)), (0, 0), halo)
    out.alpha_composite(im)
    im = out

    im = im.resize((W // S, H // S), Image.LANCZOS)
    scale = width / im.width
    if scale != 1:
        im = im.resize((width, int(im.height * scale)), Image.LANCZOS)
    if tilt:
        im = im.rotate(tilt, resample=Image.BICUBIC, expand=True)
    _cat_cache[key] = im
    return im.copy()


def paste_cat(img, theme, x, y, width=360, flip=False, tilt=0):
    c = cat(theme, width, tilt=tilt)
    if flip:
        c = c.transpose(Image.FLIP_LEFT_RIGHT)
    # лёгкая тень под котиком
    sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
    sh.putalpha(c.getchannel("A").point(lambda v: int(v * .35)))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(sh, (int(x), int(y) + 8))
    img.alpha_composite(c, (int(x), int(y)))
    return c.size


# ---------------------------------------------------------------- мелкие элементы

def chip(img, x, y, text, fnt, fg, outline, pad=16, height=34, fill=None):
    draw = ImageDraw.Draw(img)
    w = draw.textlength(text, font=fnt) + pad * 2
    rrect_a(img, [x, y, x + w, y + height], height // 2, fill=fill, outline=outline, width=2)
    ImageDraw.Draw(img).text((x + pad, y + (height - fnt.size) / 2 - 2), text, font=fnt, fill=fg)
    return w


def flame(draw, x, y, s=1.0, color=(255, 150, 60)):
    """Маленький огонёк (винстрик)."""
    pts = [(x + 8 * s, y), (x + 15 * s, y + 10 * s), (x + 17 * s, y + 20 * s),
           (x + 8 * s, y + 28 * s), (x - 1 * s, y + 20 * s), (x + 1 * s, y + 10 * s),
           (x + 5 * s, y + 14 * s)]
    draw.polygon(pts, fill=color)
    draw.polygon([(x + 8 * s, y + 14 * s), (x + 12 * s, y + 21 * s), (x + 8 * s, y + 27 * s),
                  (x + 4 * s, y + 21 * s)], fill=(255, 225, 120))


def crown(img, cx, base_y, theme, w=76, h=50, tilt=-14):
    S = 3
    im = Image.new("RGBA", (w * S, h * S + 8 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    g = theme["gold"]
    pts = [(0, h * S), (0, h * S * .35), (w * S * .24, h * S * .68), (w * S * .5, 0),
           (w * S * .76, h * S * .68), (w * S, h * S * .35), (w * S, h * S)]
    d.polygon(pts, fill=g)
    d.rectangle([0, h * S - 6 * S, w * S, h * S + 6 * S], fill=_lerp(g, (0, 0, 0), .12))
    for px, py, col in ((w * S * .5, h * S * .5, (230, 60, 90)), (w * S * .22, h * S * .72, (90, 190, 255)),
                        (w * S * .78, h * S * .72, (90, 190, 255))):
        d.ellipse([px - 6 * S, py - 6 * S, px + 6 * S, py + 6 * S], fill=col)
    im = im.resize((w, h + 8), Image.LANCZOS).rotate(tilt, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(im, (int(cx - im.width / 2), int(base_y - im.height)))


def finish(img, quality=93):
    import io
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality, subsampling=0)
    buf.seek(0)
    return buf


def cat_top(edge_y, width):
    """Y верхнего края картинки котика так, чтобы его лапки лежали на линии edge_y."""
    return edge_y - int(width * 382 / 400) + 20
