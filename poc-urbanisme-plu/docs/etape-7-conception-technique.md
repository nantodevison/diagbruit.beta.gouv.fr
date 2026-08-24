# Étape 7 — Conception technique : insertion automatisée dans Strapi et Notion

*Document de cadrage technique, faisant suite à `etape-7-stockage-diagbruit.md` (tous les points ouverts y sont tranchés) et à `etape-6-conception-technique.md`. Version issue des échanges du 24/08/2026.*

## Posture

Même sous-dossier du même POC que les étapes 1 à 6 (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, isolé du reste du produit, preuve de concept plutôt que composant prêt à intégrer.

**Écart majeur par rapport aux étapes précédentes** : c'est la première étape qui écrit dans des systèmes partagés et visibles par toute l'équipe métier (CMS Strapi préprod, base Notion collective) — jamais anodin comme un fichier `output/` local que seul l'opérateur du POC consulte. Deux conséquences directement dans la conception :
- **`--envoyer` explicite requis pour tout écriture réelle** — sans ce drapeau, `inserer.py` ne fait qu'afficher ce qu'il ferait (voir "Mode dry-run" ci-dessous). C'est le comportement par défaut, pas une option.
- **Premier usage réel limité à une seule entrée**, avec accord explicite de l'opérateur avant toute généralisation à un département complet (voir "Prochaine étape").

## Architecture des dossiers

```
poc-urbanisme-plu/
├── etape6_mise_en_forme/                  # existant
├── etape7_stockage/
│   ├── __init__.py                        # vide, comme les modules précédents
│   ├── client_strapi.py                   # aide partagée : créer/mettre à jour une entrée noisezone-alert
│   ├── client_notion.py                   # aide partagée : créer/mettre à jour une page + upload de la géométrie
│   └── inserer.py                         # phase unique — lit etape6_{dept}_export.csv + etape6_{dept}_geometries/
└── output/
    ├── etape6_{dept}_export.csv
    ├── etape6_{dept}_geometries/
    ├── etape7_{dept}_insertions.csv       # journal des créations/mises à jour, jamais relu (voir "Idempotence")
    └── etape7_{dept}_erreurs.csv          # échecs isolés, si non vide
```

Étape à phase unique, comme l'étape 6. Usage, depuis `poc-urbanisme-plu/` :

```
python -m etape7_stockage.inserer --dept 033
# → dry-run : liste ce qui serait créé/mis à jour, sur Strapi et Notion, sans rien envoyer

python -m etape7_stockage.inserer --dept 033 --envoyer
# → exécute réellement les créations/mises à jour
```

## Phase unique — Insertion (`inserer.py`)

Lit `etape6_{dept}_export.csv` (une ligne par géométrie finale, `alert_slug_propose` portant la valeur finale saisie via `outil_validation.html`) et le fichier `.geojson` correspondant dans `etape6_{dept}_geometries/`. Pour chaque ligne :

1. **Recherche de l'entrée existante** (voir "Idempotence" ci-dessous) : interroge Strapi et Notion par `alert_slug` pour savoir si une entrée existe déjà de chaque côté.
2. **Strapi** (`client_strapi.py`) — construit le payload à partir des colonnes déjà granulaires de l'étape 6 (voir `etape-6-conception-technique.md`, "Contrat de données") :
   - `alert_slug` ← `alert_slug_propose`
   - `content` ← `message_content`, encapsulé dans un unique `<p>...</p>`, chaque `\n` remplacé par `<br>` (validé le 24/08/2026 — voir "Conversion HTML" ci-dessous)
   - `source` ← `strapi_source`
   - `reference` ← `strapi_reference`
   - `label` ← `label_propose`
   - `title` ← `titre_propose` (ajouté le 24/08/2026, voir `etape-5-ameliorations-possibles.md`, "Génération LLM d'un titre court à l'étape 5" — désormais implémenté ; titre court généré par LLM à l'étape 5, validé par l'opérateur). `alert_slug` (champ `uid`, `targetField: title` côté schéma Strapi) continue d'être fourni explicitement dans le payload plutôt que dérivé de `title`.
   - Absent : création — `POST {STRAPI_URL}/api/noisezone-alerts`, corps `{"data": {...}}`. Déjà présent : mise à jour — `PUT {STRAPI_URL}/api/noisezone-alerts/{documentId}` (Strapi 5 — identifiant `documentId`, une chaîne, pas l'`id` numérique — confirmé le 24/08/2026 sur une lecture réelle), `documentId` obtenu par la recherche de l'étape 1.
   - Entrée créée **en brouillon** (`draftAndPublish` actif sur ce content-type, jamais publiée automatiquement par le script) — l'opérateur relit et publie manuellement dans Strapi. **Nécessite `?status=draft` en paramètre de requête sur le `POST`/`PUT`** — voir "Piège : publication automatique" ci-dessous, sans quoi ce n'est pas vrai.
3. **Notion** (`client_notion.py`) :
   - Upload de la géométrie : `POST /v1/file_uploads` avec le fichier renommé `{id_geometrie}.json` (`.geojson` refusé par l'API, voir `etape-7-stockage-diagbruit.md`, "Pièce jointe géométrie") et `content_type: application/json`, puis `POST {upload_url}` en `multipart/form-data`.
   - Absent : création (`POST /v1/pages`, `parent` = `{"type": "data_source_id", "data_source_id": ...}` — voir "Migration data_sources" ci-dessous). Déjà présent (`page_id` obtenu à l'étape 1) : mise à jour (`PATCH /v1/pages/{page_id}`, inchangé par la migration). Champs : `Territoire` ← `territoire_propose`, `Description` ← `titre_propose` (même source que `title` Strapi ci-dessus, depuis le 24/08/2026 — auparavant calculé par citations), `alert_slug` ← `alert_slug_propose`, `data` ← fichier uploadé (`{"type": "file_upload", "file_upload": {"id": "..."}}`).

### Migration `data_sources` (découverte le 24/08/2026 en testant)

En implémentant `trouver_page_id`, `POST /v1/databases/{NOTION_DATABASE_ID}/query` a échoué (`400 invalid_request_url`), y compris avec un corps vide — ce n'était donc pas un problème de filtre. Cause : depuis la version d'API `2025-09-03`, une base Notion peut contenir plusieurs "sources de données" ; interroger ses lignes et y créer une page se font via un `data_source_id` distinct du `database_id`, qui n'existait pas comme concept séparé avant cette version. `NOTION_DATABASE_ID` reste ce qu'on trouve dans l'URL Notion et ce qui est renseigné dans `.env` — `client_notion.py` traduit cet identifiant en `data_source_id` via `GET /v1/databases/{NOTION_DATABASE_ID}` (champ `data_sources`, premier élément — cette base n'en a qu'un seul), mis en cache pour le reste du run.

Concrètement :
- **Lecture** (`trouver_page_id`) : `POST /v1/data_sources/{data_source_id}/query`, pas `/v1/databases/{id}/query`.
- **Création** (`creer_ou_mettre_a_jour`) : `parent` = `{"type": "data_source_id", "data_source_id": ...}`, pas `{"database_id": ...}`.
- **Mise à jour** (`PATCH /v1/pages/{page_id}`) : inchangée, une page reste identifiée par son propre `id` une fois créée.

Vérifié en réel (lecture seule : `GET /v1/databases/{id}` puis `POST /v1/data_sources/{id}/query`, jamais d'écriture) — la création de page avec ce nouveau `parent` n'a, elle, pas encore été testée en réel (voir "Prochaine étape").

## Piège : publication automatique à la création Strapi (trouvé le 24/08/2026, lors du premier test réel)

**Un `POST`/`PUT` sans le paramètre de requête `status=draft` publie l'entrée immédiatement**, y compris sans jamais passer `publishedAt` dans le corps de la requête — constaté sur une vraie création (`publishedAt` non nul dans la réponse, alors que rien ne le demandait). Il s'agit d'un piège connu de l'API REST de Strapi 5 : le contrôle fiable du statut de brouillon n'est officiellement documenté que côté API interne *Document Service* (`strapi.documents(...).create({..., status: 'draft'})`), inaccessible à un client REST externe comme celui-ci — voir les retours de la communauté Strapi sur ce comportement.

**Contournement vérifié en réel** : passer `status=draft` en paramètre de requête (pas dans le corps JSON) sur `POST` et `PUT` — confirmé en créant une entrée de test entièrement neuve après correctif : `GET .../noisezone-alerts/{documentId}?status=published` renvoie `404` (aucune version publiée n'existe), `GET .../noisezone-alerts/{documentId}?status=draft` renvoie `200` avec `publishedAt: null`. `client_strapi.py` passe désormais systématiquement `status=draft` sur ses deux requêtes d'écriture.

**Conséquence pour le tout premier test (avant le correctif)** : une entrée test (`documentId` `x584txcg22k676qh8n9nxxip`, `alert_slug` `alert-EurometropoledeStrasbourg-test-poc-diagbruit-a-supprimer`) a été publiée par erreur avant que le correctif ne soit en place. Une mise à jour ultérieure (après correctif) a bien créé/mis à jour sa version brouillon, mais **la version publiée reste active** — Strapi 5 traite brouillon et publié comme deux versions distinctes du même document, une mise à jour en `status=draft` ne dépublie pas une version déjà publiée. Aucun moyen trouvé de la dépublier via l'API REST avec les droits du jeton actuel (pas de `delete`, pas d'action `unpublish` documentée pour un token) — **à supprimer manuellement dans l'admin Strapi**, ainsi que la page Notion correspondante et l'entrée de test suivante (`documentId` `ufvocwulxlfman8w0reolbdi`, créée proprement après correctif, jamais publiée).
4. **Écriture du journal** (`etape7_{dept}_insertions.csv`) : à chaque création/mise à jour réussie, une ligne est ajoutée (`documentId` Strapi, `page_id` Notion) — purement un journal de traçabilité pour l'opérateur, jamais relu par le script (voir "Idempotence").

## Idempotence — recherche à chaque exécution (révisé le 24/08/2026)

*Conception initiale (`etape-7-stockage-diagbruit.md`) : recherche Strapi via l'API avant d'écrire. Écartée temporairement le 24/08/2026 quand le jeton fourni s'est révélé sans droit `find`/`findOne` (403 sur toute lecture) — solution de repli envisagée alors : tout faire reposer sur un fichier de suivi local. **Le jeton a été corrigé le jour même** (capture d'écran, droits `find`/`findOne`/`create`/`update` désormais tous accordés) et revérifié en réel (`GET .../noisezone-alerts?filters[alert_slug][$eq]=...` renvoie l'entrée avec son `documentId`, ou une liste vide si elle n'existe pas) — la conception initiale, plus simple et plus robuste, est donc rétablie.*

- **Strapi** : avant toute écriture, `GET {STRAPI_URL}/api/noisezone-alerts?filters[alert_slug][$eq]={valeur}` — une entrée trouvée donne son `documentId` pour la mise à jour, une liste vide déclenche une création.
- **Notion** : `POST /v1/databases/{NOTION_DATABASE_ID}/query`, filtre `alert_slug` (propriété `rich_text`) égal à la valeur — même logique.

**Piège trouvé en production, corrigé le 24/08/2026 — 19 doublons créés sur Strapi** : la recherche ci-dessus, telle quelle, ne précise pas de paramètre `status`. Or une requête Strapi sans ce paramètre ne cherche par défaut que parmi les entrées **publiées** — et ce script ne crée jamais que des brouillons (voir "Piège : publication automatique" ci-dessus). Conséquence, découverte lors du premier passage réel sur un département complet (28 géométries, interrompu par un timeout après 19 lignes, puis relancé) : la recherche n'a jamais trouvé les 19 entrées déjà créées au premier passage, chacune s'est donc vu créer un **second document Strapi avec le même `alert_slug`** — la contrainte d'unicité du champ `uid` ne s'applique apparemment pas entre deux brouillons distincts. Notion n'a pas ce problème (pas de notion de statut brouillon/publié sur une ligne de base de données) — vérifié en réel, aucun doublon Notion.

**Correctif vérifié en réel** : `trouver_document_id` cherche désormais explicitement `status=draft` puis, si rien n'est trouvé, `status=published` (utile si une entrée a été publiée par un opérateur entre deux passages — brouillon et publié peuvent légitimement coexister pour un même `documentId`). Revérifié en relançant `inserer.py --envoyer` sur les 28 lignes du même département : les 28 sont passées en mise à jour, aucun nouveau doublon.

**Nettoyage restant** (jeton sans `delete`, à faire manuellement dans l'admin Strapi) : 19 `alert_slug` ont chacun deux `documentId` — contenu identique dans les deux (mêmes données sources), mais **à conserver** est celui que `inserer.py` a effectivement mis à jour lors de la dernière exécution (vérifié directement dans les logs, pas déduit d'un ordre supposé — l'ordre renvoyé par l'API n'est pas garanti, une première version de cette table s'était trompée sur 4 lignes en le supposant) :

| `alert_slug` | À conserver | **À supprimer** |
|---|---|---|
| ...-universite | `o4uv4vb4y9zhnjemg4qax6kk` | `hk99sfc1u111amlk3985q5gh` |
| ...-cathedrale | `tkxya80ytbbs1zah3onzwqey` | `u48rzoify8hnb29h1mu5j3hr` |
| ...-autorisation-spr | `usbcrbfitrbbcckinf00ixiy` | `il6ogjsqs1kkej0pzt3siqhc` |
| ...-vlio | `u9f042kdpk3gy4c987q54ogr` | `gzc5cxdwufw75ledajbv6kxm` |
| ...-Marechaux | `co43lb77u1r1uhoanlwd409g` | `pw3b78uwjyx1k9hymgns4eq8` |
| ...-Floralies | `q1h0ii3yn91ehqxa3b4k1o4p` | `q2pyw2w6rqyh8av786p7c0ok` |
| ...-ostwald | `s9st2hflbkmkxlordo0kq56t` | `r0g7om1hz2q075gqwpml4u97` |
| ...-secteur-nord-reichstett | `c2gmmuca1hm2kkksnxf0ztlf` | `wkkdf5p77zmm37r2mqof5bha` |
| ...-Souffel | `ow5ni6k3aqrhhu9v6huq1spn` | `xvnskgwdwu53eorvjqasc9s1` |
| ...-souffel-ii | `l1whgml7q9gldd1fcczsfq1s` | `a5hvdn21lpeguh7nvoqdvtfc` |
| ...-Hirschberg | `a0peast6gmo0m5ohvw07sx6m` | `iijtp1jfps0t0pwiipm0rtbd` |
| ...-etoile-ilot | `ynq1kpsz08dgng27l2myaydp` | `s4doorzx5eigglv1vghhxhny` |
| ...-Heyritz | `fflbavno9y062t16xaqpufjo` | `veo4yc6d4gveyl3un3824o9h` |
| ...-Musau-Neudorf | `o10zlha8wgvkpiaqy9pzq28j` | `zpa62x1o65d691fk13dtzf1i` |
| ...-Romains | `tgfi9mep5biq7jt0yf9qsopx` | `tyidru6ke3jsz2giped10n50` |
| ...-Petit-Marais | `ctfoa0yiv8tg1aga735iw6v9` | `rd3twk37j1rcbrxkmpshq6ed` |
| ...-Epsan | `ae132fmlgi2en798udouob77` | `gp8jw8ueoume3ftpviws0c7m` |
| ...-air-bruit | `b58uasc9z98hersp4eljd6er` | `xtj3can5840u1irird1pden3` |
| ...-route-entzheim | `vb7mrnitm1nz0ws3xdzv60hs` | `dbnm3elkpmh1ti4ihhzx1wzf` |

Les 9 dernières géométries du département (`ecran-equipement-festif`, `deux-rives`, `Huron`, `recul-30m`, `zone-commerciale-nord`, `Schwemmloch`, `Trissermatt`, `Niedermatt`, `paysage-a35`) n'ont, elles, jamais été dupliquées — créées une seule fois, après correctif.

**Précision utile** : l'ordre renvoyé par Strapi pour une paire de doublons n'est pas stable d'un appel à l'autre (revérifié : un dry-run ultérieur a retrouvé l'autre `documentId` de la paire que celui utilisé lors de la dernière mise à jour réelle). Sans conséquence tant que les doublons ne sont pas nettoyés — le contenu est strictement identique dans les deux entrées de chaque paire (mêmes données sources, aucune modification entre les deux créations) — supprimer l'un ou l'autre des deux `documentId` d'une paire est donc équivalent, la colonne "à conserver"/"à supprimer" ci-dessus n'est qu'un choix arbitraire pour ne pas avoir à décider.
- **`etape7_{dept}_insertions.csv` n'est plus qu'un journal** (voir "Contrat de données") : jamais relu par le script, la source de vérité est systématiquement l'état réel de Strapi/Notion au moment de l'exécution — plus robuste qu'un fichier local qui pourrait être perdu, désynchronisé, ou absent sur une autre machine. Utile pour l'opérateur (historique de ce qui a été inséré/mis à jour, et quand), pas pour la logique du script.

**Point de vigilance non résolu** : une mise à jour écrase le contenu existant sans distinguer une entrée encore en brouillon d'une entrée déjà publiée et éventuellement retouchée à la main dans Strapi (ex. `title` ajouté, texte peaufiné après publication) — la recherche par `alert_slug` renvoie bien l'entrée, mais pas nécessairement de quoi juger si elle a été modifiée depuis. Risque accepté pour un premier usage à volume limité ; à revoir si des mises à jour après publication deviennent fréquentes.

## Conversion `content` (texte → HTML)

**Validé le 24/08/2026** : `message_content` (texte brut, retours à la ligne `\n`) devient `content` en l'encapsulant dans un unique `<p>...</p>`, chaque `\n` remplacé par `<br>`. Ni gras, ni listes structurées (`<ul>/<li>`) — la saisie manuelle observée applique du gras sur les citations réglementaires exactes, non reproduit ici (voir `etape-5-ameliorations-possibles.md`, "Pas de mise en forme (gras, listes) capturée lors de la correction manuelle des messages", pour la piste envisagée et pourquoi elle est reportée).

## Mode dry-run

Comportement par défaut de `inserer.py`, sans `--envoyer` : aucune requête d'écriture (`POST`/`PUT`/`PATCH`) n'est faite, ni sur Strapi ni sur Notion — seules les recherches en lecture (voir "Idempotence") sont exécutées, pour afficher un dry-run fidèle. Le script affiche, pour chaque ligne, ce qu'il ferait ("créerait" ou "mettrait à jour {documentId}/{page_id}", d'après la recherche live) — y compris les valeurs exactes des champs qui seraient envoyés, pour permettre une relecture avant tout envoi réel.

## Gestion des erreurs

Même principe que les étapes précédentes : un échec isolé sur une ligne (ex. Strapi ou Notion indisponible, payload rejeté) n'empêche jamais le traitement des autres lignes — tracé dans `etape7_{dept}_erreurs.csv` (supprimé plutôt que laissé vide si rien à signaler). `inserer.py` s'arrête immédiatement si `etape6_{dept}_export.csv` est introuvable, ou si `STRAPI_API_TOKEN`/`STRAPI_URL`/`PERSONNAL_NOTION_TOKEN`/`NOTION_DATABASE_ID` sont absents de l'environnement — rien d'exploitable sans eux.

**Échec partiel Strapi/Notion pour une même ligne** : si l'insertion Strapi réussit mais l'insertion Notion échoue (ou l'inverse), la ligne est tracée en erreur pour la partie échouée. Un second passage n'a besoin d'aucun état local pour ne pas dupliquer la partie déjà réussie : la recherche par `alert_slug` (voir "Idempotence") la retrouve à chaque exécution et ne retente que la partie manquante.

## Contrat de données

`etape7_{dept}_insertions.csv` (journal, une ligne par création/mise à jour réussie — voir "Idempotence" : jamais relu par le script, uniquement pour la traçabilité de l'opérateur) :

| Colonne | Détail |
|---|---|
| `id_geometrie` | reprise de `etape6_{dept}_export.csv`. |
| `alert_slug` | clé de correspondance entre les deux systèmes et avec `etape6_{dept}_export.csv`. |
| `strapi_document_id` | `documentId` Strapi de l'entrée créée ou mise à jour — vide si l'insertion Strapi a échoué. |
| `notion_page_id` | identifiant de page Notion créée ou mise à jour — vide si l'insertion Notion a échoué. |
| `date_traitement` | date de l'écriture (création ou mise à jour) pour cette ligne. |

`etape7_{dept}_erreurs.csv` : mêmes colonnes que les fichiers d'erreurs des étapes précédentes (`identifiant`, `source`, `message`, `date_traitement`) — `source` vaut `strapi` ou `notion` selon le système en échec.

## Dépendances retenues

- `requests` — déjà présent (étape 1), réutilisé pour les appels REST Strapi et Notion.
- `python-dotenv` — déjà présent (étape 2/5), pour charger `STRAPI_API_TOKEN`/`STRAPI_URL`/`PERSONNAL_NOTION_TOKEN`/`NOTION_DATABASE_ID` depuis `.env`.
- Aucune dépendance nouvelle : ni SDK Strapi, ni SDK Notion officiel — REST brut via `requests`, cohérent avec le reste du pipeline (`resolution_territoire.py`, `communes.py`).
- `tenacity` — déjà présent (étape 1), même politique de nouvelle tentative que `resolution_territoire.py`/`communes.py` pour les deux clients.

## Implémenté le 24/08/2026

`etape7_stockage/` (`client_strapi.py`, `client_notion.py`, `inserer.py`) écrit, puis testé en deux temps sur `067-plui-strasbourg` (lignes à `alert_slug` complet simulées pour l'occasion, avec l'accord explicite de l'opérateur pour l'envoi réel) :

1. **Dry-run** : recherche Strapi (`trouver_document_id`) et Notion (`trouver_page_id`, après la migration `data_sources` ci-dessus) toutes deux vérifiées en réel, aucune écriture. Validation d'un `alert_slug` incomplet (terminé par `-`) vérifiée sur les lignes restantes du même export.
2. **Envoi réel (`--envoyer`)**, une géométrie : création Strapi + Notion réussie, contenu relu et vérifié conforme des deux côtés (`content`/`source`/`reference`/`label` côté Strapi, `Territoire`/`Description`/`alert_slug`/géométrie jointe côté Notion). A révélé le piège de publication automatique Strapi (voir section dédiée ci-dessus), corrigé, puis reconfirmé sur une seconde géométrie entièrement neuve : entrée créée sans aucune version publiée.

**Les deux entrées de test ont été nettoyées par l'opérateur le 24/08/2026** (confirmé). Feu vert donné ensuite pour la généralisation au département complet (28 géométries, `alert_slug` réellement saisis via `outil_validation.html`, voir la note du 21→24/08/2026 dans `etape-6-conception-technique.md`, "Reprise à la régénération").

3. **Envoi réel généralisé au département complet** (28 géométries), avec accord explicite : un premier passage s'est arrêté après 19 lignes (timeout de l'outil d'exécution, pas un problème du script) ; le relancer a révélé et causé le bug de doublons Strapi documenté ci-dessus dans "Idempotence" (19 `alert_slug` dupliqués, jamais côté Notion). Corrigé, puis un troisième passage a confirmé : 28/28 lignes en mise à jour, aucune nouvelle erreur, aucun nouveau doublon. **Nettoyage des 19 doublons Strapi restant à faire manuellement** — voir la table dans "Idempotence" ci-dessus (jeton sans `delete`, aucun outil du POC n'a les droits de le faire).

## Prochaine étape

1. Suppression manuelle des 19 doublons Strapi (table dans "Idempotence" ci-dessus).
2. `etape7_067-plui-strasbourg_export.csv` (28 géométries) est désormais réellement inséré/à jour sur Strapi et Notion — département suivant dès qu'un nouveau `etape6_{dept}_export.csv` est prêt (saisie `alert_slug` via `outil_validation.html`, puis `inserer.py --envoyer`).
3. **Amélioration à envisager** (pas bloquante) : le journal `etape7_{dept}_insertions.csv` n'est écrit qu'une fois à la fin du run entier — une interruption en cours de route (comme celle rencontrée ici) ne laisse aucune trace locale des lignes déjà traitées avant l'arrêt, même si les écritures elles-mêmes ont bien eu lieu côté Strapi/Notion. Sans conséquence sur la justesse du résultat (l'idempotence par recherche live rattrape tout au passage suivant, une fois corrigée), mais un journal écrit ligne par ligne donnerait une visibilité immédiate en cas d'interruption plutôt que de découvrir l'état réel a posteriori par une vérification manuelle.
