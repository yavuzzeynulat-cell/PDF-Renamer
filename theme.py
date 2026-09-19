"""Shared 'frosted glass' visual toolkit (colors, fonts, PIL drawing helpers).

Used by both the design preview (gui_preview.py) and the real app (gui.py) so
the look stays consistent in one place.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# -- palette (icy / frosted) ------------------------------------------------
GRAD_TOP = (180, 214, 255)
GRAD_BOTTOM = (232, 244, 255)
INK = "#13283F"
SLATE = "#5B7186"
MUTED = "#9AACBE"
ACCENT = (45, 127, 249)
ACCENT_HEX = "#2D7FF9"
CARD_FILL = (255, 255, 255, 155)
CARD_BORDER = (255, 255, 255, 215)

SEGOE = ["C:/Windows/Fonts/segoeui.ttf", "segoeui.ttf"]
SEGOE_SB = ["C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/segoeuib.ttf", "segoeui.ttf"]


def font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def tkfont(size, weight=None):
    if weight == "semibold":
        return ("Segoe UI Semibold", size)
    if weight == "bold":
        return ("Segoe UI", size, "bold")
    return ("Segoe UI", size)


def make_background(w, h):
    """Buzlu mavi arka plan.

    Iki kalite sorunu vardi ve ikisi de mavi alanlarda goze batiyordu:
      1) Degrade 8-bit adimlarla uretiliyordu -> genis mavi yuzeyde bantlanma
         (kullanicinin "pikselli" dedigi sey).
      2) Gorsel bir kez uretilip pencere boyutuna GERDIRILIYORDU; buyutme
         degradeyi ve isik lekelerini kabalastiriyordu.
    Cozum: degrade her boyutta yeniden ve yuksek kalitede uretilir, uzerine
    gozle gorulmeyen ince bir gurultu eklenir -- gurultu bant siniriini kirar,
    goz duz bir gecis gorur (standart "dither" yontemi).
    """
    top = Image.new("RGB", (w, h), GRAD_TOP)
    bottom = Image.new("RGB", (w, h), GRAD_BOTTOM)
    # 256x256'lik hazir degradeyi yuksek kaliteli olcekleme ile buyutuyoruz:
    # piksel piksel donguden hem daha duzgun hem cok daha hizli.
    mask = Image.linear_gradient("L").resize((w, h), Image.LANCZOS)
    base = Image.composite(bottom, top, mask).convert("RGBA")

    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-120, -160, 320, 240], fill=(255, 255, 255, 130))
    gd.ellipse([w - 320, h - 280, w + 140, h + 120], fill=(120, 180, 255, 95))
    glow = glow.filter(ImageFilter.GaussianBlur(65))
    out = Image.alpha_composite(base, glow)
    return _dither(out)


def _dither(img):
    """Bantlanmayi kiran, fark edilmeyecek kadar hafif gurultu (+-1 ton)."""
    noise = Image.effect_noise(img.size, 6).convert("L")
    grain = Image.merge("RGBA", (noise, noise, noise,
                                 Image.new("L", img.size, 10)))
    return Image.alpha_composite(img, grain)


# PIL'in cizim fonksiyonlari kenar YUMUSATMASI yapmaz: yuvarlak bir kosede
# piksel ya tam dolu ya bos olur, bu da mavi dugmelerde merdiven basamagi
# ("pikselli") gorunumu verir. Cozum supersampling: sekli SS kat buyuk cizip
# yuksek kaliteli olceklemeyle kucultuyoruz -- ara tonlar boyle olusuyor.
SS = 4


def _shrink(img, size):
    return img.resize(size, Image.LANCZOS)


def rounded_rect(size, radius, fill, border=None, border_w=0):
    w, h = size
    big = (w * SS, h * SS)
    img = Image.new("RGBA", big, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big[0] - 1, big[1] - 1], radius=radius * SS,
                        fill=fill, outline=border, width=border_w * SS)
    return _shrink(img, (w, h))


def card_with_shadow(size, radius, pad=32):
    w, h = size
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([pad, pad + 8, pad + w, pad + h + 8], radius=radius,
                         fill=(20, 50, 90, 85))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.alpha_composite(rounded_rect((w, h), radius, CARD_FILL, CARD_BORDER, 2),
                           (pad, pad))
    return canvas, pad


def pill(text, fnt, fg, bg, pad_x=12, pad_y=5, radius=12):
    tmp = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    b = tmp.textbbox((0, 0), text, font=fnt)
    tw, th = b[2] - b[0], b[3] - b[1]
    w, h = tw + pad_x * 2, th + pad_y * 2
    img = rounded_rect((w, h), radius, bg)
    ImageDraw.Draw(img).text((pad_x - b[0], pad_y - b[1]), text, font=fnt, fill=fg)
    return img


def button_image(w, h, text, kind="accent"):
    radius = h // 2
    if kind == "accent":
        fill, fg, border = ACCENT + (255,), (255, 255, 255, 255), None
    elif kind == "ghost":
        fill, fg, border = (255, 255, 255, 95), ACCENT + (255,), ACCENT + (170,)
    elif kind == "disabled":
        fill, fg, border = (210, 220, 232, 200), (150, 165, 182, 255), None
    else:  # soft
        fill, fg, border = (255, 255, 255, 170), (19, 40, 63, 255), (185, 205, 225, 220)
    img = rounded_rect((w, h), radius, fill, border, 2 if border else 0)
    d = ImageDraw.Draw(img)
    f = font(SEGOE_SB, 14)
    b = d.textbbox((0, 0), text, font=f)
    tw, th = b[2] - b[0], b[3] - b[1]
    d.text(((w - tw) / 2 - b[0], (h - th) / 2 - b[1]), text, font=f, fill=fg)
    return img


def toggle_image(on=True):
    w, h = 42, 24
    track = ACCENT + (255,) if on else (190, 204, 218, 255)
    big = (w * SS, h * SS)
    img = Image.new("RGBA", big, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big[0] - 1, big[1] - 1], radius=(h // 2) * SS,
                        fill=track)
    r = (h - 8) * SS
    cx = (w - 4) * SS - r if on else 4 * SS
    d.ellipse([cx, 4 * SS, cx + r, 4 * SS + r], fill=(255, 255, 255, 255))
    return _shrink(img, (w, h))


def splash_image(w, h, title, subtitle):
    """A self-contained frosted splash with centered title + subtitle.

    Tek temiz yuzey: ana pencereyle ayni dil (ic ice cerceve / kart yok).
    """
    bg = make_background(w, h)
    d = ImageDraw.Draw(bg)
    tf = font(SEGOE_SB, 30)
    sf = font(SEGOE, 14)
    tb = d.textbbox((0, 0), title, font=tf)
    d.text(((w - (tb[2] - tb[0])) / 2 - tb[0], h * 0.34), title, font=tf, fill=INK)
    sb = d.textbbox((0, 0), subtitle, font=sf)
    d.text(((w - (sb[2] - sb[0])) / 2 - sb[0], h * 0.56), subtitle, font=sf,
           fill=ACCENT_HEX)
    # yuvarlak koseler: disari saydam (kare gorunumu giderir)
    mask = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w * SS - 1, h * SS - 1], radius=26 * SS, fill=255)
    mask = _shrink(mask, (w, h))
    bg.putalpha(mask)
    return bg
