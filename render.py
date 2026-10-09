"""Son Koz — karusel slayt üretici (1080x1350 PNG).

Metin içinde *kelime* yazılırsa o kelime vurgu rengiyle çizilir.
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
MARGIN = 96
BRAND = "Son Koz"
HANDLE = "@sonkozx"
DEFAULT_PALETTE = "siyah_neon"

PALETTES = {
    "gece_altin":     {"bg": "#0E0E10", "text": "#F4F1EA", "accent": "#F5C542", "muted": "#8A877F"},
    "lacivert_mercan": {"bg": "#0B1D3A", "text": "#FFFFFF", "accent": "#FF6B5B", "muted": "#8FA0BD"},
    "krem_siyah":     {"bg": "#F3EDE2", "text": "#111111", "accent": "#E4572E", "muted": "#8C8478"},
    "siyah_neon":     {"bg": "#121212", "text": "#FFFFFF", "accent": "#C6FF00", "muted": "#7A7A7A"},
}

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")


def _font(weight, size):
    """Proje içindeki fontu, yoksa sistem fontunu kullan."""
    candidates = {
        "bold": [os.path.join(FONT_DIR, "Montserrat-ExtraBold.ttf"),
                 "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
        "regular": [os.path.join(FONT_DIR, "Montserrat-Medium.ttf"),
                    "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    }[weight]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    raise FileNotFoundError(f"{weight} font bulunamadı")


def _tokens(text):
    """'Bugün *başla* artık' -> [('Bugün', False), ('başla', True), ('artık', False)]"""
    out, on = [], False
    for word in text.split():
        if word.startswith("*"):
            on = True
        hl = on
        if word.rstrip(".,!?:;…").endswith("*"):
            on = False
        out.append((word.replace("*", ""), hl))
    return out


def _wrap(draw, text, font, max_w):
    lines, line = [], []
    space = draw.textlength(" ", font=font)
    for paragraph in text.split("\n"):
        line, width = [], 0
        for word, hl in _tokens(paragraph):
            ww = draw.textlength(word, font=font)
            if line and width + space + ww > max_w:
                lines.append(line)
                line, width = [], 0
            width += (space if line else 0) + ww
            line.append((word, hl))
        lines.append(line)
    return lines


def _fit(draw, text, weight, max_w, max_h, start, minimum, spacing):
    """Metni kutuya sığacak en büyük font boyutunu bul."""
    size = start
    while size > minimum:
        font = _font(weight, size)
        # tek bir uzun kelime bile satıra sığmalı
        if max(draw.textlength(w, font=font) for w in text.replace("*", "").split()) <= max_w:
            lines = _wrap(draw, text, font, max_w)
            if len(lines) * size * spacing <= max_h:
                return font, lines, size
        size -= 4
    font = _font(weight, minimum)
    return font, _wrap(draw, text, font, max_w), minimum


def _draw_lines(draw, lines, font, size, x, y, pal, spacing):
    space = draw.textlength(" ", font=font)
    for line in lines:
        cx = x
        for word, hl in line:
            draw.text((cx, y), word, font=font, fill=pal["accent"] if hl else pal["text"])
            cx += draw.textlength(word, font=font) + space
        y += size * spacing
    return y


def render_slide(slide, palette, idx, total, out_path):
    pal = PALETTES[palette] if isinstance(palette, str) else palette
    img = Image.new("RGB", (W, H), pal["bg"])
    d = ImageDraw.Draw(img)
    max_w = W - 2 * MARGIN
    kind = slide.get("type", "body")

    # üst bant: marka + sayfa
    d.text((MARGIN, 80), HANDLE, font=_font("bold", 30), fill=pal["muted"])
    page = f"{idx}/{total}"
    pf = _font("bold", 30)
    d.text((W - MARGIN - d.textlength(page, font=pf), 80), page, font=pf, fill=pal["muted"])

    if kind == "hook":
        d.rectangle([MARGIN, 300, MARGIN + 120, 314], fill=pal["accent"])
        font, lines, size = _fit(d, slide["text"], "bold", max_w, 680, 118, 64, 1.12)
        block_h = len(lines) * size * 1.12
        y = max(380, (H - block_h) / 2)
        _draw_lines(d, lines, font, size, MARGIN, y, pal, 1.12)
        sf = _font("bold", 36)
        d.text((MARGIN, H - 150), "Kaydır  →", font=sf, fill=pal["accent"])

    elif kind == "cta":
        font, lines, size = _fit(d, slide["text"], "bold", max_w, 560, 100, 56, 1.15)
        y = 400
        spacing_cta = 1.15
        y = _draw_lines(d, lines, font, size, MARGIN, y, pal, spacing_cta)
        y += 60
        d.rectangle([MARGIN, y, MARGIN + 120, y + 14], fill=pal["accent"])
        cf = _font("regular", 40)
        cta = slide.get("cta", f"Kaydet. Yarın tekrar oku.\nTakip et: {HANDLE}")
        for i, line in enumerate(cta.split("\n")):
            d.text((MARGIN, y + 60 + i * 60), line, font=cf, fill=pal["text"] if i == 0 else pal["accent"])

    else:  # body
        nf = _font("bold", 170)
        d.text((MARGIN, 220), f"{idx - 1:02d}", font=nf, fill=pal["accent"])
        y = 500
        if slide.get("title"):
            tf, tlines, tsize = _fit(d, slide["title"], "bold", max_w, 300, 84, 52, 1.15)
            y = _draw_lines(d, tlines, tf, tsize, MARGIN, y, pal, 1.15) + 50
        font, lines, size = _fit(d, slide["text"], "regular", max_w, H - y - 160, 56, 34, 1.4)
        _draw_lines(d, lines, font, size, MARGIN, y, {**pal, "text": pal["text"]}, 1.4)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    if out_path.lower().endswith((".jpg", ".jpeg")):  # Instagram API yalnızca JPEG kabul ediyor
        img.save(out_path, "JPEG", quality=92, optimize=True)
    else:
        img.save(out_path, "PNG", optimize=True)
    return out_path


def render_carousel(post, palette, out_dir, ext="png"):
    slides = post["slides"]
    return [render_slide(s, palette, i + 1, len(slides), os.path.join(out_dir, f"{i + 1}.{ext}"))
            for i, s in enumerate(slides)]


# ---------- Story (1080x1920) ----------

SW, SH = 1080, 1920
STORY_LABELS = {"yeni": "YENİ KARUSEL", "ipucu": "MİNİ İPUCU", "gorev": "HAFTANIN GÖREVİ",
                "aksam": "BU AKŞAM 20:30", "ozet": "BU HAFTA", "tokat": None}
STORY_FOOTERS = {"yeni": "Profile git, kaydır  →", "aksam": "Bildirimleri açmayı unutma.",
                 "gorev": "Yaptıysan story'de paylaş,\n" + HANDLE + " etiketle.",
                 "ozet": "Kaçırdıysan profile git  →", "ipucu": "Kaydet. Bugün uygula.", "tokat": None}


def render_story(kind, data, out_path, palette=DEFAULT_PALETTE):
    """Story görseli. Instagram arayüzü üst ~250 ve alt ~350 pikseli kapatır, oralara yazı koyma."""
    pal = PALETTES[palette]
    img = Image.new("RGB", (SW, SH), pal["bg"])
    d = ImageDraw.Draw(img)
    max_w = SW - 2 * MARGIN
    y = 380

    label = STORY_LABELS[kind]
    if label:
        lf = _font("bold", 38)
        l, t, r, b = d.textbbox((0, 0), label, font=lf)
        d.rounded_rectangle([MARGIN, y, MARGIN + (r - l) + 60, y + 84], radius=42, fill=pal["accent"])
        d.text((MARGIN + 30 - l, y + 42 - (b - t) / 2 - t), label, font=lf, fill=pal["bg"])
        y += 170

    bottom = SH - 560  # alt bilgi bloğunun başladığı yer
    if kind == "ozet":
        nf, tf = _font("bold", 48), _font("regular", 46)
        for i, item in enumerate(data["items"], 1):
            d.text((MARGIN, y), f"{i:02d}", font=nf, fill=pal["accent"])
            lines = _wrap(d, item.replace("*", ""), tf, max_w - 120)
            y = _draw_lines(d, [[(w, False) for w, _ in ln] for ln in lines], tf, 46, MARGIN + 120, y + 2,
                            pal, 1.3) + 34
    elif kind == "ipucu":
        tf, tl, ts = _fit(d, data["title"], "bold", max_w, 300, 96, 56, 1.15)
        y = _draw_lines(d, tl, tf, ts, MARGIN, y, pal, 1.15) + 50
        bf, bl, bs = _fit(d, data["text"], "regular", max_w, bottom - y - 40, 58, 38, 1.4)
        _draw_lines(d, bl, bf, bs, MARGIN, y, pal, 1.4)
    else:
        font, lines, size = _fit(d, data["text"], "bold", max_w, bottom - y - 40, 120, 60, 1.12)
        block = len(lines) * size * 1.12
        if kind == "tokat":  # tek cümle ortada dursun
            d.rectangle([MARGIN, (SH - block) / 2 - 90, MARGIN + 120, (SH - block) / 2 - 76], fill=pal["accent"])
            y = (SH - block) / 2
        _draw_lines(d, lines, font, size, MARGIN, y, pal, 1.12)

    footer = STORY_FOOTERS[kind]
    if footer:
        ff = _font("bold", 44)
        for i, line in enumerate(footer.split("\n")):
            d.text((MARGIN, bottom + 40 + i * 60), line, font=ff, fill=pal["accent"] if i == 0 else pal["text"])
    hf = _font("bold", 34)
    d.text((MARGIN, SH - 380), HANDLE, font=hf, fill=pal["muted"])

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "JPEG", quality=92, optimize=True)
    return out_path
