# Dashboard saison cycliste (Strava → GitHub Pages, chiffré)

Page HTML statique, mise à jour chaque jour par GitHub Actions depuis l'API Strava. Les données sont chiffrées : la page ne les affiche qu'après saisie de la phrase de passe.

URL : https://mathis-ghs.github.io/dashboard/

## Arborescence

```
.github/workflows/update.yml   Cron quotidien (05:00 UTC = 07:00 Paris) + workflow_dispatch (aussi lancé par le bouton #refresh)
docs/index.html                Page unique : déchiffrement WebCrypto, rendu, plan éditable et enregistrable, coach IA
docs/data.enc.json             Données Strava chiffrées (généré par fetch_strava.py, commit du bot)
docs/plan.enc.json             Plan chiffré : commité depuis la page (API GitHub) ou par encrypt_plan.py
docs/bibliotheque.enc.json     Bibliothèque d'entraînement chiffrée (encrypt_bibliotheque.py)
docs/biblio/*.bin              Illustrations des exercices, chiffrées une à une (clé dans la bibliothèque)
docs/garmin.enc.json           Données santé Garmin chiffrées (phrase), générées par fetch_garmin.py
state/garmin_tokens.enc.json   Jetons Garmin chiffrés avec GARMIN_TOKEN_KEY (pas la phrase), réécrits par le bot quand ils tournent
tools/fetch_strava.py          Strava → métriques → chiffrement → docs/data.enc.json
tools/fetch_garmin.py          Garmin Connect → docs/garmin.enc.json (historique fusionné, 7 derniers jours relus)
tools/garmin_login.py          Connexion Garmin locale (MFA), crée private/garmin.key et state/garmin_tokens.enc.json
tools/encrypt_plan.py          private/plan.json → docs/plan.enc.json
tools/encrypt_bibliotheque.py  private/bibliotheque.json + private/livre/images → docs/bibliotheque.enc.json + docs/biblio/
tools/decrypt_plan.py          docs/plan.enc.json → private/plan.json (à lancer avant toute édition locale)
tools/crypto_util.py           AES-GCM, PBKDF2-SHA256, utilisé par les scripts Python
requirements.txt               requests==2.34.2, cryptography==43.0.3, garminconnect==0.3.19
private/plan.json              Plan source, git-ignoré, JAMAIS commité
private/garmin.key             Clé des jetons Garmin (= secret GARMIN_TOKEN_KEY), git-ignorée
private/bibliotheque.json      Bibliothèque source (générée), git-ignorée
private/livre/                 Livre « The Science of Cycling » (md, pages), build_bibliotheque.py, images réduites, img.key : git-ignoré
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

## Garmin Connect (santé)

- Pas d'API officielle pour les particuliers : bibliothèque non officielle `garminconnect` (jetons DI, plus de garth). Garmin peut casser l'accès : l'étape du workflow a `continue-on-error`, la mise à jour Strava passe quand même. Étape ignorée sans secret `GARMIN_TOKEN_KEY` ou sans `state/garmin_tokens.enc.json`.
- Mise en place : `python tools/garmin_login.py` (email, mot de passe, MFA, jamais enregistrés), `gh secret set GARMIN_TOKEN_KEY < private/garmin.key`, commit de `state/garmin_tokens.enc.json`. Premier run : 180 jours d'historique (`GARMIN_BACKFILL`), puis 7 jours relus par run (`GARMIN_DAYS`), 400 jours conservés (`GARMIN_KEEP`). Si l'authentification échoue (refresh token expiré), relancer `garmin_login.py` et commiter le fichier de jetons.
- Jetons chiffrés avec une clé aléatoire distincte de la phrase (`encrypt_with_key` dans `crypto_util.py`, format `{v, iv, ct}`) : la phrase ne donne pas accès au compte Garmin.
- `docs/garmin.enc.json` : `{generated, days: [...]}`, un objet par jour (clés absentes si pas de donnée) : `steps`, `floors`, `kcal`, `kcal_act`, `rhr`, `stress`, `bb_max`, `bb_min`, `bb_wake`, `spo2`, `spo2_min`, `resp`, `sleep_h`, `deep_h`, `rem_h`, `light_h`, `awake_h`, `sleep_score`, `hrv`, `hrv_7d`, `hrv_status`, `hrv_lo`, `hrv_hi`, `vo2`, `vo2_bike`, `weight` (kg), `fat` (%). Convention Garmin : sommeil, VFC, FC repos et `bb_wake` du jour J = nuit qui précède J.
- Page : `HEALTH`, `H_BY_DAY` (dans `indexData`), `HM` (indicateurs du graphe), `hBase` (moyenne 28 j), `hNight`, `hLatest`, `recoveryOf` (feu : VFC basse 2 pts, déséquilibrée 1, FC repos +5 bpm 2 / +3 bpm 1, sommeil score < 60 ou < 6 h 1, Body Battery réveil < 30 1 ; rouge ≥ 3), `isHard` (séance intense d'après la fiche ou le titre). Carte `#recCard` (`renderRecovery`, sous `#today`) et graphe `#chartHealth` (`renderHealthChart`, indicateur `#healthSeg` mémorisé dans `localStorage["healthMetric"]`, période `RANGE`). Les deux sont masqués sans données Garmin. Effacés au verrouillage.
- Coach : `healthContext` ajoute `sante_garmin` (28 jours, 14 en compact) ; consignes dans `COACH_SYS`.

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
- Six onglets (`showTab`, routage par hash `#apercu`, `#plan`, `#coach`, `#bibliotheque`, `#activites`, `#notes`). Sur mobile (< 640 px), la barre d'onglets passe en bas d'écran.
  - Aperçu : `#today` (séance du jour, prochaine séance, semaine en cours avec 7 pastilles et écart au plan : prévu à date, réalisé, écart, compte des séances), `#kpis` (CTL/ATL/TSB avec variation sur 7 j, jauge TSB, volume), `#chartForm` (CTL/ATL + panneau TSB, période 6 sem./3 mois/6 mois), `#chartWeeks` (heures par semaine empilées par sport, cible du plan).
  - Plan : `#plan` en lecture par défaut, bouton `#editPlan` pour passer en édition (séances, objectif et cible de chaque semaine, ajout et suppression de semaines). `#draftBar` apparaît quand le brouillon local diffère du plan enregistré, avec `#savePlan` (commit GitHub), `#resetPlan`, `#exportPlan`.
  - Coach : chat `#chat`, saisie `#coachForm` (voir « Coach IA »).
  - Biblio : `#libSeg` (Vélo, Renfo, Étirements, Exercices, Programmes, Principes), `#libPhase`, `#libSearch`, liste `#lib`, fiche `#libDlg` (voir « Bibliothèque »).
  - Activités : filtres `#sportSeg` et `#actSearch`, liste `#acts` groupée par semaine avec lien vers Strava, `#quality`.
  - Notes : `#rules`, `#analysis`.
- Fonctions de rendu : `renderToday`, `renderKpis`, `renderCharts` (`renderFormChart`, `renderWeeksChart`, survol + clavier), `renderPlan`, `renderRules`, `renderAnalysis`, `renderQuality`, `renderActivities`, orchestrées par `renderAll`. `indexData` construit `BY_DAY` et `WEEKS` (heures par semaine et par sport) à partir de `DATA.activities`.
- Plan : `actualFor` et `statusFor` comparent le planifié au réalisé par date et sport (`findSession`, `sessionRow`). Une séance `other` ne compte que les activités hors vélo et course.
- Édition du plan : brouillon dans `localStorage` (`loadDraft`, `saveDraft`), local au navigateur, supprimé s'il redevient identique au plan chiffré. Suppression de séance annulable via le toast. Bouton d'export `#exportPlan` qui produit un `plan.json`.
- Préférences par navigateur dans `localStorage` : `theme` (auto/clair/sombre), `range` (période du graphe de charge). La phrase de passe n'est jamais stockée : elle reste en mémoire le temps de la session, `#lock` l'efface.
- Réglages (`#settingsDlg`, `openSettings`) : jeton GitHub, dépôt, fournisseur du coach (`#coachProv`), clé et modèle Gemini, Groq ou OpenAI (`#groqKey`, `#openaiKey`, etc.). Stockés dans `localStorage["secrets"]`, chiffrés avec la phrase (`loadSecrets`, `storeSecrets`, même format que les fichiers chiffrés).

## Bibliothèque d'entraînement (livre)

- Source : « The Science of Cycling » (David Bailey). Contenu reformulé en français pour un usage personnel. Le livre lui-même reste dans `private/livre/`, jamais commité, jamais en clair dans `docs/`.
- `private/livre/build_bibliotheque.py` génère `private/bibliotheque.json` : `zones` (Z1-Z6 en % FTP), `principes` (thème, titre, texte, source), `seances` (id, categorie velo/test/renfo/etirement, structure en blocs, progression, phases, intensite, composee), `exercices` (exécution, dosage, variantes, images), `programmes` (7 plans jour par jour, chaque jour lié à une séance type). `private/livre/alttext.txt` = descriptions accessibles de l'EPUB (`OEBPS/xhtml/AltText.xhtml` converti en texte) ; le tableau cyclocross est transcrit à la main dans le script (description EPUB erronée).
- Séances `composee: true` : assemblées à partir du livre, pas telles quelles dans le texte (tempo, test FTP, routines d'étirement).
- Chiffrement : bibliothèque comme le plan (phrase). Images : AES-GCM avec une clé aléatoire `private/livre/img.key`, transmise dans la bibliothèque chiffrée (`img_key`) ; format `iv || ct`, nom = HMAC(clé, nom) tronqué. Une image déjà présente n'est pas réécrite.
- Page : `loadLib` (une fois par session), `libImage` (déchiffrement à la demande, URL blob en cache), `clearLib` au verrouillage. Rendu : `renderLib`, `openFiche` (`ficheSeance`, `ficheExercice`, `ficheProgramme`, pile `LIB_STACK` pour le retour), profil d'intensité `profile` / `profHTML`.
- « Ajouter au plan » depuis une fiche : `sessionFromTemplate` (titre, durée, consigne, `type`, `sport`) avec un champ `model` = id de la séance. Le plan affiche un lien « Fiche » (`ficheLink`) dans l'Aperçu et le Plan.
- Couleurs des zones : variables `--z1` à `--z6` (clair et sombre).

## Enregistrement du plan depuis la page

- `savePlan` chiffre le plan dans le navigateur (`encrypt`) et commite `docs/plan.enc.json` via l'API GitHub contents (`gh`). Jeton « fine-grained » limité au dépôt, permission Contents en lecture et écriture.
- Avec un jeton, `fetchPlanBlob` lit le plan sur l'API GitHub plutôt que sur GitHub Pages (qui met environ une minute à se mettre à jour).
- `docs/plan.enc.json` devient la référence : `private/plan.json` peut être en retard. Avant une édition locale : `git pull`, puis `tools/decrypt_plan.py`, puis éditer, puis `encrypt_plan.py`.
- Le workflow fait `git pull --rebase` avant de pousser `data.enc.json`, pour ne pas échouer si le plan a été commité entre-temps.
- Bouton `#refresh` avec un jeton : `syncStrava` déclenche le workflow `update.yml` (API `workflow_dispatch`, permission Actions en lecture et écriture), suit le run jusqu'à la fin (4 min au plus), puis `loadData` relit `data.enc.json` via l'API GitHub (`fetchRepoBlob`). Sans jeton ou en cas d'échec, simple relecture des fichiers publiés. Le workflow a un groupe `concurrency` : un seul run à la fois.

## Coach IA

- Trois fournisseurs au choix (`SECRETS.prov`, `provOf`), appelés directement depuis le navigateur via `llm` :
  - Gemini (offre gratuite Google AI Studio) : `gemini`, endpoint `generateContent`. Modèles listés dynamiquement (`loadModels`), le Flash non Lite le plus récent par défaut.
  - Groq (console.groq.com) et OpenAI (platform.openai.com, API payante à l'usage) partagent le format OpenAI : table `OAI` (adresse, filtre `keep` et choix par défaut `pick` des modèles, `compact`, paramètres `extra`), appel `oai`, endpoint `/chat/completions`. L'historique `CHAT` reste au format Gemini et `oaiMessages` le traduit à chaque appel (`functionCall` → `tool_calls`, `functionResponse` → messages `tool`). Les schémas d'outils sont convertis par `OAI_TOOLS` (`lowerTypes`). Modèles listés par `loadOaiModels`. Groq : sans audio, modération ni « compound », Llama 4 Scout puis GPT-OSS 120B par défaut. OpenAI : modèles de conversation sans versions datées, le « gpt-N-mini » le plus récent par défaut, pas de température (refusée par les modèles de raisonnement), contexte complet, erreur de crédit (`insufficient_quota`) expliquée. Les limites gratuites se comptent en tokens par minute : Groq (`compact: true`) reçoit un contexte compact (`coachContextCompact`, environ 5 000 tokens au lieu de 13 000) avec 4 semaines de détail, des données en colonnes, le plan à partir de la semaine précédente, une seule analyse et un catalogue abrégé (`libContext(true)`, titres des principes seulement). Le détail passe par `consulter_bibliotheque`, qui accepte aussi l'id `"principes"`. Sur une erreur 429, nouvelle tentative après le délai `retry-after`, deux fois au plus. Certains modèles refusent les outils : « Vérifier et enregistrer » le teste par un mini-appel (`checkTools`) et l'erreur est expliquée (`NO_TOOLS`).
  - Changer de fournisseur remet la conversation à zéro.
- En gratuit, Google peut utiliser les échanges pour entraîner ses modèles. Choix de l'utilisateur, valable pour les deux fournisseurs : `coachContext` n'envoie jamais les noms d'activités, les heures de départ ni les identifiants Strava (lieux et horaires). Ne pas ajouter ces champs.
- Contexte envoyé une fois en tête de conversation : résumé de charge, 8 semaines de charge quotidienne et d'activités, 16 semaines de volume, plan complet (ids de séances, `modele`, statut, réalisé), règles, 3 dernières analyses, et `bibliotheque` (`libContext` : zones, principes, catalogue compact des séances avec progressions, liste des exercices, résumé des programmes).
- `COACH_SYS` : le livre est la base de la méthode (priorité : règles de l'athlète, puis le livre, puis règles générales). Chaque séance proposée doit venir du catalogue (`modele` + `variante`).
- Outil `consulter_bibliotheque(id)` : fiche complète (séance, exercice sans images, programme jour par jour), répondu automatiquement par la page (`libLookup`, boucle `coachRun`, 5 consultations d'affilée maximum).
- Outil `proposer_modifications_plan` (opérations `modifier_seance`, `ajouter_seance`, `supprimer_seance`, `modifier_semaine`, `ajouter_semaine`, `ajouter_analyse` ; champs `modele` et `variante` pour préremplir depuis une fiche). `applyOps` les applique sur une copie et produit un diff ; l'utilisateur accepte ou refuse (`showProposal`), puis la réponse de l'outil est renvoyée au modèle. Rien n'est enregistré sur GitHub sans clic sur « Enregistrer ».
- Conversation gardée en mémoire seulement (`CHAT`), effacée au verrouillage.
- Couleurs des graphes : variables `--ctl`, `--atl`, `--tsb`, `--bike`, `--run`, `--other`, validées pour le daltonisme en clair et en sombre. Les changer avec précaution.
- Le HTML est un fichier unique : CSS et JS inline, pas de build, pas de dépendance externe.

## Direction artistique

- Inspiration : dashboard « Lector » (Dribbble) pour la palette, keynote / apple.com pour la typographie, l'espace et le mouvement. Onglets en haut (barre iOS en bas sur mobile), pas de menu latéral.
- Logo : symbole SVG `#i-logo` (A + V rouges néon sur fond noir), classes `.mark` / `.mark.lg`, favicon SVG inline, `docs/favicon-32.png` et `docs/favicon-96.png` (Safari ignore le SVG), `docs/apple-touch-icon.png`. Le logo reste rouge néon quelle que soit la palette.
- Jetons dans `:root` : neutres (`--bg`, `--fg`, `--fg2`, `--mut`, `--card`, `--line`, `--soft`), accent rose `--acc` / `--grad` / `--glow`, `--navy` ; cartes KPI `--g1` (cyan, forme/CTL), `--g2` (ambre, fatigue/ATL), `--g3` (violet, fraîcheur/TSB), `--g4` (rose, volume), chacune avec son encre `--gN-ink` (bleu nuit sur cyan et ambre, blanc sur violet et rose) ; rayons `--r-sm` / `--r` / `--r-lg` / `--r-pill` ; espacements `--sp-1` à `--sp-8` ; ombres `--sh-1`, `--sh-2`, `--kpi-sh` ; typographie `--font`, `--font-d`, `--fs-hero`, `--fs-h1`, `--fs-h2`, `--track-hero`, `--track-h` ; mouvement `--ease` (cubic-bezier(.22,1,.36,1)), `--dur`, `--dur-fast` ; `--tap` (44 px).
- Contrastes vérifiés AA (texte secondaire, accent, texte des cartes KPI) en clair et en sombre. Les vérifier à nouveau si une teinte change.
- Sombre : les jetons sombres sont déclarés deux fois (media query et `[data-theme="dark"]`). Le second sélecteur inclut `.keynote` : la porte d'entrée (`#gate`) et la séance du jour (`#today`) sont sombres dans les deux thèmes.
- Composants : boutons en pilule (`.btn`, `.btn.primary` en dégradé), lien secondaire `.more-link` (« › »), en-têtes d'onglet `.page-h` / `.eyebrow` / `.page-title` / `.page-sub`, grille de 12 colonnes `.ov-grid` (8 + 4).
- Navigation : `.top` translucide (saturate(180%) blur(20px)), classe `.compact` au-delà de 24 px de défilement (logo réduit, sous-titre masqué). La variable `--scroll` alimente la parallaxe du halo de `#today` ; `--px` / `--py` celle de `.gate-glow`.
- Mouvement : entrée décalée des enfants de `.panel` à l'affichage d'un onglet (`@keyframes rise`), apparition au défilement via `reveal()` (classes `.rv` / `.rv.in`, IntersectionObserver). `reveal()` ne masque que les blocs sous la ligne de flottaison, au changement d'onglet : un nouveau rendu crée des éléments visibles d'emblée. `prefers-reduced-motion` coupe tout.

## Format de `private/plan.json`

Clés de premier niveau : `updated`, `season`, `rules`, `weeks`, `analysis`. Séance : `id`, `date`, `sport`, `type`, `title`, `duration_min`, `notes`, `skip` (optionnel), `model` (optionnel, id d'une séance de la bibliothèque). Les textes de `analysis` sont rendus en paragraphes (séparés par des lignes vides), le HTML est échappé.

Édition locale : `git pull`, `python tools/decrypt_plan.py` (le plan a pu être modifié depuis la page), éditer, `python tools/encrypt_plan.py`, puis commit de `docs/plan.enc.json`.

## Règles pour les modifications

- Ne jamais commiter `private/`, `HANDOFF.md`, `.venv/`, ni de phrase de passe, de client secret, de refresh token ou d'access token (les jetons Garmin ne sont commités que chiffrés, dans `state/`).
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

# Bibliothèque : régénérer puis chiffrer (même phrase, saisie sans historique)
python private/livre/build_bibliotheque.py
python tools/encrypt_bibliotheque.py      # puis commit de docs/bibliotheque.enc.json et docs/biblio/

# Prévisualiser
cd docs && python3 -m http.server 8000
```

## Limites connues

- Le refresh token Strava peut tourner. Le script loggue un avertissement mais ne met pas à jour le secret. En cas d'échec d'authentification dans le workflow, régénérer le refresh token et mettre à jour `STRAVA_REFRESH_TOKEN`.
- Le dépôt est public : le code et les fichiers chiffrés sont lisibles, pas les données. La sécurité repose entièrement sur la longueur de la phrase de passe (recommandation : diceware 6 mots minimum).
- Les seuils TSB et les indicateurs sont indicatifs (proxy RE).
- La puissance réelle n'est pas issue de Strava pour toutes les sorties : la FTP de référence est estimée, non mesurée.
- Sans jeton GitHub, les éditions du plan restent dans le navigateur. Avec un jeton, « Enregistrer » les commite ; GitHub Pages sert la nouvelle version après environ une minute.
- Coach : quotas des offres gratuites Gemini et Groq faibles et variables (erreur 429 affichée, relancée automatiquement pour Groq et OpenAI). OpenAI demande du crédit prépayé. Changer de modèle ou de fournisseur dans les réglages si besoin.
