"""Profil fotoğrafı seçenekleri (1080x1080). Instagram daire şeklinde kırpar."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw
from render import _font, PALETTES

P = PALETTES["siyah_neon"]
S = 1080
OUT = os.path.dirname(os.path.abspath(__file__))


def centered(d, text, font, cy, fill):
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    d.text(((S - (r - l)) / 2 - l, cy - (b - t) / 2 - t), text, font=font, fill=fill)


def card(angle, fill, outline, width=18):
    """Döndürülmüş oyun kartı katmanı."""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w, h = 420, 600
    box = [(S - w) / 2, (S - h) / 2, (S + w) / 2, (S + h) / 2]
    d.rounded_rectangle(box, radius=48, fill=fill, outline=outline, width=width)
    return layer.rotate(angle, resample=Image.BICUBIC, center=(S / 2, S / 2))


# 1) SK monogram
im = Image.new("RGB", (S, S), P["bg"])
d = ImageDraw.Draw(im)
centered(d, "SK", _font("bold", 460), S / 2 - 10, P["accent"])
d.rectangle([S / 2 - 120, 790, S / 2 + 120, 812], fill=P["text"])
im.save(os.path.join(OUT, "profil_1_monogram.png"))

# 2) Kart yelpazesi, öndeki kart neon ve üzerinde K
im = Image.new("RGBA", (S, S), P["bg"])
im.alpha_composite(card(18, "#1E1E1E", "#3A3A3A"))
im.alpha_composite(card(8, "#262626", "#555555"))
front = card(-6, P["accent"], P["accent"], 0)
im.alpha_composite(front)
txt = Image.new("RGBA", (S, S), (0, 0, 0, 0))
centered(ImageDraw.Draw(txt), "K", _font("bold", 400), S / 2, P["bg"])
im.alpha_composite(txt.rotate(-6, resample=Image.BICUBIC, center=(S / 2, S / 2)))
im.convert("RGB").save(os.path.join(OUT, "profil_2_kart.png"))

# 3) Yazı: SON / KOZ
im = Image.new("RGB", (S, S), P["bg"])
d = ImageDraw.Draw(im)
centered(d, "SON", _font("bold", 250), S / 2 - 140, P["text"])
centered(d, "KOZ", _font("bold", 250), S / 2 + 140, P["accent"])
im.save(os.path.join(OUT, "profil_3_yazi.png"))

# Önizleme: büyük daire + Instagram'daki küçük boyut
names = ["profil_1_monogram.png", "profil_2_kart.png", "profil_3_yazi.png"]
sheet = Image.new("RGB", (3 * 380 + 40, 560), "#FAFAFA")
mask_big = Image.new("L", (340, 340), 0); ImageDraw.Draw(mask_big).ellipse([0, 0, 339, 339], fill=255)
mask_sm = Image.new("L", (77, 77), 0); ImageDraw.Draw(mask_sm).ellipse([0, 0, 76, 76], fill=255)
sd = ImageDraw.Draw(sheet)
for i, n in enumerate(names):
    src = Image.open(os.path.join(OUT, n)).convert("RGB")
    x = 20 + i * 380
    sheet.paste(src.resize((340, 340), Image.LANCZOS), (x + 20, 20), mask_big)
    sheet.paste(src.resize((77, 77), Image.LANCZOS), (x + 20, 400), mask_sm)
    sd.text((x + 110, 420), f"{i + 1}) gerçek boyut", font=_font("bold", 22), fill="#262626")
    sd.text((x + 110, 450), "@sonkozx", font=_font("regular", 20), fill="#737373")
sheet.save(os.path.join(OUT, "profil_onizleme.png"))
print("ok")
