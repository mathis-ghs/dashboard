#!/usr/bin/env python3
"""Déchiffre docs/plan.enc.json vers private/plan.json.

Le plan peut être modifié et enregistré depuis la page : lancer ce script (après git pull)
avant de modifier private/plan.json à la main, sinon encrypt_plan.py écraserait ces changements.
Phrase de passe demandée, ou variable DASH_PASSPHRASE.
"""
import getpass
import json
import os

from crypto_util import decrypt_json

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "docs", "plan.enc.json")
DST = os.path.join(ROOT, "private", "plan.json")


def main() -> None:
    with open(SRC, encoding="utf-8") as f:
        blob = json.load(f)
    passphrase = os.environ.get("DASH_PASSPHRASE") or getpass.getpass("Phrase de passe: ")
    plan = decrypt_json(blob, passphrase)
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"ok: écrit {os.path.relpath(DST, ROOT)}")


if __name__ == "__main__":
    main()
