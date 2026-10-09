"""Kart + SON KOZ yazılı profil varyasyonları."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw
from render import _font, PALETTES

P = PALETTES["siyah_neon"]
S = 1080
OUT = os.path.dirname(os.path.abspath(__file__))
src = Image.open(os.path.join(OUT, "profil_2_kart.png")).convert("RGB")


def centered(d, text, font, cy, fill):
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    d.text(((S - (r - l)) / 2 - l, cy - (b - t) / 2 - t), text, font=font, fill=fill)


# A) Kart küçülüp yukarı, altında SON KOZ
a = Image.new("RGB", (S, S), P["bg"])
card = src.resize((760, 760), Image.LANCZOS)
a.paste(card, ((S - 760) // 2, 40))
d = ImageDraw.Draw(a)
centered(d, "SON KOZ", _font("bold", 130), 840, P["text"])
a.save(os.path.join(OUT, "profil_4_kart_yazi_alt.png"))

# B) Kart yerinde, yazı kartın üstüne şerit olarak
b = src.copy()
d = ImageDraw.Draw(b)
d.rectangle([0, 470, S, 610], fill=P["bg"])
centered(d, "SON KOZ", _font("bold", 120), 540, P["accent"])
b.save(os.path.join(OUT, "profil_5_kart_serit.png"))

# Önizleme
names = ["profil_2_kart.png", "profil_4_kart_yazi_alt.png", "profil_5_kart_serit.png"]
titles = ["Mevcut", "A) Yazı altta", "B) Yazı şerit"]
sheet = Image.new("RGB", (3 * 380 + 40, 560), "#FAFAFA")
mb = Image.new("L", (340, 340), 0); ImageDraw.Draw(mb).ellipse([0, 0, 339, 339], fill=255)
ms = Image.new("L", (77, 77), 0); ImageDraw.Draw(ms).ellipse([0, 0, 76, 76], fill=255)
sd = ImageDraw.Draw(sheet)
for i, n in enumerate(names):
    im = Image.open(os.path.join(OUT, n)).convert("RGB")
    x = 20 + i * 380
    sheet.paste(im.resize((340, 340), Image.LANCZOS), (x + 20, 20), mb)
    sheet.paste(im.resize((77, 77), Image.LANCZOS), (x + 20, 400), ms)
    sd.text((x + 110, 420), titles[i], font=_font("bold", 22), fill="#262626")
    sd.text((x + 110, 450), "gerçek boyut", font=_font("regular", 20), fill="#737373")
sheet.save(os.path.join(OUT, "profil_yazili_onizleme.png"))
print("ok")
