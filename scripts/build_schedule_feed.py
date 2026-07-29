#!/usr/bin/env python3
"""Vygeneruje VEŘEJNÝ feed rozvrhu stavění pro weby Lanovky/Limitu.

Bere z Firestore JEN vyřešená pole profil+datum (_monSector/_monDate = Lanovka,
_wedSector/_wedDate = Limit, _thuSector/_thuDate = Tělocvična). ŽÁDNÍ stavěči,
žádné sundavání, žádná obsazenost. Výstup: schedule.json = [{date, wall, profile}].

Spouští se z GitHub Action (viz .github/workflows/schedule-feed.yml). Čtení
Firestore je přes veřejné REST API (klíč je stejně veřejný v index.html),
takže Action nepotřebuje žádný secret.
"""
import json
import urllib.request

FIRESTORE_URL = (
    "https://firestore.googleapis.com/v1/projects/climbing-app-d0074/"
    "databases/(default)/documents/weeks?pageSize=300&key="
    "AIzaSyAkrjX5SaUV8WyyVsYJK5TX2n_gmvuJGJE"
)

WALLS = [
    ("Lanovka",    "_monSector", "_monDate", "_monCancelled"),
    ("Limit",      "_wedSector", "_wedDate", "_wedCancelled"),
    ("Tělocvična", "_thuSector", "_thuDate", "_thuCancelled"),
]


def val(f):
    """Firestore field → prostá hodnota (''__NULL__'' → None)."""
    if f is None:
        return None
    if "stringValue" in f:
        return None if f["stringValue"] == "__NULL__" else f["stringValue"]
    if "booleanValue" in f:
        return f["booleanValue"]
    return None


def main():
    with urllib.request.urlopen(FIRESTORE_URL, timeout=30) as resp:
        data = json.load(resp)

    out = []
    for doc in data.get("documents", []):
        fields = doc.get("fields", {})
        get = lambda k: val(fields.get(k))
        for wall, sec_key, date_key, canc_key in WALLS:
            sector = get(sec_key)
            date = get(date_key)
            if sector and date and get(canc_key) is not True:
                out.append({"date": date, "wall": wall, "profile": sector})

    out.sort(key=lambda x: (x["date"], x["wall"]))

    with open("schedule.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"schedule.json vygenerován: {len(out)} stavění")


if __name__ == "__main__":
    main()
