#!/usr/bin/env python3
"""Fusionne un nouveau plan (JSON en clair, même format que private/plan.json) dans docs/plan.enc.json.

  python tools/import_plan.py private/plan_fsgt2027.json

Déchiffre le plan enregistré, garde ses semaines antérieures à la première semaine du nouveau plan
(l'historique planifié reste comparable au réalisé), remplace les suivantes, la saison et les règles,
ajoute les analyses nouvelles en tête. Écrit private/plan.json puis docs/plan.enc.json.
Phrase de passe demandée, ou variable DASH_PASSPHRASE. Faire git pull avant.
"""
import getpass
import json
import os
import sys

from crypto_util import decrypt_json, encrypt_json

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ENC = os.path.join(ROOT, "docs", "plan.enc.json")
PLAIN = os.path.join(ROOT, "private", "plan.json")


def merge(old: dict, new: dict) -> dict:
    first = min(w["start"] for w in new["weeks"])
    kept = [w for w in old.get("weeks", []) if w["start"] < first]
    seen = {(a.get("date"), a.get("title")) for a in new.get("analysis", [])}
    analysis = new.get("analysis", []) + [a for a in old.get("analysis", []) if (a.get("date"), a.get("title")) not in seen]
    return {
        "updated": new.get("updated") or old.get("updated"),
        "season": new.get("season") or old.get("season"),
        "rules": new.get("rules") or old.get("rules", []),
        "weeks": sorted(kept + new["weeks"], key=lambda w: w["start"]),
        "analysis": analysis,
    }


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage : python tools/import_plan.py <nouveau_plan.json>")
    with open(sys.argv[1], encoding="utf-8") as f:
        new = json.load(f)
    with open(ENC, encoding="utf-8") as f:
        blob = json.load(f)
    passphrase = os.environ.get("DASH_PASSPHRASE") or getpass.getpass("Phrase de passe: ")
    old = decrypt_json(blob, passphrase)
    plan = merge(old, new)
    with open(PLAIN, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(ENC, "w", encoding="utf-8") as f:
        json.dump(encrypt_json(plan, passphrase), f)
    kept = sum(1 for w in plan["weeks"] if w["start"] < min(w["start"] for w in new["weeks"]))
    print(f"ok : {kept} semaine(s) conservée(s), {len(new['weeks'])} importée(s), {len(plan['analysis'])} analyse(s)")
    print(f"écrit {os.path.relpath(PLAIN, ROOT)} et {os.path.relpath(ENC, ROOT)}")


if __name__ == "__main__":
    main()
