#!/usr/bin/env python3
"""Chiffre private/plan.json (plan d'entraînement + analyses) vers docs/plan.enc.json.

Lancer en local. Phrase de passe demandée, ou variable DASH_PASSPHRASE.
private/ est dans .gitignore : seul le fichier chiffré est commité.
"""
import getpass
import json
import os

from crypto_util import encrypt_json

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "private", "plan.json")
DST = os.path.join(ROOT, "docs", "plan.enc.json")


def main() -> None:
    with open(SRC, encoding="utf-8") as f:
        plan = json.load(f)
    passphrase = os.environ.get("DASH_PASSPHRASE") or getpass.getpass("Phrase de passe: ")
    blob = encrypt_json(plan, passphrase)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(blob, f)
    print(f"ok: écrit {os.path.relpath(DST, ROOT)}")


if __name__ == "__main__":
    main()
