"""Son Koz — vurucu reels üretici (1080x1920, 30 fps MP4, ~12 sn).

Kaydırmayı durdurmak için:
  * ilk karede kanca zaten ekranda (boş açılış yok),
  * dev yazı, her satır "çarparak" gelir + ekran sarsılır + bas vuruşu,
  * vurgulu kelimeler neon blok üstünde siyah (ters kontrast),
  * sahneler kısa (madde başına ~2 sn), geçişte neon flaş + whoosh,
  * kumlu doku ve hafif neon ışık; düz siyah ekran gibi durmaz.

    python reels.py 1            # 1 numaralı fikir -> samples/reels_0001.mp4
"""
import glob
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw

from render import PALETTES, DEFAULT_PALETTE, HANDLE, _font, _tokens

W, H, FPS, SR = 1080, 1920, 30, 44100
MARGIN = 90
MAX_W = W - MARGIN - 160          # sağdaki beğeni/yorum ikonlarına çarpmasın
TOP, BOTTOM = 360, 1420           # Reels arayüzünün kapatmadığı alan

LINE_GAP = 0.3                    # satırların arka arkaya çarpma aralığı (sn)
SLAM = 4                          # çarpma animasyonu (kare)
SHAKE = 4                         # sarsıntı (kare)
FLASH = 3                         # sahne geçişi flaşı (kare)


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


# ---------- yazı ----------

def _lines(d, text, font, max_w):
    """Kelimeleri satırlara böl; cümle sonunda (. ! ?) her zaman yeni satır."""
    lines, line, width = [], [], 0
    space = d.textlength(" ", font=font)
    for word, hl in _tokens(text):
        ww = d.textlength(word, font=font)
        if line and width + space + ww > max_w:
            lines.append(line)
            line, width = [], 0
        width += (space if line else 0) + ww
        line.append((word, hl))
        if word[-1] in ".!?…":
            lines.append(line)
            line, width = [], 0
    if line:
        lines.append(line)
    return lines


def _fit_lines(d, texts, max_h, start=168, minimum=54):
    """Sahnedeki tüm metinler için ortak, sığan en büyük font."""
    size = start
    while True:
        font = _font("bold", size)
        too_wide = any(d.textlength(w, font=font) > MAX_W
                       for t in texts for w in t.replace("*", "").split())
        groups = [_lines(d, t, font, MAX_W) for t in texts]
        n = sum(len(g) for g in groups)
        if (not too_wide and n * size * 1.34 <= max_h) or size <= minimum:
            return font, size, groups
        size -= 6


def _line_img(line, font, size, pal):
    """Bir satırı şeffaf görsele çiz; vurgulu kelimeler neon blok üstünde siyah."""
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    space = d.textlength(" ", font=font)
    pad = int(size * 0.12)
    # kutu, aksanlı büyük harflerin (İ Ğ Ü) tepesinden alt uzantıların (ğ y g ç ş) dibine kadar
    top, bottom = font.getbbox("HİĞÜÇŞgyğçş")[1::2]
    box_top, box_bot = top - pad * 0.6, bottom + pad * 0.6
    width = int(sum(d.textlength(w, font=font) for w, _ in line) + space * (len(line) - 1)) + 2 * pad
    img = Image.new("RGBA", (width, int(box_bot + pad)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for i, (word, hl) in enumerate(line):
        ww = d.textlength(word, font=font)
        if hl:
            nxt_hl = i + 1 < len(line) and line[i + 1][1]
            d.rectangle([x - pad, box_top, x + ww + (space if nxt_hl else pad), box_bot], fill=pal["accent"])
            d.text((x, 0), word, font=font, fill=pal["bg"])
        else:
            d.text((x, 0), word, font=font, fill=pal["text"])
        x += ww + space
    return img


# ---------- sahneler ----------

def build_scenes(post, pal):
    d = ImageDraw.Draw(Image.new("RGB", (W, H)))
    slides = post["slides"]
    bodies = [s for s in slides if s.get("type") == "body"]
    scenes = []

    def scene(texts, label=None, hold=1.0, first_at=0.0, extra=None, gap=LINE_GAP):
        extra_h = 40 + 110 * len(extra) if extra else 0   # alttaki KAYDET / takip satırları
        font, size, groups = _fit_lines(d, texts, BOTTOM - TOP - (160 if label else 0) - extra_h)
        rows = [line for g in groups for line in g]
        imgs = [_line_img(r, font, size, pal) for r in rows]
        block = len(rows) * size * 1.34
        y = (TOP + BOTTOM) / 2 - (block + extra_h) / 2 + (60 if label else 0)
        items = []
        for i, im in enumerate(imgs):
            items.append({"img": im, "xy": (MARGIN - int(size * 0.12), int(y)), "t": first_at + i * gap})
            y += size * 1.34
        last = items[-1]["t"]
        if extra:
            for j, (im, gap) in enumerate(extra):
                last += gap
                items.append({"img": im, "xy": (MARGIN, int(y + 40 + j * 110)), "t": last})
        scenes.append({"items": items, "label": label,
                       "label_y": int((TOP + BOTTOM) / 2 - block / 2 - 70),
                       "dur": last + hold})

    # kanca: cümle cümle ayrı ekran, daha büyük yazı; ilk satır 0. karede tam görünür
    parts = re.split(r"(?<=[.!?…*])\s+(?=[A-ZÇĞİÖŞÜ*])", slides[0]["text"])
    for j, part in enumerate(parts):
        scene([part], hold=0.55 if j < len(parts) - 1 else 0.75,
              first_at=-SLAM / FPS if j == 0 else 0.0, gap=0.22)
    for i, s in enumerate(bodies, 1):
        scene([s.get("title") or s["text"]], label=f"{i}/{len(bodies)}", hold=0.75)
    sub = _font("bold", 58)
    extra = [(_line_img([("KAYDET.", True)], sub, 58, pal), 0.35),
             (_line_img([(f"Takip et {HANDLE}", False)], _font("regular", 50), 50, pal), 0.25)]
    scene([slides[-1]["text"]], hold=1.3, extra=extra)
    return scenes


def _grain(seed):
    rng = np.random.default_rng(seed)
    n = rng.normal(0, 7, (H // 2, W // 2)).clip(-20, 20)
    return np.kron(n, np.ones((2, 2))).astype(np.int16)[..., None]


def _glow(pal):
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W * 0.3) / (W * 0.9)) ** 2 + ((yy - H * 0.45) / (H * 0.55)) ** 2)
    g = np.clip(1 - r, 0, 1) ** 2 * 0.07
    return (np.array(_hex(pal["accent"])) * g[..., None]).astype(np.int16)


def render_frames(scenes, pal, total):
    bg = np.array(_hex(pal["bg"]), dtype=np.int16)
    base = bg + _glow(pal)
    grains = [_grain(s) for s in range(4)]
    accent = _hex(pal["accent"])
    hf, lf = _font("bold", 32), _font("bold", 44)
    rng = random.Random(7)
    t_all = 0.0
    for si, sc in enumerate(scenes):
        for f in range(round(sc["dur"] * FPS)):
            local = f / FPS
            arr = np.clip(base + grains[f % 4], 0, 255).astype(np.uint8)
            canvas = Image.fromarray(arr, "RGB")
            d = ImageDraw.Draw(canvas)

            # sarsıntı: en son çarpan satırdan sonraki birkaç kare
            since = min([(local - it["t"]) * FPS for it in sc["items"] if local >= it["t"]], default=99)
            k = max(0.0, 1 - since / SHAKE) if since >= SLAM - 1 else 0
            ox, oy = (rng.randint(-14, 14) * k, rng.randint(-14, 14) * k) if k else (0, 0)

            d.text((MARGIN, 230), HANDLE, font=hf, fill=_hex(pal["muted"]))
            d.rectangle([MARGIN, 285, W - MARGIN, 290], fill=(45, 45, 45))
            d.rectangle([MARGIN, 285, MARGIN + (W - 2 * MARGIN) * (t_all + local) / total, 290], fill=accent)
            if sc["label"]:
                d.text((MARGIN + ox, sc["label_y"] + oy), sc["label"], font=lf, fill=accent)

            for it in sc["items"]:
                p = (local - it["t"]) * FPS / SLAM
                if p < 0:
                    continue
                e = _ease(p)
                scale = 1.35 - 0.35 * e
                im = it["img"]
                if scale != 1:
                    im = im.resize((int(im.width * scale), int(im.height * scale)), Image.BILINEAR)
                if e < 1:
                    a = im.getchannel("A").point(lambda v, e=e: int(v * min(1, e * 1.6)))
                    im.putalpha(a)
                x, y = it["xy"]
                y -= (im.height - it["img"].height) // 2
                canvas.paste(im, (int(x + ox), int(y + oy)), im)

            if si and f < FLASH:                         # sahne geçişi neon flaş
                fl = Image.new("RGB", (W, H), accent)
                canvas = Image.blend(canvas, fl, 0.55 * (1 - f / FLASH))
            yield canvas.tobytes()
        t_all += sc["dur"]


# ---------- ses ----------

def _kick(n):
    t = np.arange(n) / SR
    freq = 45 + 110 * np.exp(-t * 35)
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 9)


def _whoosh(n, seed=0):
    noise = np.random.default_rng(seed).normal(0, 1, n)
    noise = np.convolve(noise, np.ones(24) / 24, mode="same")
    env = np.linspace(0, 1, n) ** 2.5
    return noise * env * 2.2


MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")


def pick_track(pid):
    """Parçalar karışık sırayla döner; art arda gelen reels'lerde aynı parça çıkmaz."""
    tracks = sorted(glob.glob(os.path.join(MUSIC_DIR, "*.mp3")))
    if not tracks:
        return None
    random.Random(2026).shuffle(tracks)
    return tracks[pid % len(tracks)]


def load_music(path, total):
    """Parçanın video süresi kadar en enerjik bölümünü (stereo, -1..1) döndürür."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).astype(np.float64)
    n = int(total * SR)
    if len(audio) <= n:
        audio = np.tile(audio, (n // len(audio) + 1, 1))
        return audio[:n]
    hop = SR // 4                                     # çeyrek saniyelik adımlarla en yüksek enerjili pencere
    energy = np.sqrt((audio ** 2).mean(axis=1))
    blocks = energy[:len(energy) // hop * hop].reshape(-1, hop).mean(axis=1)
    win = max(1, n // hop)
    sums = np.convolve(blocks, np.ones(win), mode="valid")
    start = int(np.argmax(sums)) * hop
    seg = audio[start:start + n]
    rms = np.sqrt((seg ** 2).mean()) or 1.0
    return seg * (0.22 / rms)                         # parçalar arası ses seviyesi eşit olsun


def build_audio(scenes, total, path, music=None):
    n = int(total * SR) + SR
    out = np.zeros(n)
    t = np.arange(n) / SR
    if music is None:                                 # müzik yoksa alttan gelen uğultu
        drone = 0.10 * np.sin(2 * np.pi * 55 * t) + 0.05 * np.sin(2 * np.pi * 82.4 * t)
        out += drone * np.clip(t / 0.4, 0, 1)
    k = _kick(int(0.45 * SR))
    kick_gain = 0.9 if music is None else 0.55        # müzikle birlikte vuruşlar daha kısık
    start = 0.0
    for si, sc in enumerate(scenes):
        if si:
            w = _whoosh(int(0.35 * SR), si)
            a = int(start * SR) - len(w)
            out[a:a + len(w)] += w * 0.35
        for it in sc["items"]:
            a = int(max(0.0, start + it["t"] + SLAM / FPS * 0.6) * SR)
            out[a:a + len(k)] += k[:n - a] * kick_gain
        start += sc["dur"]
    m = int(total * SR)
    stereo = np.repeat(out[:m, None], 2, axis=1)
    if music is not None:
        stereo += music[:m] * np.clip(t[:m] / 0.05, 0, 1)[:, None]
    stereo *= np.clip((total - t[:m]) / 0.3, 0, 1)[:, None]   # sonda kısık bitiş
    pcm = (np.tanh(stereo * 1.4) * 0.85 * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def render_reel(post, out_path, palette=DEFAULT_PALETTE, music="auto"):
    """music: 'auto' = music/ klasöründen sıradaki parça, bir dosya yolu ya da None (yalnızca efekt sesleri)."""
    pal = PALETTES[palette]
    scenes = build_scenes(post, pal)
    total = sum(s["dur"] for s in scenes)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    track = pick_track(post["id"]) if music == "auto" else music
    wav = os.path.join(tempfile.mkdtemp(), "ses.wav")
    build_audio(scenes, total, wav, load_music(track, total) if track else None)
    if track:
        print(f"Müzik: {os.path.basename(track)}")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
           "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for frame in render_frames(scenes, pal, total):
        proc.stdin.write(frame)
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError("ffmpeg hata verdi")
    cover_ms = int((scenes[0]["dur"] - 0.1) * 1000)   # kapak: kancanın ilk cümlesi tam ekrandayken
    return out_path, total, cover_ms


def find_post(pid):
    for f in glob.glob(os.path.join(os.path.dirname(__file__), "content", "*.json")):
        for p in json.load(open(f, encoding="utf-8")):
            if p["id"] == pid:
                return p
    raise KeyError(pid)


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    path, secs, _ = render_reel(find_post(pid), os.path.join(os.path.dirname(__file__) or ".",
                                                          "samples", f"reels_{pid:04d}_v2.mp4"))
    print(f"{path}  ({secs:.1f} sn)")
