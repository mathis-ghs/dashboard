#!/usr/bin/env python3
"""Chiffre la bibliothèque d'entraînement vers docs/bibliotheque.enc.json et docs/biblio/*.bin.

Sources (git-ignorées) :
  private/bibliotheque.json        séances, exercices, programmes, principes (build_bibliotheque.py)
  private/livre/images/<nom>.jpg   illustrations des exercices, déjà réduites
  private/livre/img.key            clé AES des images (créée au premier lancement)

La bibliothèque est chiffrée comme le plan (phrase de passe). Les images sont chiffrées
en AES-GCM avec une clé aléatoire stockée dans la bibliothèque chiffrée : la page dérive
la clé de la phrase une seule fois, puis déchiffre chaque image à la demande.
Format d'une image : iv (12 octets) || ciphertext || tag. Nom : HMAC(clé, nom) tronqué.
Une image déjà présente n'est pas réécrite. Phrase demandée, ou variable DASH_PASSPHRASE.
"""
import base64
import getpass
import hashlib
import hmac
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from crypto_util import encrypt_json

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "private", "bibliotheque.json")
IMG_SRC = os.path.join(ROOT, "private", "livre", "images")
KEY_FILE = os.path.join(ROOT, "private", "livre", "img.key")
DST = os.path.join(ROOT, "docs", "bibliotheque.enc.json")
IMG_DST = os.path.join(ROOT, "docs", "biblio")


def img_key() -> bytes:
    if not os.path.exists(KEY_FILE):
        with open(KEY_FILE, "w") as f:
            f.write(os.urandom(32).hex())
    with open(KEY_FILE) as f:
        return bytes.fromhex(f.read().strip())


def main() -> None:
    with open(SRC, encoding="utf-8") as f:
        lib = json.load(f)
    passphrase = os.environ.get("DASH_PASSPHRASE") or getpass.getpass("Phrase de passe: ")
    key = img_key()
    os.makedirs(IMG_DST, exist_ok=True)
    files, written, wanted = {}, 0, set()
    for ex in lib["exercices"]:
        for name in ex["images"]:
            if name in files:
                continue
            fid = hmac.new(key, name.encode(), hashlib.sha256).hexdigest()[:20]
            files[name] = fid
            path = os.path.join(IMG_DST, fid + ".bin")
            wanted.add(fid + ".bin")
            if os.path.exists(path):
                continue
            with open(os.path.join(IMG_SRC, name + ".jpg"), "rb") as f:
                data = f.read()
            iv = os.urandom(12)
            with open(path, "wb") as f:
                f.write(iv + AESGCM(key).encrypt(iv, data, None))
            written += 1
    for ex in lib["exercices"]:
        ex["images"] = [files[n] for n in ex["images"]]
    removed = 0
    for fn in os.listdir(IMG_DST):
        if fn.endswith(".bin") and fn not in wanted:
            os.remove(os.path.join(IMG_DST, fn))
            removed += 1
    lib["img_key"] = base64.b64encode(key).decode("ascii")
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(encrypt_json(lib, passphrase), f)
    print(f"ok: écrit {os.path.relpath(DST, ROOT)}, {len(files)} images ({written} nouvelles, {removed} supprimées)")


if __name__ == "__main__":
    main()
