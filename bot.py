"""Son Koz Instagram botu (@sonkozx).

İki bağlantı yöntemi var (BACKEND ortam değişkeni):
  instagram (varsayılan)  Instagram ile giriş: graph.instagram.com + Instagram token'ı. Facebook sayfası ve
                          işletme portföyü gerekmez. Görseller repodaki 'media' dalından herkese açık adres alır.
  meta                    DOKU botuyla aynı: graph.facebook.com + sistem kullanıcısı token'ı, görseller reklam
                          hesabının görsel kütüphanesinden yayınlanır.

Komutlar:
  python bot.py post [--dry-run|--dene] [--id N]     sıradaki karuseli (ve "yeni karusel" story'sini) yayınla
  python bot.py story [--dry-run|--dene] [--kind K]  günün story'sini yayınla
    --dry-run  yalnızca çizer, Instagram'a bağlanmaz
    --dene     her şeyi yapar (yükleme, izin kontrolü, Instagram'ın işlemesi) ama YAYINLAMAZ, sırayı ilerletmez
  python bot.py baglanti                      token'ın hangi hesabı gördüğüne bak (yalnızca okur)
  python bot.py refresh-token                 Instagram token'ını yenile (instagram yöntemi)
  python bot.py status                        kaç gönderi kaldığını göster

Ortam değişkenleri:
  instagram: IG_ACCESS_TOKEN, GITHUB_TOKEN, GITHUB_REPOSITORY (Actions verir), isteğe bağlı MEDIA_REPO + MEDIA_TOKEN
             (görselleri ayrı bir herkese açık repoya koymak için), GH_PAT (token değişirse secret'ı güncellemek için)
  meta:      META_TOKEN, META_AD_ACCOUNT, IG_USERNAME
  ortak:     STORIES="0" story'leri kapatır
"""
import argparse
import base64
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests

from render import DEFAULT_PALETTE, HANDLE, render_carousel, render_story
from validate import load_all

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(ROOT, "state.json")
TASKS_PATH = os.path.join(ROOT, "content", "stories", "gorevler.json")
GIZLI = os.path.join(os.path.expanduser("~"), "Desktop", "sablonpazarı", ".gizli")

BACKEND = os.environ.get("BACKEND") or "instagram"
IG_GRAPH = os.environ.get("IG_GRAPH", "https://graph.instagram.com/v23.0/")
META_GRAPH = os.environ.get("META_GRAPH", "https://graph.facebook.com/v26.0/")
AD_ACCOUNT = os.environ.get("META_AD_ACCOUNT") or "act_298552273"
IG_USERNAME = os.environ.get("IG_USERNAME") or "sonkozx"
MEDIA_BRANCH = os.environ.get("MEDIA_BRANCH", "media")
STORIES_ENABLED = os.environ.get("STORIES", "1") != "0"

TR = dt.timezone(dt.timedelta(hours=3))
# Günlük story türü (pazartesi=0). Karusel sonrası "yeni" story'si ayrıca atılır.
DAILY_STORY = {0: "gorev", 1: "tokat", 2: "ipucu", 3: "tokat", 4: "ipucu", 5: "aksam", 6: "ozet"}

BASE_TAGS = ["#motivasyon", "#disiplin", "#kişiselgelişim", "#sonkoz"]
TOPIC_TAGS = [
    ({"para", "yan gelir", "girişimcilik", "risk", "kariyer", "iş"}, ["#para", "#girişimcilik", "#kariyer"]),
    ({"spor", "beslenme", "sağlık", "uyku", "enerji", "hareket"}, ["#spor", "#sağlıklıyaşam", "#fitness"]),
    ({"sınav", "ders çalışma", "öğrenme", "okuma"}, ["#yks", "#dersçalışma", "#öğrenci"]),
    ({"stoacılık", "zihin", "kaygı", "korku", "aşırı düşünme", "zihinsel sağlamlık", "kendini sabotaj"},
     ["#stoacılık", "#zihin", "#farkındalık"]),
    ({"ilişkiler", "çevre", "iletişim", "liderlik", "etki", "sınırlar", "yalnızlık"},
     ["#iletişim", "#liderlik", "#ilişkiler"]),
    ({"yaratıcılık", "üretmek"}, ["#yaratıcılık", "#üretkenlik", "#ilham"]),
    ({"alışkanlık", "dopamin", "dijital bağımlılık", "telefon", "sosyal medya", "odak", "üretkenlik",
      "rutin", "sabah", "akşam", "planlama"}, ["#alışkanlık", "#odak", "#üretkenlik"]),
]
DEFAULT_TOPIC_TAGS = ["#başarı", "#hedef", "#azim"]


# ---------- durum ----------

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"next_id": 1, "history": []}


def save_state(state):
    state["history"] = state["history"][-60:]
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def slot_key(when=None):
    """Zamanlanmış işler için 'YYYY-AA-GG-sabah/aksam' (TR saati)."""
    t = (when or dt.datetime.now(dt.timezone.utc)).astimezone(TR)
    return f"{t:%Y-%m-%d}-{'sabah' if t.hour < 14 else 'aksam'}"


# ---------- açıklama ----------

def build_caption(post):
    topic = post.get("topic", "")
    tags = next((t for topics, t in TOPIC_TAGS if topic in topics), DEFAULT_TOPIC_TAGS)
    hashtags = " ".join(dict.fromkeys(BASE_TAGS + tags))
    return f"{post['caption']}\n\nKaydet, yarın tekrar oku.\nTakip et: {HANDLE}\n\n{hashtags}"


# ---------- ortak Graph istemcisi ----------

class Graph:
    """Instagram ve Meta yöntemlerinin ortak kısmı: istek, bekleme, karusel ve story akışı."""

    base = ""

    def __init__(self, token):
        self.token = token
        self._ig = None

    def call(self, method, path, **params):
        params = {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in params.items()}
        params["access_token"] = self.token
        try:
            if method == "GET":
                r = requests.get(self.base + path, params=params, timeout=120)
            else:
                r = requests.post(self.base + path, data=params, timeout=120)
            data = r.json()
        except Exception as e:  # token URL'de görünmesin
            raise RuntimeError(f"{path}: istek başarısız: {str(e).replace(self.token, '***')}") from None
        if "error" in data:
            e = data["error"]
            raise RuntimeError(f"{path}: {e.get('error_user_title') or e.get('message')} "
                               f"{e.get('error_user_msg', '')} (kod {e.get('code')}/{e.get('error_subcode', '-')})")
        return data

    def wait(self, container_id, timeout=300):
        start = time.time()
        while time.time() - start < timeout:
            s = self.call("GET", container_id, fields="status_code")
            if s.get("status_code") == "FINISHED":
                return
            if s.get("status_code") in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram medyayı işleyemedi ({s.get('status_code')}): {container_id}")
            time.sleep(5)
        raise RuntimeError(f"Instagram medyayı zamanında işlemedi: {container_id}")

    def urls(self, paths, folder):
        raise NotImplementedError

    def recent(self, edge, since):
        """Hesapta `since`'ten sonra çıkmış bir gönderi/story varsa id'sini döndürür."""
        try:
            items = self.call("GET", f"{self.ig}/{edge}", fields="id,timestamp", limit="5").get("data", [])
        except RuntimeError:
            return None
        for m in items:
            ts = m.get("timestamp")
            if ts and dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z") >= since:
                return m["id"]
        return None

    def publish(self, container_id, edge="media", tries=4):
        # Instagram, işlenmiş kapsayıcı için bile (özellikle başka bir yayının hemen ardından)
        # geçici olarak "Media Not Found" (2207006) dönebiliyor; biraz bekleyip yeniden dene.
        # Hata dönse bile yayın bazen gerçekleşiyor: her denemeden önce hesaba bakılır ki
        # aynı gönderi iki kez çıkmasın.
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=30)
        for i in range(tries):
            try:
                return self.call("POST", f"{self.ig}/media_publish", creation_id=container_id)["id"]
            except RuntimeError as e:
                transient = any(k in str(e) for k in ("2207006", "2207027", "kod 2/", "kod 1/"))
                if i < tries - 1 and transient:
                    print(f"Yayın denemesi {i + 1} başarısız: {e}")
                    time.sleep(15 * (i + 1))
                found = self.recent(edge, since)
                if found:
                    print(f"Hata dönmesine rağmen yayın gerçekleşmiş (id {found}), tekrar denenmiyor.")
                    return found
                if i == tries - 1 or not transient:
                    raise

    def publish_carousel(self, paths, caption, folder, publish=True):
        children = [self.call("POST", f"{self.ig}/media", is_carousel_item="true", image_url=u)["id"]
                    for u in self.urls(paths, folder)]
        for c in children:
            self.wait(c)
        carousel = self.call("POST", f"{self.ig}/media", media_type="CAROUSEL",
                             children=",".join(children), caption=caption)["id"]
        self.wait(carousel)
        return self.publish(carousel) if publish else carousel

    def publish_story(self, path, folder, publish=True):
        url = self.urls([path], folder)[0]
        cid = self.call("POST", f"{self.ig}/media", media_type="STORIES", image_url=url)["id"]
        self.wait(cid)
        return self.publish(cid, edge="stories") if publish else cid


# ---------- yöntem 1: Instagram ile giriş ----------

class InstagramLogin(Graph):
    base = IG_GRAPH

    @property
    def ig(self):
        if not self._ig:
            self._ig = os.environ.get("IG_USER_ID") or self.call("GET", "me", fields="user_id")["user_id"]
        return self._ig

    def urls(self, paths, folder):
        return host_on_github(paths, folder)

    def describe(self):
        me = self.call("GET", "me", fields="user_id,username,account_type,media_count,followers_count")
        return f"@{me.get('username')} ({me.get('account_type')}) · {me.get('media_count', 0)} gönderi · " \
               f"{me.get('followers_count', 0)} takipçi"

    def refresh(self):
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": self.token}, timeout=60)
        data = r.json()
        if "access_token" not in data:
            raise RuntimeError(f"Token yenilenemedi: {data.get('error', data)}")
        return data["access_token"], data.get("expires_in")


def host_on_github(paths, folder):
    """Görselleri bir repodaki 'media' dalına zorla gönderir, herkese açık adreslerini döndürür.

    Instagram görseli adresten indirir, bu yüzden o repo herkese açık olmalı. Dal her seferinde yalnızca o anki
    görselleri içerir, repo şişmez. MEDIA_REPO verilirse görseller o (herkese açık) repoya gider ve ana repo gizli kalabilir.
    """
    repo = os.environ.get("MEDIA_REPO") or os.environ["GITHUB_REPOSITORY"]
    token = os.environ.get("MEDIA_TOKEN") or os.environ["GITHUB_TOKEN"]
    work = tempfile.mkdtemp()
    try:
        rel = os.path.join("media", folder)
        os.makedirs(os.path.join(work, rel))
        names = []
        for p in paths:
            shutil.copy(p, os.path.join(work, rel, os.path.basename(p)))
            names.append(os.path.basename(p))
        ident = ["-c", "user.name=sonkoz-bot", "-c", "user.email=bot@users.noreply.github.com"]
        for args in (["init", "-q", "-b", MEDIA_BRANCH], [*ident, "add", "."],
                     [*ident, "commit", "-q", "-m", f"media {folder}"]):
            subprocess.run(["git", *args], cwd=work, check=True, capture_output=True)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, check=True,
                             capture_output=True, text=True).stdout.strip()
        push = subprocess.run(["git", "push", "-q", "--force", f"https://x-access-token:{token}@github.com/{repo}.git",
                               f"HEAD:{MEDIA_BRANCH}"], cwd=work, capture_output=True, text=True)
        if push.returncode != 0:
            raise RuntimeError("Görseller GitHub'a gönderilemedi: " + push.stderr.replace(token, "***"))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    urls = [f"https://raw.githubusercontent.com/{repo}/{sha}/media/{folder}/{n}" for n in names]
    for url in urls:  # yayına çıkmasını bekle
        for _ in range(30):
            if requests.head(url, timeout=20, allow_redirects=True).status_code == 200:
                break
            time.sleep(5)
        else:
            raise RuntimeError(f"Görsel açılmıyor (repo herkese açık mı?): {url}")
    return urls


# ---------- yöntem 2: Meta (DOKU altyapısı) ----------

class MetaSystem(Graph):
    base = META_GRAPH

    def accounts(self):
        r = self.call("GET", "me/accounts", fields="name,instagram_business_account{id,username}", limit="50")
        return [(x["name"], x.get("instagram_business_account")) for x in r.get("data", [])]

    @property
    def ig(self):
        if not self._ig:
            match = [ig for _, ig in self.accounts() if ig and ig.get("username") == IG_USERNAME]
            if not match:
                raise RuntimeError(f"@{IG_USERNAME} görünmüyor: İşletme hesabı + Facebook sayfası + sistem "
                                   f"kullanıcısında sayfa yetkisi gerekli ('python bot.py baglanti').")
            self._ig = os.environ.get("IG_USER_ID") or match[0]["id"]
        return self._ig

    def urls(self, paths, folder):
        out = []
        for p in paths:  # yerel JPEG → reklam görsel kütüphanesi → herkese açık adres
            with open(p, "rb") as f:
                r = self.call("POST", f"{AD_ACCOUNT}/adimages", bytes=base64.b64encode(f.read()).decode())
            h = next(iter(r["images"].values()))["hash"]
            out.append(self.call("GET", f"{AD_ACCOUNT}/adimages", hashes=[h], fields="url")["data"][0]["url"])
        return out

    def describe(self):
        lines = [f"Sayfa: {page} -> {'@' + ig['username'] if ig else '(bağlı Instagram yok)'}"
                 for page, ig in self.accounts()]
        b = self.call("GET", self.ig, fields="username,media_count,followers_count")
        self.call("GET", AD_ACCOUNT, fields="name")
        lines.append(f"Bağlı: @{b['username']} · {b.get('media_count', 0)} gönderi · {b.get('followers_count', 0)} "
                     f"takipçi · reklam hesabı {AD_ACCOUNT} erişilebilir")
        return "\n".join(lines)


def read_meta_token():
    tok = os.environ.get("META_TOKEN", "").strip()
    if tok:
        return tok
    for name in ("doku-sistem-token.txt", "meta-token.txt"):  # yerelde DOKU ile aynı dosyalar
        p = os.path.join(GIZLI, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                tok = f.read().strip()
            if tok:
                return tok
    raise SystemExit("Token yok: META_TOKEN ortam değişkenini ya da .gizli dosyasını ayarla.")


def client():
    if BACKEND == "meta":
        return MetaSystem(read_meta_token())
    tok = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not tok:
        raise SystemExit("Token yok: IG_ACCESS_TOKEN ortam değişkenini ayarla.")
    return InstagramLogin(tok)


# ---------- komutlar ----------

def cmd_post(args):
    posts = {p["id"]: p for p in load_all()}
    state = load_state()
    post_id = args.id or state["next_id"]
    if args.zamanli and not args.dry_run and not args.dene:
        hour = dt.datetime.now(TR).hour
        if not (8 <= hour < 11 or 20 <= hour < 23):
            print(f"Saat {hour}:xx paylaşım penceresi dışında (08-11 / 20-23), gecikmiş tetikleme atlanıyor.")
            return 0
        slot = slot_key()
        if any(slot_key(dt.datetime.fromisoformat(h["at"])) == slot for h in state["history"] if h.get("at")):
            print(f"Bu dilimde ({slot}) zaten paylaşıldı, yedek tetikleme atlanıyor.")
            return 0
    if post_id not in posts:
        print(f"Paylaşılacak gönderi kalmadı (sıradaki id: {post_id}). Yeni içerik ekle.")
        return 0
    post = posts[post_id]
    caption = build_caption(post)
    story_data = {"text": post["slides"][0]["text"]}

    if args.dry_run:
        out = os.path.join(ROOT, "preview", f"{post_id:04d}")
        render_carousel(post, DEFAULT_PALETTE, out, ext="jpg")
        render_story("yeni", story_data, os.path.join(out, "story.jpg"))
        print(f"[deneme] #{post_id} çizildi: {out}\n\n{caption}")
        return 0

    api = client()
    tmp = tempfile.mkdtemp()
    try:
        paths = render_carousel(post, DEFAULT_PALETTE, tmp, ext="jpg")
        if args.dene:  # her adım gerçek, sadece son "yayınla" çağrısı yok
            cid = api.publish_carousel(paths, caption, f"dene-{post_id:04d}", publish=False)
            print(f"[dene] #{post_id} karuseli Instagram'da hazır, YAYINLANMADI (kapsayıcı {cid})")
            sid = api.publish_story(render_story("yeni", story_data, os.path.join(tmp, "story.jpg")),
                                    f"dene-{post_id:04d}-story", publish=False)
            print(f"[dene] 'yeni karusel' story'si hazır, YAYINLANMADI (kapsayıcı {sid})")
            return 0
        media_id = api.publish_carousel(paths, caption, f"{post_id:04d}")
        print(f"Yayınlandı: #{post_id} (media id {media_id})")
        if STORIES_ENABLED:
            try:  # story başarısız olsa da karusel yayınlandı sayılır
                api.publish_story(render_story("yeni", story_data, os.path.join(tmp, "story.jpg")),
                                  f"{post_id:04d}-story")
                print("Story yayınlandı: yeni karusel duyurusu")
            except RuntimeError as e:
                print(f"UYARI: story yayınlanamadı: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    state["history"].append({"id": post_id, "media_id": media_id,
                             "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
    if not args.id:
        state["next_id"] = post_id + 1
    save_state(state)
    return 0


def daily_story_data(kind, state, posts):
    """(tür, veri, ilerletilecek sayaç) döndürür."""
    counters = state.setdefault("story", {"tokat": 0, "ipucu": 0, "gorev": 0})
    ids = sorted(posts)
    if kind == "aksam":
        nxt = posts.get(state["next_id"])
        if nxt:
            return "aksam", {"text": nxt["slides"][0]["text"]}, None
        kind = "tokat"
    if kind == "ozet":
        recent = [posts[h["id"]]["slides"][0]["text"] for h in state["history"][-5:] if h["id"] in posts]
        if recent:
            return "ozet", {"items": recent}, None
        kind = "tokat"
    if kind == "gorev":
        with open(TASKS_PATH, encoding="utf-8") as f:
            tasks = json.load(f)
        return "gorev", {"text": tasks[counters["gorev"] % len(tasks)]}, "gorev"
    if kind == "ipucu":
        k = counters["ipucu"]
        slide = posts[ids[k % len(ids)]]["slides"][1 + (k // len(ids)) % 3]
        return "ipucu", {"title": slide["title"], "text": slide["text"]}, "ipucu"
    return "tokat", {"text": posts[ids[counters["tokat"] % len(ids)]]["caption"]}, "tokat"


def cmd_story(args):
    posts = {p["id"]: p for p in load_all()}
    state = load_state()
    today = f"{dt.datetime.now(TR):%Y-%m-%d}"
    if args.zamanli and not args.dry_run and not args.dene and not 11 <= dt.datetime.now(TR).hour < 16:
        print("Story penceresi (11-16) dışında, gecikmiş tetikleme atlanıyor.")
        return 0
    if args.zamanli and not args.dry_run and not args.dene and state.get("story_last") == today:
        print(f"Bugünün story'si ({today}) zaten paylaşıldı, yedek tetikleme atlanıyor.")
        return 0
    kind = args.kind or DAILY_STORY[dt.datetime.now(TR).weekday()]
    kind, data, counter = daily_story_data(kind, state, posts)

    if args.dry_run:
        out = render_story(kind, data, os.path.join(ROOT, "preview", f"story_{kind}.jpg"))
        print(f"[deneme] story ({kind}) çizildi: {out}")
        return 0

    api = client()
    tmp = tempfile.mkdtemp()
    try:
        cid = api.publish_story(render_story(kind, data, os.path.join(tmp, "story.jpg")),
                                f"story-{dt.datetime.now(TR):%Y%m%d-%H%M}", publish=not args.dene)
        if args.dene:
            print(f"[dene] story ({kind}) hazır, YAYINLANMADI (kapsayıcı {cid})")
            return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if counter:
        state["story"][counter] += 1
    state["story_last"] = today
    save_state(state)
    print(f"Story yayınlandı: {kind}")
    return 0


def cmd_baglanti(_args):
    print(client().describe())
    return 0


def cmd_refresh_token(_args):
    if BACKEND != "instagram":
        print("Meta sistem kullanıcısı token'ı süresiz, yenileme gerekmez.")
        return 0
    api = client()
    new_token, expires_in = api.refresh()
    days = int(expires_in) // 86400 if expires_in else "?"
    if new_token == api.token:
        print(f"Token yenilendi (aynı token, ~{days} gün geçerli).")
        return 0
    if not os.environ.get("GH_PAT"):
        raise SystemExit("Instagram yeni bir token verdi ama GH_PAT yok; IG_ACCESS_TOKEN secret'ı güncellenemedi.")
    env = {**os.environ, "GH_TOKEN": os.environ["GH_PAT"]}
    subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", os.environ["GITHUB_REPOSITORY"]],
                   input=new_token, text=True, check=True, env=env, capture_output=True)
    print(f"Token yenilendi ve IG_ACCESS_TOKEN secret'ı güncellendi (~{days} gün geçerli).")
    return 0


def cmd_status(_args):
    total = len(load_all())
    state = load_state()
    left = max(0, total - state["next_id"] + 1)
    print(f"Toplam {total} gönderi, sıradaki #{state['next_id']}, kalan {left} "
          f"(günde 2 ile ~{left // 2} gün).")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Son Koz Instagram botu")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("post")
    p.add_argument("--dry-run", action="store_true", help="yayınlamadan sadece çiz")
    p.add_argument("--dene", action="store_true", help="her şeyi yap ama yayınlama")
    p.add_argument("--id", type=int, help="belirli bir gönderiyi yayınla (sıra ilerlemez)")
    p.add_argument("--zamanli", action="store_true", help="bu dilimde paylaşıldıysa atla (yedek cron'lar için)")
    st = sub.add_parser("story")
    st.add_argument("--dry-run", action="store_true", help="yayınlamadan sadece çiz")
    st.add_argument("--dene", action="store_true", help="her şeyi yap ama yayınlama")
    st.add_argument("--kind", choices=["gorev", "tokat", "ipucu", "aksam", "ozet"], help="türü zorla")
    st.add_argument("--zamanli", action="store_true", help="bugün paylaşıldıysa atla (yedek cron'lar için)")
    sub.add_parser("baglanti")
    sub.add_parser("refresh-token")
    sub.add_parser("status")
    args = parser.parse_args()
    return {"post": cmd_post, "story": cmd_story, "baglanti": cmd_baglanti,
            "refresh-token": cmd_refresh_token, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
