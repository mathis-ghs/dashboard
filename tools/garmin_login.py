#!/usr/bin/env python3
"""Connexion Garmin Connect en local (une fois, MFA possible) : écrit state/garmin_tokens.enc.json.

Les jetons sont chiffrés avec une clé aléatoire private/garmin.key (créée si absente, git-ignorée).
Copier ensuite cette clé dans le secret GitHub GARMIN_TOKEN_KEY :
    gh secret set GARMIN_TOKEN_KEY < private/garmin.key
L'email et le mot de passe ne sont ni enregistrés ni envoyés à GitHub.
"""
import base64
import getpass
import os

from fetch_garmin import KEY_FILE, ROOT, TOKENS, save_tokens


def main() -> None:
    from garminconnect import Garmin

    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            key = base64.b64decode(f.read().strip())
    else:
        key = os.urandom(32)
        os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(base64.b64encode(key).decode("ascii"))
        print(f"Clé créée : {os.path.relpath(KEY_FILE, ROOT)}")

    email = input("Email Garmin : ").strip()
    password = getpass.getpass("Mot de passe Garmin : ")
    g = Garmin(email, password, prompt_mfa=lambda: input("Code MFA : ").strip())
    g.login()
    save_tokens(g.client.dumps(), key)
    print(f"ok: connecté ({g.get_full_name()}), jetons dans {os.path.relpath(TOKENS, ROOT)}")
    print("Étapes suivantes : gh secret set GARMIN_TOKEN_KEY < private/garmin.key, puis commit de state/garmin_tokens.enc.json")


if __name__ == "__main__":
    main()
