#!/usr/bin/env python3
"""Vygeneruje VEŘEJNÝ feed rozvrhu stavění pro weby Lanovky/Limitu.

Bere z Firestore JEN vyřešený profil (_monSector = Lanovka, _wedSector = Limit,
_thuSector = Tělocvična). Datum si POČÍTÁ SÁM z ID týdne + případného
*DateOverride — pomocná pole _monDate/_wedDate/_thuDate se nečtou, protože je
může přepsat klient se starou verzí appky (starý rozvrh Po/St). ŽÁDNÍ stavěči,
žádné sundavání, žádná obsazenost. Výstup: schedule.json = [{date, wall, profile}].

Spouští se z GitHub Action (viz .github/workflows/schedule-feed.yml). Čtení
Firestore je přes veřejné REST API (klíč je stejně veřejný v index.html),
takže Action nepotřebuje žádný secret.
"""
import datetime
import json
import urllib.request

FIRESTORE_URL = (
    "https://firestore.googleapis.com/v1/projects/climbing-app-d0074/"
    "databases/(default)/documents/weeks?pageSize=300&key="
    "AIzaSyAkrjX5SaUV8WyyVsYJK5TX2n_gmvuJGJE"
)

# (stěna, pole s vyřešeným profilem, pole s ručním datumovým override, zrušeno)
WALLS = [
    ("Lanovka",    "_monSector", "monDateOverride", "_monCancelled"),
    ("Limit",      "_wedSector", "wedDateOverride", "_wedCancelled"),
    ("Tělocvična", "_thuSector", "thuDateOverride", "_thuCancelled"),
]


def is_new_schedule(monday):
    """Od září 2026: Lanovka úterý, Limit vždy čtvrtek, Tělocvična pátek."""
    return (monday.year, monday.month) >= (2026, 9)


def default_date(monday, wall, sector):
    """Výchozí den stavění (parita s index.html a sync_calendar.py)."""
    if wall == "Lanovka":
        off = 1 if is_new_schedule(monday) else 0
    elif wall == "Limit":
        off = 3 if (is_new_schedule(monday) or sector == "Dětská") else 2
    else:  # Tělocvična
        off = 4 if is_new_schedule(monday) else 3
    return (monday + datetime.timedelta(days=off)).isoformat()


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
        week_id = doc["name"].rsplit("/", 1)[-1]
        try:
            monday = datetime.date.fromisoformat(week_id)
        except ValueError:
            continue
        for wall, sec_key, ovr_key, canc_key in WALLS:
            sector = get(sec_key)
            date = get(ovr_key) or default_date(monday, wall, sector)
            if sector and get(canc_key) is not True:
                out.append({"date": date, "wall": wall, "profile": sector})

    out.sort(key=lambda x: (x["date"], x["wall"]))

    with open("schedule.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"schedule.json vygenerován: {len(out)} stavění")


if __name__ == "__main__":
    main()
