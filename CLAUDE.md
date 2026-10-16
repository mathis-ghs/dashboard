# Dashboard saison cycliste (Strava → GitHub Pages, chiffré)

Page HTML statique, mise à jour chaque jour par GitHub Actions depuis l'API Strava. Les données sont chiffrées : la page ne les affiche qu'après saisie de la phrase de passe.

URL : https://mathis-ghs.github.io/dashboard/

## Arborescence

```
.github/workflows/update.yml   Cron quotidien (05:00 UTC = 07:00 Paris) + workflow_dispatch
docs/index.html                Page unique : déchiffrement WebCrypto, rendu, plan éditable et enregistrable, coach IA
docs/data.enc.json             Données Strava chiffrées (généré par fetch_strava.py, commit du bot)
docs/plan.enc.json             Plan chiffré : commité depuis la page (API GitHub) ou par encrypt_plan.py
tools/fetch_strava.py          Strava → métriques → chiffrement → docs/data.enc.json
tools/encrypt_plan.py          private/plan.json → docs/plan.enc.json
tools/decrypt_plan.py          docs/plan.enc.json → private/plan.json (à lancer avant toute édition locale)
tools/crypto_util.py           AES-GCM, PBKDF2-SHA256, utilisé par les scripts Python
requirements.txt               requests==2.32.3, cryptography==43.0.3
private/plan.json              Plan source, git-ignoré, JAMAIS commité
HANDOFF.md                     Notes de passation, git-ignoré
```

## Flux de données

1. Le workflow lance `tools/fetch_strava.py` avec les secrets `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, `DASH_PASSPHRASE`.
2. `access_token()` échange le refresh token contre un access token.
3. `fetch_activities()` pagine l'API (`DAYS` jours, défaut 180).
4. `norm()` normalise chaque activité, `flags()` détecte les anomalies de données.
5. `compute()` calcule CTL, ATL, TSB via `ewma()`.
6. `encrypt_json()` écrit `docs/data.enc.json`. Le workflow ne commit que ce fichier, et seulement s'il a changé.
7. Dans le navigateur, `index.html` demande la phrase, dérive la clé, déchiffre `data.enc.json` et `plan.enc.json`, puis appelle `renderAll()`.

## Chiffrement (à ne pas modifier sans raison)

- AES-GCM, tag de 16 octets concaténé au ciphertext (format WebCrypto).
- PBKDF2-SHA256, 310 000 itérations, sel 16 octets, IV 12 octets.
- Phrase de passe : 16 caractères minimum (vérifié dans `crypto_util.py`).
- Toute modification de ces paramètres doit rester identique entre `crypto_util.py` (Python) et `decrypt` / `encrypt` dans `index.html` (WebCrypto, constante `ITER`), sinon le déchiffrement échoue.

## Modèle de charge

- CTL = EWMA 42 jours, ATL = EWMA 7 jours, TSB = CTL − ATL.
- Entrée : Strava Relative Effort (RE), un proxy et non un TSS. Les valeurs ne sont pas comparables à un PMC standard.
- Types d'activité : `CYCLING` (Ride, VirtualRide, GravelRide, MountainBikeRide, EBikeRide), `RUNNING` (Run, TrailRun, VirtualRun).
- Fuseau d'agrégation : Europe/Paris.

## Structure de `docs/index.html`

- Éléments d'identification : `#gate`, `#unlockForm`, `#pass`, `#app`, `#updated`, `#refresh`, `#theme`, `#settings`, `#lock`.
- Cinq onglets (`showTab`, routage par hash `#apercu`, `#plan`, `#coach`, `#activites`, `#notes`). Sur mobile (< 640 px), la barre d'onglets passe en bas d'écran.
  - Aperçu : `#today` (séance du jour, prochaine séance, semaine en cours avec 7 pastilles et écart au plan : prévu à date, réalisé, écart, compte des séances), `#kpis` (CTL/ATL/TSB avec variation sur 7 j, jauge TSB, volume), `#chartForm` (CTL/ATL + panneau TSB, période 6 sem./3 mois/6 mois), `#chartWeeks` (heures par semaine empilées par sport, cible du plan).
  - Plan : `#plan` en lecture par défaut, bouton `#editPlan` pour passer en édition (séances, objectif et cible de chaque semaine, ajout et suppression de semaines). `#draftBar` apparaît quand le brouillon local diffère du plan enregistré, avec `#savePlan` (commit GitHub), `#resetPlan`, `#exportPlan`.
  - Coach : chat `#chat`, saisie `#coachForm` (voir « Coach IA »).
  - Activités : filtres `#sportSeg` et `#actSearch`, liste `#acts` groupée par semaine avec lien vers Strava, `#quality`.
  - Notes : `#rules`, `#analysis`.
- Fonctions de rendu : `renderToday`, `renderKpis`, `renderCharts` (`renderFormChart`, `renderWeeksChart`, survol + clavier), `renderPlan`, `renderRules`, `renderAnalysis`, `renderQuality`, `renderActivities`, orchestrées par `renderAll`. `indexData` construit `BY_DAY` et `WEEKS` (heures par semaine et par sport) à partir de `DATA.activities`.
- Plan : `actualFor` et `statusFor` comparent le planifié au réalisé par date et sport (`findSession`, `sessionRow`). Une séance `other` ne compte que les activités hors vélo et course.
- Édition du plan : brouillon dans `localStorage` (`loadDraft`, `saveDraft`), local au navigateur, supprimé s'il redevient identique au plan chiffré. Suppression de séance annulable via le toast. Bouton d'export `#exportPlan` qui produit un `plan.json`.
- Préférences par navigateur dans `localStorage` : `theme` (auto/clair/sombre), `range` (période du graphe de charge). La phrase de passe n'est jamais stockée : elle reste en mémoire le temps de la session, `#lock` l'efface.
- Réglages (`#settingsDlg`, `openSettings`) : jeton GitHub, dépôt, clé Gemini, modèle. Stockés dans `localStorage["secrets"]`, chiffrés avec la phrase (`loadSecrets`, `storeSecrets`, même format que les fichiers chiffrés).

## Enregistrement du plan depuis la page

- `savePlan` chiffre le plan dans le navigateur (`encrypt`) et commite `docs/plan.enc.json` via l'API GitHub contents (`gh`). Jeton « fine-grained » limité au dépôt, permission Contents en lecture et écriture.
- Avec un jeton, `fetchPlanBlob` lit le plan sur l'API GitHub plutôt que sur GitHub Pages (qui met environ une minute à se mettre à jour).
- `docs/plan.enc.json` devient la référence : `private/plan.json` peut être en retard. Avant une édition locale : `git pull`, puis `tools/decrypt_plan.py`, puis éditer, puis `encrypt_plan.py`.
- Le workflow fait `git pull --rebase` avant de pousser `data.enc.json`, pour ne pas échouer si le plan a été commité entre-temps.

## Coach IA

- Gemini (offre gratuite Google AI Studio), appelé directement depuis le navigateur (`gemini`, endpoint `generateContent`). Modèles listés dynamiquement (`loadModels`), le Flash non Lite le plus récent par défaut.
- En gratuit, Google peut utiliser les échanges pour entraîner ses modèles. Choix de l'utilisateur : `coachContext` n'envoie jamais les noms d'activités, les heures de départ ni les identifiants Strava (lieux et horaires). Ne pas ajouter ces champs.
- Contexte envoyé une fois en tête de conversation : résumé de charge, 8 semaines de charge quotidienne et d'activités, 16 semaines de volume, plan complet (ids de séances, statut, réalisé), règles, 3 dernières analyses.
- Un seul outil, `proposer_modifications_plan` (opérations `modifier_seance`, `ajouter_seance`, `supprimer_seance`, `modifier_semaine`, `ajouter_semaine`, `ajouter_analyse`). `applyOps` les applique sur une copie et produit un diff ; l'utilisateur accepte ou refuse (`showProposal`), puis la réponse de l'outil est renvoyée au modèle. Rien n'est enregistré sur GitHub sans clic sur « Enregistrer ».
- Conversation gardée en mémoire seulement (`CHAT`), effacée au verrouillage.
- Couleurs des graphes : variables `--ctl`, `--atl`, `--tsb`, `--bike`, `--run`, `--other`, validées pour le daltonisme en clair et en sombre. Les changer avec précaution.
- Le HTML est un fichier unique : CSS et JS inline, pas de build, pas de dépendance externe.

## Format de `private/plan.json`

Clés de premier niveau : `updated`, `season`, `rules`, `weeks`, `analysis`. Les textes de `analysis` sont rendus en paragraphes (séparés par des lignes vides), le HTML est échappé.

Édition locale : `git pull`, `python tools/decrypt_plan.py` (le plan a pu être modifié depuis la page), éditer, `python tools/encrypt_plan.py`, puis commit de `docs/plan.enc.json`.

## Règles pour les modifications

- Ne jamais commiter `private/`, `HANDOFF.md`, `.venv/`, ni de phrase de passe, de client secret, de refresh token ou d'access token.
- Ne jamais afficher de données personnelles en clair dans `docs/` : tout passe par le chiffrement.
- Pour un changement visuel (CSS, mise en page, couleurs, graphes) : modifier `docs/index.html` seul. Aucun re-chiffrement nécessaire.
- Pour un changement de logique de calcul : modifier `tools/fetch_strava.py`, puis lancer le workflow manuellement pour régénérer `docs/data.enc.json`.
- Tester la page en local : ouvrir `docs/index.html` dans un navigateur (le déchiffrement fonctionne sans serveur, mais `fetch` sur un fichier local peut être bloqué : utiliser `python3 -m http.server` dans `docs/`).
- Vérifier sur téléphone (largeur 390 px) : pas de débordement horizontal.
- Pour tester l'interface sans la vraie phrase : générer hors du dépôt des données fictives avec `fetch_strava.compute` / `flags` et `crypto_util.encrypt_json` (phrase de test), les servir à côté d'une copie de `index.html`. Ne jamais commiter ces fichiers.

## Commandes utiles

```zsh
# Environnement local
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Chiffrer le plan (phrase saisie sans être enregistrée dans l'historique)
read -s "DASH_PASSPHRASE?Phrase de passe : "; echo
export DASH_PASSPHRASE
python tools/encrypt_plan.py
unset DASH_PASSPHRASE

# Prévisualiser
cd docs && python3 -m http.server 8000
```

## Limites connues

- Le refresh token Strava peut tourner. Le script loggue un avertissement mais ne met pas à jour le secret. En cas d'échec d'authentification dans le workflow, régénérer le refresh token et mettre à jour `STRAVA_REFRESH_TOKEN`.
- Le dépôt est public : le code et les fichiers chiffrés sont lisibles, pas les données. La sécurité repose entièrement sur la longueur de la phrase de passe (recommandation : diceware 6 mots minimum).
- Les seuils TSB et les indicateurs sont indicatifs (proxy RE).
- La puissance réelle n'est pas issue de Strava pour toutes les sorties : la FTP de référence est estimée, non mesurée.
- Sans jeton GitHub, les éditions du plan restent dans le navigateur. Avec un jeton, « Enregistrer » les commite ; GitHub Pages sert la nouvelle version après environ une minute.
- Coach : quotas de l'offre gratuite Gemini faibles et variables (erreur 429 affichée). Changer de modèle dans les réglages si besoin.
