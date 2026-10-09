"""İçerik dosyalarını kontrol eder: id sırası, slayt yapısı, metin uzunluğu, tekrar eden kancalar."""
import glob
import json
import os
import re
import sys

LIMITS = {"hook": 95, "title": 42, "text": 200, "cta": 75}


def norm(s):
    return re.sub(r"[^\wçğıöşü]", "", s.replace("*", "").lower())


def load_all():
    posts = []
    for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "content", "*.json"))):
        with open(path, encoding="utf-8") as f:
            for p in json.load(f):
                p["_file"] = os.path.basename(path)
                posts.append(p)
    return posts


def main():
    posts = load_all()
    errors, seen = [], {}
    for n, p in enumerate(posts, 1):
        where = f"{p['_file']} #{p.get('id')}"
        if p.get("id") != n:
            errors.append(f"{where}: id {n} olmalı")
        s = p.get("slides", [])
        if [x.get("type") for x in s] != ["hook", "body", "body", "body", "cta"]:
            errors.append(f"{where}: slayt yapısı hatalı")
            continue
        if not p.get("caption"):
            errors.append(f"{where}: caption yok")
        if len(s[0]["text"]) > LIMITS["hook"]:
            errors.append(f"{where}: kanca çok uzun ({len(s[0]['text'])})")
        for b in s[1:4]:
            if len(b.get("title", "")) > LIMITS["title"]:
                errors.append(f"{where}: başlık uzun: {b['title']}")
            if len(b["text"]) > LIMITS["text"]:
                errors.append(f"{where}: metin uzun ({len(b['text'])})")
        if len(s[4]["text"]) > LIMITS["cta"]:
            errors.append(f"{where}: kapanış uzun")
        for t in [x.get("text", "") for x in s] + [x.get("title", "") for x in s]:
            if t.count("*") % 2:
                errors.append(f"{where}: kapanmamış * : {t}")
        key = norm(s[0]["text"])
        if key in seen:
            errors.append(f"{where}: kanca tekrarı (#{seen[key]})")
        seen[key] = p.get("id")
    print(f"{len(posts)} gönderi, {len(errors)} hata")
    for e in errors:
        print(" -", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
