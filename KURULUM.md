# Son Koz (@sonkozx) — Bot Kurulum Rehberi

Bot GitHub'ın sunucularında çalışır (bilgisayarın kapalı olsa bile). Her gün:

| Saat (TR) | Paylaşım |
|---|---|
| 08:30 | Karusel + "Yeni karusel" story'si |
| 13:00 | Günün story'si (görev / tokat / ipucu / bu akşam / haftalık özet) |
| 20:30 | Karusel + "Yeni karusel" story'si |

Bağlantı yöntemi: **Instagram ile giriş.** Facebook sayfası, işletme portföyü ya da sistem kullanıcısı gerekmez.
Token Facebook şifrene ve oturumuna bağlı değildir. 60 gün geçerlidir ve bot her pazartesi kendisi yeniler.

Token'ı ve şifreleri **sen** girersin; ben göremem ve giremem. Toplam süre ~20–30 dakika.

---

## 1) Instagram hesabı

Instagram → ☰ → **Ayarlar ve gizlilik** → **Hesap türü ve araçlar** → **Profesyonel hesaba geç**.
**İşletme** ya da **İçerik Üreticisi** ikisi de olur. Hesap herkese açık olmalı.

## 2) Instagram token'ı

1. https://developers.facebook.com → **Uygulamalarım**. Mevcut uygulamanı (Akis Reklam Aracı) kullanabilirsin
   ya da **Uygulama oluştur** ile yeni bir tane aç (ör. `sonkoz-bot`).
2. Uygulama panelinde **Ürün ekle** → **Instagram** → **API setup with Instagram login**.
3. **Generate access tokens** bölümünde **Add account** → @sonkozx ile giriş yap → izin ver.
   (Hesap "test kullanıcısı" daveti isterse Instagram'da **Ayarlar → Uygulamalar ve web siteleri → Test kullanıcısı davetleri**
   bölümünden kabul et.)
4. İzinler: `instagram_business_basic` ve `instagram_business_content_publish`.
5. Çıkan **token**'ı kopyala. Bu sohbete yazma, 4. adımda doğrudan GitHub'a gireceksin.

## 3) GitHub reposu

1. https://github.com → **New repository** → ad: `sonkozx-bot` → **Public** → oluştur.
   - **Neden herkese açık?** Instagram görselleri bir internet adresinden indiriyor. Bot görselleri reponun
     `media` dalına koyuyor. Bu dalda her seferinde sadece son gönderinin görselleri kalıyor.
   - Ana reponun gizli kalmasını istersen: ana repoyu **Private** aç, görseller için ayrı, boş, **Public** bir repo aç
     (ör. `sonkozx-media`). Aşağıdaki tabloda `MEDIA_REPO` ve `MEDIA_TOKEN` alanlarını doldur.
2. Bu klasörü yükle:

```bash
git init -b main
```
```bash
git add .
```
```bash
git commit -m "Son Koz bot"
```
```bash
git remote add origin https://github.com/KULLANICI_ADIN/sonkozx-bot.git
```
```bash
git push -u origin main
```

## 4) Gizli anahtarlar

Repo → **Settings** → **Secrets and variables** → **Actions**:

| Sekme | Ad | Değer | Gerekli mi |
|---|---|---|---|
| Secrets | `IG_ACCESS_TOKEN` | 2. adımdaki token | **Evet** |
| Secrets | `GH_PAT` | GitHub token'ı (aşağıda), Instagram yeni token verirse secret'ı günceller | Önerilir |
| Variables | `MEDIA_REPO` | `KULLANICI_ADIN/sonkozx-media` | Sadece ana repo gizliyse |
| Secrets | `MEDIA_TOKEN` | o repoya yazabilen GitHub token'ı | Sadece ana repo gizliyse |
| Variables | `STORIES` | `0` yazarsan story'ler kapanır | Hayır |

**GitHub token'ı (GH_PAT / MEDIA_TOKEN):** GitHub → sağ üst profil → **Settings** → **Developer settings** →
**Personal access tokens** → **Fine-grained tokens** → **Generate new token** → sadece ilgili repoyu seç →
GH_PAT için **Secrets: Read and write**, MEDIA_TOKEN için **Contents: Read and write**.

## 5) Test et ve başlat

1. Repo → **Actions** → iş akışlarını etkinleştir.
2. **Instagram paylaşımı** → **Run workflow** → "Sadece dene" işaretli → yeşil tik gelmeli (sadece çizer).
3. Tekrar **Run workflow** → "Sadece dene" işaretsiz → ilk karusel ve story @sonkozx'e düşer.
4. Bundan sonrası otomatik.

---

## Story'ler

| Gün | 13:00 story'si |
|---|---|
| Pazartesi | Haftanın görevi (`content/stories/gorevler.json`, 60 görev) |
| Salı, Perşembe | Tek cümlelik tokat |
| Çarşamba, Cuma | Mini ipucu (karuselin ara slaytlarından) |
| Cumartesi | "Bu akşam 20:30" ön gösterimi |
| Pazar | Haftalık özet (son 5 karusel) |

Anket, soru kutusu, test gibi **çıkartmalar API'de yok**; istersen günde bir tanesini telefondan ekle.
Story yayınlanamazsa karusel yine yayınlanır, Actions kaydında `UYARI: story yayınlanamadı` görünür.

## Alternatif: Meta sistem kullanıcısı (DOKU altyapısı)

İleride DOKU'daki sistem kullanıcısı token'ı düzelirse Son Koz da ona geçebilir: Variables'a `BACKEND` = `meta`,
Secrets'a `META_TOKEN` ekle. Bu yöntemde görseller reklam hesabının kütüphanesinden yayınlanır, repo tamamen gizli kalabilir.
@sonkozx'in bir Facebook sayfasına bağlı olması ve o sayfanın sistem kullanıcısına atanması gerekir.

## Sık sorulanlar

**Günde 3 karusel:** `.github/workflows/post.yml` içine bir `cron` satırı ekle, örn. `- cron: "0 10 * * *"` (13:00 TR).
Story ile çakışmasın diye `story.yml`'deki saati de kaydır.

**Saatler birkaç dakika kayıyor:** GitHub zamanlanmış işleri 5–30 dk geciktirebilir; normal.

**Yerelde önizleme** (yayınlamaz, token gerekmez):
```bash
python bot.py post --dry-run --id 42
```
```bash
python bot.py story --dry-run --kind gorev
```
```bash
python bot.py status
```

**Yeni içerik:** `content/` içine `1001-1050.json` gibi dosya ekle, `python validate.py` ile kontrol et.

**Hata olursa:** Actions'ta kırmızı çarpılı çalışmayı aç, hata satırını kopyala, bana gönder.
