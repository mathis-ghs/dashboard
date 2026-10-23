#!/usr/bin/env python3
"""Récupère les données santé Garmin Connect (sommeil, VFC, FC repos, Body Battery, stress, pas, étages,
calories, SpO2, VO2max, poids), écrit docs/garmin.enc.json (chiffré avec la phrase).

Accès non officiel (bibliothèque garminconnect). Les jetons Garmin sont dans state/garmin_tokens.enc.json,
chiffrés avec une clé distincte de la phrase (GARMIN_TOKEN_KEY). Le refresh token peut tourner : le fichier
est réécrit quand les jetons changent, et le workflow le commite. Premier jeton : tools/garmin_login.py.

Variables d'environnement : DASH_PASSPHRASE, GARMIN_TOKEN_KEY (sinon private/garmin.key en local).
Optionnel : GARMIN_DAYS (jours relus à chaque run, défaut 7), GARMIN_BACKFILL (historique au premier run, défaut 180),
GARMIN_KEEP (jours conservés, défaut 400).
"""
import base64
import datetime as dt
import json
import os
import sys
import time
from zoneinfo import ZoneInfo

from crypto_util import decrypt_json, decrypt_with_key, encrypt_json, encrypt_with_key

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "docs", "garmin.enc.json")
TOKENS = os.path.join(ROOT, "state", "garmin_tokens.enc.json")
KEY_FILE = os.path.join(ROOT, "private", "garmin.key")
TZ = ZoneInfo("Europe/Paris")
DAYS = int(os.environ.get("GARMIN_DAYS", "7"))
BACKFILL = int(os.environ.get("GARMIN_BACKFILL", "180"))
KEEP = int(os.environ.get("GARMIN_KEEP", "400"))


def token_key() -> bytes:
    k = os.environ.get("GARMIN_TOKEN_KEY")
    if not k and os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            k = f.read().strip()
    if not k:
        raise SystemExit("GARMIN_TOKEN_KEY absent (secret GitHub, ou private/garmin.key en local).")
    key = base64.b64decode(k)
    if len(key) != 32:
        raise SystemExit("GARMIN_TOKEN_KEY invalide (32 octets en base64 attendus).")
    return key


def save_tokens(tokens: str, key: bytes) -> None:
    os.makedirs(os.path.dirname(TOKENS), exist_ok=True)
    with open(TOKENS, "w", encoding="utf-8") as f:
        json.dump(encrypt_with_key({"tokens": tokens}, key), f)


def load_tokens(key: bytes) -> str:
    if not os.path.exists(TOKENS):
        raise SystemExit("state/garmin_tokens.enc.json absent : lancer tools/garmin_login.py en local.")
    with open(TOKENS, encoding="utf-8") as f:
        return decrypt_with_key(json.load(f), key)["tokens"]


def dig(o, *path):
    for p in path:
        if isinstance(o, list):
            o = o[0] if o else None
        if not isinstance(o, dict):
            return None
        o = o.get(p)
    return o


def hours(sec):
    return round(sec / 3600, 2) if sec else None


def call(fn, *args):
    """Un appel qui échoue (donnée absente, erreur ponctuelle) ne bloque pas les autres."""
    for attempt in range(3):
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001
            name = type(e).__name__
            if "TooManyRequests" in name and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            if "Authentication" in name:
                raise
            print(f"  {fn.__name__}{args}: {name}", file=sys.stderr)
            return None


def day(g, d: str) -> dict:
    s = call(g.get_user_summary, d) or {}
    sl = dig(call(g.get_sleep_data, d), "dailySleepDTO") or {}
    hrv = dig(call(g.get_hrv_data, d), "hrvSummary") or {}
    mm = call(g.get_max_metrics, d)
    out = {
        "d": d,
        "steps": s.get("totalSteps"),
        "floors": round(s["floorsAscended"]) if s.get("floorsAscended") is not None else None,
        "kcal": s.get("totalKilocalories"),
        "kcal_act": s.get("activeKilocalories"),
        "rhr": s.get("restingHeartRate"),
        "stress": s.get("averageStressLevel") if (s.get("averageStressLevel") or -1) >= 0 else None,
        "bb_max": s.get("bodyBatteryHighestValue"),
        "bb_min": s.get("bodyBatteryLowestValue"),
        "bb_wake": s.get("bodyBatteryAtWakeTime"),
        "spo2": s.get("averageSpo2"),
        "spo2_min": s.get("lowestSpo2"),
        "resp": s.get("avgWakingRespirationValue"),
        "sleep_h": hours(sl.get("sleepTimeSeconds")),
        "deep_h": hours(sl.get("deepSleepSeconds")),
        "rem_h": hours(sl.get("remSleepSeconds")),
        "light_h": hours(sl.get("lightSleepSeconds")),
        "awake_h": hours(sl.get("awakeSleepSeconds")),
        "sleep_score": dig(sl, "sleepScores", "overall", "value"),
        "hrv": hrv.get("lastNightAvg"),
        "hrv_7d": hrv.get("weeklyAvg"),
        "hrv_status": hrv.get("status"),
        "hrv_lo": dig(hrv, "baseline", "balancedLow"),
        "hrv_hi": dig(hrv, "baseline", "balancedUpper"),
        "vo2": dig(mm, "generic", "vo2MaxPreciseValue") or dig(mm, "generic", "vo2MaxValue"),
        "vo2_bike": dig(mm, "cycling", "vo2MaxPreciseValue") or dig(mm, "cycling", "vo2MaxValue"),
    }
    return {k: v for k, v in out.items() if v is not None}


def weights(g, start: str, end: str) -> dict:
    """Poids par jour (kg) et masse grasse (%), si balance ou saisie dans Garmin Connect."""
    r = call(g.get_weigh_ins, start, end) or {}
    out = {}
    for w in r.get("dailyWeightSummaries") or []:
        lw = w.get("latestWeight") or {}
        if lw.get("weight"):
            out[w["summaryDate"]] = {"weight": round(lw["weight"] / 1000, 1),
                                     **({"fat": round(lw["bodyFat"], 1)} if lw.get("bodyFat") else {})}
    return out


def login(key: bytes):
    from garminconnect import Garmin

    tokens = load_tokens(key)
    g = Garmin()
    g.login(tokenstore=tokens)
    return g, tokens


def main() -> None:
    passphrase = os.environ["DASH_PASSPHRASE"]
    key = token_key()
    g, tokens = login(key)

    old = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                old = decrypt_json(json.load(f), passphrase)
        except Exception as e:  # noqa: BLE001
            print(f"ATTENTION: historique Garmin illisible ({type(e).__name__}), reconstruction.", file=sys.stderr)
    by_day = {x["d"]: x for x in old.get("days", [])}

    today = dt.datetime.now(TZ).date()
    n = DAYS if by_day else BACKFILL
    dates = [(today - dt.timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]
    for i, d in enumerate(dates):
        by_day[d] = day(g, d)
        if n > 20 and i % 20 == 0:
            print(f"  {d} ({i + 1}/{n})")
    for d, w in weights(g, (today - dt.timedelta(days=max(n, 30))).isoformat(), today.isoformat()).items():
        by_day.setdefault(d, {"d": d}).update(w)

    first = (today - dt.timedelta(days=KEEP)).isoformat()
    days = [by_day[d] for d in sorted(by_day) if d >= first and len(by_day[d]) > 1]
    if days != old.get("days"):
        payload = {"generated": dt.datetime.now(TZ).isoformat(timespec="minutes"), "days": days}
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(encrypt_json(payload, passphrase), f)
        print(f"ok: {len(days)} jours Garmin, écrit {os.path.relpath(OUT, ROOT)}")
    else:
        print("Garmin : pas de changement.")

    new_tokens = g.client.dumps()
    if json.loads(new_tokens) != json.loads(tokens):
        save_tokens(new_tokens, key)
        print("Jetons Garmin renouvelés, state/garmin_tokens.enc.json réécrit.")


if __name__ == "__main__":
    main()
