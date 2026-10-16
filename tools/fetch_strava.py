#!/usr/bin/env python3
"""Récupère les activités Strava, calcule les métriques de charge, écrit docs/data.enc.json (chiffré).

Variables d'environnement : STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN, DASH_PASSPHRASE.
Optionnel : DAYS (défaut 180).
"""
import datetime as dt
import json
import math
import os
import sys
from zoneinfo import ZoneInfo

import requests

from crypto_util import encrypt_json

API = "https://www.strava.com/api/v3"
DAYS = int(os.environ.get("DAYS", "180"))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "docs", "data.enc.json")
TZ = ZoneInfo("Europe/Paris")
CYCLING = {"Ride", "VirtualRide", "GravelRide", "MountainBikeRide", "EBikeRide"}
RUNNING = {"Run", "TrailRun", "VirtualRun"}
TAU_CTL, TAU_ATL = 42, 7
MODEL_NOTE = "CTL = EWMA 42 j, ATL = EWMA 7 j, sur Strava Relative Effort (proxy, pas TSS). TSB = CTL - ATL."


def access_token() -> str:
    old = os.environ["STRAVA_REFRESH_TOKEN"]
    r = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.environ["STRAVA_CLIENT_ID"],
            "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": old,
        },
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    if j.get("refresh_token") and j["refresh_token"] != old:
        print("ATTENTION: refresh token Strava tourné. Mettre à jour le secret STRAVA_REFRESH_TOKEN.", file=sys.stderr)
    return j["access_token"]


def fetch_activities(token: str, after: int) -> list:
    out, page = [], 1
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        r = requests.get(
            f"{API}/athlete/activities",
            headers=headers,
            params={"after": after, "per_page": 200, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        out.extend(batch)
        if len(batch) < 200:
            return out
        page += 1


def norm(a: dict) -> dict:
    sport = a.get("sport_type") or a.get("type") or "?"
    return {
        "id": a["id"],
        "date": a["start_date_local"][:10],
        "start": a["start_date_local"],
        "name": a.get("name", ""),
        "sport": sport,
        "trainer": bool(a.get("trainer", False)),
        "km": round(a.get("distance", 0) / 1000, 2),
        "h": round(a.get("moving_time", 0) / 3600, 2),
        "elev": round(a.get("total_elevation_gain", 0) or 0),
        "re": a.get("suffer_score"),
        "hr_avg": a.get("average_heartrate"),
        "hr_max": a.get("max_heartrate"),
        "w_avg": a.get("average_watts") if a.get("device_watts") else None,
        "kudos": a.get("kudos_count", 0),
    }


def flags(a: dict) -> list:
    f = []
    if a["sport"] in CYCLING | RUNNING and a["h"] < 0.25:
        f.append("short")
    if a["hr_avg"] is None:
        f.append("no_hr")
    if a["re"] is None:
        f.append("no_re")
    if a["sport"] in CYCLING and a["w_avg"] is None:
        f.append("trainer_no_power" if a["trainer"] else "no_power")
    return f


def ewma(series, tau, init=0.0):
    alpha = 1 - math.exp(-1 / tau)
    v, out = init, []
    for x in series:
        v = v + alpha * (x - v)
        out.append(v)
    return out


def compute(acts: list, today: dt.date) -> dict:
    start = today - dt.timedelta(days=DAYS - 1)
    days = [start + dt.timedelta(i) for i in range(DAYS)]
    load_by_day = {}
    for a in acts:
        load_by_day[a["date"]] = load_by_day.get(a["date"], 0.0) + (a["re"] or 0)
    loads = [load_by_day.get(d.isoformat(), 0.0) for d in days]
    ctl = ewma(loads, TAU_CTL)
    atl = ewma(loads, TAU_ATL)
    daily = [
        {"d": d.isoformat(), "load": round(l, 1), "ctl": round(c, 1), "atl": round(t, 1), "tsb": round(c - t, 1)}
        for d, l, c, t in zip(days, loads, ctl, atl)
    ]

    weeks = {}
    for a in acts:
        d = dt.date.fromisoformat(a["date"])
        mon = (d - dt.timedelta(days=d.weekday())).isoformat()
        w = weeks.setdefault(mon, {"week": mon, "h": 0.0, "km": 0.0, "re": 0.0, "n": 0})
        w["h"] += a["h"]
        w["km"] += a["km"]
        w["re"] += a["re"] or 0
        w["n"] += 1
    weekly = [
        {"week": w["week"], "h": round(w["h"], 2), "km": round(w["km"], 1), "re": round(w["re"]), "n": w["n"]}
        for _, w in sorted(weeks.items())
    ]

    def within(n):
        return [a for a in acts if 0 <= (today - dt.date.fromisoformat(a["date"])).days < n]

    last7, last28 = within(7), within(28)
    last = daily[-1]
    summary = {
        "ctl": last["ctl"],
        "atl": last["atl"],
        "tsb": last["tsb"],
        "h_7d": round(sum(a["h"] for a in last7), 2),
        "km_7d": round(sum(a["km"] for a in last7), 1),
        "re_7d": round(sum(a["re"] or 0 for a in last7)),
        "n_7d": len(last7),
        "h_week_28d": round(sum(a["h"] for a in last28) / 4, 2),
        "re_week_28d": round(sum(a["re"] or 0 for a in last28) / 4),
        "n_28d": len(last28),
    }
    return {"summary": summary, "daily": daily, "weekly": weekly}


def main() -> None:
    passphrase = os.environ["DASH_PASSPHRASE"]
    token = access_token()
    today = dt.datetime.now(TZ).date()
    after = int((dt.datetime.now(TZ) - dt.timedelta(days=DAYS)).timestamp())
    acts = [norm(a) for a in fetch_activities(token, after)]
    acts.sort(key=lambda a: a["start"], reverse=True)
    for a in acts:
        a["flags"] = flags(a)
    payload = {
        "generated": dt.datetime.now(TZ).isoformat(timespec="minutes"),
        "days": DAYS,
        "model": MODEL_NOTE,
        **compute(acts, today),
        "activities": acts,
    }
    blob = encrypt_json(payload, passphrase)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(blob, f)
    print(f"ok: {len(acts)} activités, écrit {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
