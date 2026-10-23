"""Chiffrement AES-GCM avec clé dérivée PBKDF2-SHA256.

Format identique côté navigateur (WebCrypto) :
  {"v":1,"kdf":"PBKDF2-SHA256","iter":N,"salt":b64,"iv":b64,"ct":b64}
ct = ciphertext || tag (16 octets), comme WebCrypto.
"""
import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITER = 310000


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _derive(passphrase: str, salt: bytes, iterations: int = ITER) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_json(obj, passphrase: str) -> dict:
    if not passphrase or len(passphrase) < 16:
        raise ValueError("Phrase de passe trop courte (16 caractères minimum).")
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = _derive(passphrase, salt)
    ct = AESGCM(key).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode("utf-8"), None)
    return {"v": 1, "kdf": "PBKDF2-SHA256", "iter": ITER, "salt": _b64(salt), "iv": _b64(iv), "ct": _b64(ct)}


def encrypt_with_key(obj, key: bytes) -> dict:
    """Chiffre avec une clé brute de 32 octets (jetons Garmin : clé distincte de la phrase)."""
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, json.dumps(obj).encode("utf-8"), None)
    return {"v": 1, "iv": _b64(iv), "ct": _b64(ct)}


def decrypt_with_key(blob: dict, key: bytes):
    iv = base64.b64decode(blob["iv"])
    ct = base64.b64decode(blob["ct"])
    return json.loads(AESGCM(key).decrypt(iv, ct, None).decode("utf-8"))


def decrypt_json(blob: dict, passphrase: str):
    salt = base64.b64decode(blob["salt"])
    iv = base64.b64decode(blob["iv"])
    ct = base64.b64decode(blob["ct"])
    key = _derive(passphrase, salt, int(blob["iter"]))
    return json.loads(AESGCM(key).decrypt(iv, ct, None).decode("utf-8"))
