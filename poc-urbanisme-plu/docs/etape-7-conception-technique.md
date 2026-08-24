# Étape 7 — Conception technique : insertion automatisée dans Strapi et Notion

*Document de conception technique, faisant suite à `etape-7-stockage-diagbruit.md` et à `etape-6-conception-technique.md`.*

## Posture

Même sous-dossier du même POC que les étapes 1 à 6 (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, isolé du reste du produit, preuve de concept plutôt que composant prêt à intégrer.

**Écart majeur par rapport aux étapes précédentes** : c'est la première étape qui écrit dans des systèmes partagés et visibles par toute l'équipe métier (CMS Strapi préprod, base Notion collective) — jamais anodin comme un fichier `output/` local que seul l'opérateur du POC consulte. Conséquence directe dans la conception : **`--envoyer` explicite requis pour toute écriture réelle** — sans ce drapeau, `inserer.py` ne fait qu'afficher ce qu'il ferait (voir "Mode dry-run" ci-dessous). C'est le comportement par défaut, pas une option.

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
    └── etape7_{dept}_erreurs.csv          # échecs isolés, absent si rien à signaler
```

Étape à phase unique, comme l'étape 6. Usage, depuis `poc-urbanisme-plu/` :

```
python -m etape7_stockage.inserer --dept 033
# → dry-run : liste ce qui serait créé/mis à jour, sur Strapi et Notion, sans rien envoyer

python -m etape7_stockage.inserer --dept 033 --envoyer
# → exécute réellement les créations/mises à jour
```

`--output-dir` (défaut `output/`) permet de pointer vers un autre dossier de lecture/écriture que le défaut.

## Phase unique — Insertion (`inserer.py`)

Lit `etape6_{dept}_export.csv` (une ligne par géométrie finale, `alert_slug_propose` portant la valeur finale saisie via `outil_validation.html`) et le fichier `.geojson` correspondant dans `etape6_{dept}_geometries/`. S'arrête immédiatement, avant de traiter la moindre ligne, si `etape6_{dept}_export.csv` ou `etape6_{dept}_geometries/` sont introuvables, ou si `STRAPI_API_TOKEN`/`STRAPI_URL`/`PERSONNAL_NOTION_TOKEN`/`NOTION_DATABASE_ID` sont absents de l'environnement (voir "Gestion des erreurs").

Pour chaque ligne :

1. **Validation de l'`alert_slug`** : une valeur vide, ou encore terminée par `-` (proposition mécanique de `outil_validation.html` jamais complétée par l'opérateur — voir `etape-6-conception-technique.md`), n'est pas exploitable. La ligne est tracée dans `etape7_{dept}_erreurs.csv` (`source` = `validation`) et ni Strapi ni Notion ne sont appelés pour elle.
2. **Strapi** (`client_strapi.py`) — construit le payload à partir des colonnes déjà granulaires de l'étape 6 (voir `etape-6-conception-technique.md`, "Contrat de données") :
   - `alert_slug` ← `alert_slug_propose`
   - `content` ← `message_content`, encapsulé dans un unique `<p>...</p>`, chaque `\n` remplacé par `<br>` (voir "Conversion `content`" ci-dessous)
   - `source` ← `strapi_source`
   - `reference` ← `strapi_reference`
   - `label` ← `label_propose`
   - `title` ← `titre_propose` (titre court généré par LLM à l'étape 5, validé par l'opérateur). `alert_slug` (champ `uid`, `targetField: title` côté schéma Strapi) est fourni explicitement dans le payload plutôt que dérivé de `title`.
   - Recherche préalable (`trouver_document_id`, voir "Idempotence") : absente → création, `POST {STRAPI_URL}/api/noisezone-alerts?status=draft`, corps `{"data": {...}}`. Présente → mise à jour, `PUT {STRAPI_URL}/api/noisezone-alerts/{documentId}?status=draft` (Strapi 5 — `documentId`, une chaîne, pas l'`id` numérique).
   - Entrée créée **en brouillon** (`draftAndPublish` actif sur ce content-type), jamais publiée automatiquement par le script — l'opérateur relit et publie manuellement dans Strapi. Le paramètre de requête `status=draft` sur `POST`/`PUT` est ce qui garantit ce comportement — voir "Piège : publication automatique" ci-dessous.
3. **Notion** (`client_notion.py`) :
   - Upload de la géométrie : `POST /v1/file_uploads` avec le fichier renommé `{id_geometrie}.json` (`.geojson` refusé par l'API, voir `etape-7-stockage-diagbruit.md`, "Pièce jointe géométrie") et `content_type: application/json`, puis `POST {upload_url}` en `multipart/form-data`.
   - Recherche préalable (`trouver_page_id`, `POST /v1/data_sources/{data_source_id}/query` — voir "Sources de données Notion" ci-dessous). Absente → création (`POST /v1/pages`, `parent` = `{"type": "data_source_id", "data_source_id": ...}`). Présente (`page_id`) → mise à jour (`PATCH /v1/pages/{page_id}`).
   - Champs : `Territoire` ← `territoire_propose`, `Description` ← `titre_propose` (même source que `title` Strapi ci-dessus), `alert_slug` ← `alert_slug_propose`, `data` ← fichier uploadé (`{"type": "file_upload", "file_upload": {"id": "..."}}`).
4. **Journal** (`etape7_{dept}_insertions.csv`, uniquement avec `--envoyer`) : une ligne est ajoutée dès qu'au moins un des deux systèmes a été créé ou mis à jour avec succès, écrite et vidée sur disque immédiatement après le traitement de la ligne — pas accumulée en mémoire jusqu'à la fin du run. Une interruption en cours de route (timeout, erreur réseau) laisse donc une trace locale des lignes déjà traitées avant l'arrêt.

Strapi et Notion sont traités indépendamment pour une même ligne : un échec sur l'un n'empêche jamais de tenter l'autre (voir "Gestion des erreurs").

## Sources de données Notion (`data_source_id` vs `database_id`)

Depuis la version d'API Notion `2025-09-03`, une base peut contenir plusieurs "sources de données" ; interroger ses lignes et y créer une page se font via un `data_source_id`, distinct du `database_id` et absent comme concept séparé avant cette version. `NOTION_DATABASE_ID` (dans `.env`) reste l'identifiant visible dans l'URL Notion ; `client_notion._data_source_id()` le traduit en `data_source_id` via `GET /v1/databases/{NOTION_DATABASE_ID}` (champ `data_sources`, premier élément — cette base n'en a qu'un seul), mis en cache pour le reste du run.

- **Lecture** (`trouver_page_id`) : `POST /v1/data_sources/{data_source_id}/query`, pas `/v1/databases/{id}/query` (retiré par cette version de l'API).
- **Création** (`creer_ou_mettre_a_jour`) : `parent` = `{"type": "data_source_id", "data_source_id": ...}`, pas `{"database_id": ...}`.
- **Mise à jour** (`PATCH /v1/pages/{page_id}`) : inchangée — une page reste identifiée par son propre `id` une fois créée, indépendamment de sa base parente.

## Piège : publication automatique à la création Strapi

Un `POST`/`PUT` sans le paramètre de requête `status=draft` publie l'entrée immédiatement sur Strapi 5, y compris sans jamais passer `publishedAt` dans le corps de la requête. Il s'agit d'un comportement connu de l'API REST de Strapi 5 : le contrôle fiable du statut de brouillon n'est officiellement documenté que côté API interne *Document Service* (`strapi.documents(...).create({..., status: 'draft'})`), inaccessible à un client REST externe comme celui-ci. Le contournement retenu — passer `status=draft` en paramètre de requête (pas dans le corps JSON) sur `POST` et `PUT` — est appliqué systématiquement par `client_strapi._post`/`_put`.

**Conséquence directe sur la recherche** (voir "Idempotence" ci-dessous) : comme ce script ne crée jamais que des brouillons, une recherche Strapi qui omettrait le paramètre `status` — qui ne porte par défaut que sur les entrées **publiées** — ne trouverait jamais les entrées déjà créées, et déclencherait une nouvelle création à chaque passage au lieu d'une mise à jour.

## Idempotence

Avant toute écriture, l'étape 7 cherche une entrée/page existante par `alert_slug`, de chaque côté — jamais l'inverse. Une ligne déjà insérée qui est relancée (ex. correction d'un message à l'étape 5, nouvel `etape6_{dept}_export.csv`) met donc à jour l'existant au lieu de dupliquer.

- **Strapi** (`trouver_document_id`) : `GET {STRAPI_URL}/api/noisezone-alerts?filters[alert_slug][$eq]={valeur}&status=draft` puis, si rien n'est trouvé, la même requête avec `status=published` (utile si une entrée a été publiée par un opérateur entre deux passages — brouillon et publié peuvent légitimement coexister pour un même `documentId`, voir "Piège : publication automatique" ci-dessus). Une entrée trouvée donne son `documentId` pour la mise à jour ; aucune des deux recherches ne trouvant rien déclenche une création.
- **Notion** (`trouver_page_id`) : `POST /v1/data_sources/{data_source_id}/query`, filtre `alert_slug` (propriété `rich_text`) égal à la valeur — même logique. Notion n'a pas de notion de statut brouillon/publié sur une ligne de base de données : une seule recherche suffit.

`etape7_{dept}_insertions.csv` n'est qu'un journal de traçabilité pour l'opérateur (voir "Contrat de données") — jamais relu par le script : la source de vérité est systématiquement l'état réel de Strapi/Notion au moment de l'exécution, plus robuste qu'un fichier local qui pourrait être perdu, désynchronisé, ou absent sur une autre machine.

**Limite connue** : une mise à jour écrase le contenu existant sans distinguer une entrée encore en brouillon d'une entrée déjà publiée et éventuellement retouchée à la main dans Strapi — voir `ameliorations-identifiees.md`, "Une mise à jour Strapi écrase le contenu sans détecter une retouche manuelle post-publication".

**Historique** : une première version de la recherche Strapi ne passait pas le paramètre `status`, ce qui a fait recréer en doublon plusieurs dizaines d'entrées déjà existantes avant la correction décrite ci-dessus (recherche en deux temps `draft` puis `published`) — voir `ameliorations-identifiees.md`, "Doublons Strapi résiduels d'un bug d'idempotence désormais corrigé", pour le nettoyage résiduel encore nécessaire côté admin Strapi.

## Conversion `content` (texte → HTML)

`message_content` (texte brut, retours à la ligne `\n`) devient `content` en l'encapsulant dans un unique `<p>...</p>`, chaque `\n` remplacé par `<br>` (`client_strapi.convertir_content_html`). Ni gras, ni listes structurées (`<ul>/<li>`) : la saisie manuelle observée applique du gras sur les citations réglementaires exactes, non reproduit ici — voir `ameliorations-identifiees.md` pour la piste envisagée et pourquoi elle est reportée.

## Mode dry-run

Comportement par défaut de `inserer.py`, sans `--envoyer` : aucune requête d'écriture (`POST`/`PUT`/`PATCH`) n'est faite, ni sur Strapi ni sur Notion — seules les recherches en lecture (voir "Idempotence") sont exécutées, pour afficher un dry-run fidèle à l'état réel. Le script affiche, pour chaque ligne, ce qu'il ferait ("créerait" ou "mettrait à jour {documentId}/{page_id}", d'après la recherche live) — y compris les valeurs exactes des champs qui seraient envoyés, pour permettre une relecture avant tout envoi réel. Aucun fichier n'est écrit dans `output/` en dry-run (ni journal ni fichier d'erreurs).

## Gestion des erreurs

Même principe que les étapes précédentes : un échec isolé sur une ligne (ex. Strapi ou Notion indisponible, payload rejeté, `alert_slug` incomplet) n'empêche jamais le traitement des autres lignes — tracé dans `etape7_{dept}_erreurs.csv` (supprimé plutôt que laissé vide si rien à signaler). `inserer.py` s'arrête immédiatement, avant de traiter la moindre ligne, si `etape6_{dept}_export.csv` ou `etape6_{dept}_geometries/` sont introuvables, ou si `STRAPI_API_TOKEN`/`STRAPI_URL`/`PERSONNAL_NOTION_TOKEN`/`NOTION_DATABASE_ID` sont absents de l'environnement — rien d'exploitable sans eux.

**Échec partiel Strapi/Notion pour une même ligne** : si l'insertion Strapi réussit mais l'insertion Notion échoue (ou l'inverse), la ligne est tracée en erreur pour la partie échouée, et journalisée pour la partie réussie (une ligne est journalisée dès qu'au moins un des deux identifiants est obtenu — voir "Phase unique" ci-dessus). Un second passage n'a besoin d'aucun état local pour ne pas dupliquer la partie déjà réussie : la recherche par `alert_slug` (voir "Idempotence") la retrouve à chaque exécution et ne retente que la partie manquante.

## Contrat de données

`etape7_{dept}_insertions.csv` (journal, une ligne par création/mise à jour réussie d'au moins un système — voir "Idempotence" : jamais relu par le script, uniquement pour la traçabilité de l'opérateur) :

| Colonne | Détail |
|---|---|
| `id_geometrie` | reprise de `etape6_{dept}_export.csv`. |
| `alert_slug` | clé de correspondance entre les deux systèmes et avec `etape6_{dept}_export.csv`. |
| `strapi_document_id` | `documentId` Strapi de l'entrée créée ou mise à jour — vide si l'insertion Strapi a échoué. |
| `notion_page_id` | identifiant de page Notion créée ou mise à jour — vide si l'insertion Notion a échoué. |
| `date_traitement` | date de l'écriture (création ou mise à jour) pour cette ligne. |

`etape7_{dept}_erreurs.csv` : mêmes colonnes que les fichiers d'erreurs des étapes précédentes (`identifiant`, `source`, `message`, `date_traitement`) :
- `source` vaut `strapi` ou `notion` pour un échec d'appel API — `identifiant` porte alors l'`alert_slug` ;
- `source` vaut `validation` pour un `alert_slug` incomplet ou vide, détecté avant tout appel API — `identifiant` porte alors l'`id_geometrie`, faute d'`alert_slug` exploitable.

## Dépendances retenues

- `requests` — déjà présent (étape 1), réutilisé pour les appels REST Strapi et Notion.
- `python-dotenv` — déjà présent (étape 2/5), pour charger `STRAPI_API_TOKEN`/`STRAPI_URL`/`PERSONNAL_NOTION_TOKEN`/`NOTION_DATABASE_ID` depuis `.env`.
- `tenacity` — déjà présent (étape 1), même politique de nouvelle tentative que `resolution_territoire.py`/`communes.py` pour les deux clients.
- Aucune dépendance nouvelle : ni SDK Strapi, ni SDK Notion officiel — REST brut via `requests`, cohérent avec le reste du pipeline.

## Validation

Testé en conditions réelles sur `067-plui-strasbourg` : dry-run (recherche Strapi et Notion vérifiée, aucune écriture), puis envoi réel sur une géométrie isolée (contenu relu et vérifié conforme des deux côtés — `content`/`source`/`reference`/`label`/`title` côté Strapi, `Territoire`/`Description`/`alert_slug`/géométrie jointe côté Notion), puis généralisation au département complet (28 géométries, `alert_slug` saisis via `outil_validation.html`) : les 28 lignes sont créées/à jour sur Strapi et sur Notion, sans nouveau doublon depuis le correctif décrit dans "Idempotence".
