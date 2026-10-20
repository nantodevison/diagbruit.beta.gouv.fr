# Étape 7 — Conception technique : insertion automatisée dans Strapi et Notion

*Document de conception technique, faisant suite à `etape-7-stockage-diagbruit.md` et à `etape-6-conception-technique.md`.*

## Posture

Même sous-dossier du même POC que les étapes 1 à 6 (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, isolé du reste du produit, preuve de concept plutôt que composant prêt à intégrer.

**Écart majeur par rapport aux étapes précédentes** : c'est la première étape qui écrit dans des systèmes partagés et visibles par toute l'équipe métier (CMS Strapi préprod, base Notion collective) — jamais anodin comme un fichier `output/` local que seul l'opérateur du POC consulte. Conséquence directe dans la conception : **`--envoyer` explicite requis pour toute écriture réelle** — sans ce drapeau, `inserer.py` ne fait qu'afficher ce qu'il ferait (voir "Mode dry-run" ci-dessous). C'est le comportement par défaut, pas une option.

## Correctif du 20/10/2026 — `alert_slug` dans les géométries, contrôles bloquants, audit

*Constat du 11/09/2026 (le `.geojson` déposé sur Box ne portait que `id_geometrie`), complété le 19/10/2026 par le retour de l'équipe de développement (identifiants dupliqués, PLU manquants entre prod et préprod). Implémenté et testé hors ligne le 20/10/2026 ; le bloc d'avertissement `TODO(alert_slug)` de `inserer.py` est retiré.*

**Pourquoi `alert_slug` doit être dans le fichier géométrie** : c'est lui qui relie un contour à son contenu Strapi une fois sorti de ce pipeline POC. Notion (`alert_slug` et lien Box côte à côte sur la même page) n'est qu'un outil de coordination avec l'équipe de développement, pas la jointure définitive.

**Ce qui est fait, dans `inserer.py`, à chaque exécution** (jamais un script de vérification séparé à lancer « avant », qui pourrait porter sur des fichiers modifiés entre-temps) :

1. **Contrôles bloquants sur l'export entier, avant tout appel réseau** (`_controler_export`) — au moindre problème, arrêt sans rien envoyer, avec la liste complète des problèmes :
   - format de chaque `alert_slug` : non vide, pas de `-` final, au moins deux `-` (`alert-{Territoire}-{Terme}`), et uniquement `A-Z a-z 0-9 - _ . ~` — règle du champ `uid` de Strapi, lue dans le code de Strapi 5.13.0 (`@strapi/core`, `uidValidator`), version déclarée dans `cms/package.json`. Strapi ne l'applique qu'à la **publication**, pas au brouillon : sans ce contrôle, un slug invalide passerait l'étape 7 et ne bloquerait qu'au moment de publier ;
   - **unicité** des slugs dans l'export : un doublon ferait mettre à jour la même entrée deux fois, l'une écrasant l'autre ;
   - présence du `.geojson` de chaque ligne ;
   - **champs obligatoires de Strapi non vides** (`source`, `reference`, `label`, plus `content`) et `label` parmi `ZONE SOUMISE AU BRUIT`/`ZONE CALME` — ajouté le 20/10/2026 après le dry-run du 067 : même piège que le format du slug, Strapi ne vérifie les champs obligatoires qu'à la publication (`required: !isDraft && attr.required`). 253 lignes sur 400 avaient `source`/`reference` vides : elles auraient été créées en brouillon puis impossibles à publier (voir `etape-6-conception-technique.md`, "Source et référence de ces quatre cas").

   Pourquoi bloquer plutôt que sauter la ligne (comportement d'avant) : un envoi partiel est plus difficile à rattraper qu'un envoi qui n'a pas eu lieu.
2. **`alert_slug` ajouté au `.geojson` local juste avant le dépôt Box** (`_ajouter_alert_slug_geojson`), puis le fichier est relu pour vérification. Option retenue le 20/10/2026 : modifier le fichier local plutôt qu'envoyer une copie modifiée en mémoire — le fichier du disque, celui du dépôt Git et celui de Box restent identiques, sans modification silencieuse. Conséquences assumées : les `.geojson` locaux apparaissent modifiés dans Git après le premier envoi réel (à commiter) ; une relance de `generer_export.py` les réécrit sans `alert_slug`, que l'envoi suivant remet. Jamais en dry-run. `generer_export.py` (étape 6) reste inchangé : le slug n'y est pas encore définitif.
3. **Recherche stricte des entrées existantes** (`client_strapi.etat_entree`, `client_notion.trouver_page_id`) : si plusieurs documents Strapi (ou pages Notion) portent le même `alert_slug`, la ligne passe en erreur sans aucune écriture, avec la liste des identifiants à dédoublonner à la main. Avant, seul le premier résultat était retenu : avec un doublon (cas des doublons résiduels du 24/08), une entrée était mise à jour et l'autre restait obsolète sans que rien ne le signale.
4. **Journal enrichi** : colonnes `environnement` (`preprod`/`prod`) et `action_strapi`/`action_notion` (`cree`/`mis_a_jour`) — voir "Contrat de données". Un journal existant à l'ancien format est refusé (à renommer à la main) plutôt que complété avec un format mélangé. Le journal de l'Eurométropole (`etape7_067-plui-strasbourg_insertions.csv`) ne permettait pas de savoir dans quel environnement chaque ligne avait été écrite.
5. **Mode `--audit`**, lecture seule — voir "Mode audit" ci-dessous.

## Draft and publish (Strapi 5) — rappel et conséquences

Le content-type `noisezone-alert` a `draftAndPublish: true`. Un document (une alerte, identifiée par son `documentId`) existe en base sous une ou deux lignes, chacune avec son propre `id` numérique :
- **jamais publié** : une seule ligne, le brouillon (`published_at` vide) — état normal d'une entrée créée par ce script ;
- **publié** : deux lignes, brouillon **et** version publiée, qui partagent le même `documentId`.

Une alerte publiée à qui il manquerait sa ligne brouillon casse l'interface d'administration (retour de l'équipe de développement du 19/10/2026). Cet état ne peut pas être produit par ce script : il passe exclusivement par l'API REST (`POST`/`PUT /api/noisezone-alerts`), c'est Strapi qui crée les lignes et attribue les identifiants. Le payload ne contient **aucun** `id` ni `documentId` (ce dernier est seulement lu dans les réponses, puis utilisé dans l'URL d'un `PUT`) — vérifié dans le code le 19/10/2026.

Conséquences pratiques :
- le front (FastAPI, `fetch_noisezone_alert_content`) interroge Strapi **sans** paramètre `status`, donc ne voit que les entrées **publiées** : une alerte créée par ce script reste invisible sur le site tant que personne ne la publie dans l'admin Strapi. Un écart de publication entre prod et préprod se traduit donc par des PLU « manquants » d'un côté ;
- une mise à jour (`PUT ... ?status=draft`) d'une alerte déjà publiée ne modifie que son brouillon : la version publiée reste l'ancienne jusqu'à une republication manuelle. Le dry-run le signale ligne par ligne.

## Mode audit (`--audit`)

`python -m etape7_stockage.inserer --dept 067 --audit --environnement preprod` — **lecture seule** : uniquement des `GET` sur Strapi (`client_strapi.lister_entrees`, toutes les entrées, page par page, en brouillon puis en publié), aucun appel Notion ni Box, aucune écriture distante. `--box-folder-id` n'est pas requis. Écrit `etape7_{dept}_audit_{environnement}.csv`, une ligne par `alert_slug` présent dans Strapi ou dans l'export (`alert_slug`, `dans_export`, `id_geometrie`, `document_ids`, `brouillon`, `publie`, `anomalie`), et affiche un résumé.

Anomalies relevées : `doublon` (plusieurs documents pour un même slug), `publie_sans_brouillon` (document publié sans version brouillon visible, le cas signalé par l'équipe de développement), `absent` (slug de l'export absent de Strapi). Un brouillon seul n'est pas une anomalie.

Même en lecture seule, un audit sur la **prod** n'est lancé qu'avec l'accord explicite de l'opérateur.

## Architecture des dossiers

```
poc-urbanisme-plu/
├── etape6_mise_en_forme/                  # existant
├── etape7_stockage/
│   ├── __init__.py                        # vide, comme les modules précédents
│   ├── client_strapi.py                   # aide partagée : créer/mettre à jour une entrée noisezone-alert
│   ├── client_box.py                      # aide partagée : déposer la géométrie sur Box, retourner son URL
│   ├── client_notion.py                   # aide partagée : créer/mettre à jour une page (data = URL Box)
│   └── inserer.py                         # phase unique — lit etape6_{dept}_export.csv + etape6_{dept}_geometries/
└── output/
    ├── etape6_{dept}_export.csv
    ├── etape6_{dept}_geometries/
    ├── etape7_{dept}_insertions.csv       # journal des créations/mises à jour, jamais relu (voir "Idempotence")
    └── etape7_{dept}_erreurs.csv          # échecs isolés, absent si rien à signaler
```

Étape à phase unique, comme l'étape 6. Usage, depuis `poc-urbanisme-plu/` :

```
python -m etape7_stockage.inserer --dept 033 --box-folder-id 398163261000
# → dry-run, Strapi préprod (défaut) : liste ce qui serait créé/mis à jour, sans rien envoyer

python -m etape7_stockage.inserer --dept 033 --box-folder-id 398163261000 --envoyer
# → exécute réellement les créations/mises à jour, sur le Strapi préprod

python -m etape7_stockage.inserer --dept 033 --box-folder-id 398163261000 --environnement prod --envoyer
# → même chose, sur le Strapi de production
```

`--output-dir` (défaut `output/`) permet de pointer vers un autre dossier de lecture/écriture que le défaut. `--box-folder-id` est **requis** : il n'y a pas de dossier Box par défaut — un dossier Box existe par territoire, jamais résolu automatiquement depuis les données (voir "Dépôt sur Box" ci-dessous). `--environnement` (`preprod` par défaut, ou `prod`) choisit le Strapi ciblé — voir "Deux environnements Strapi" ci-dessous ; Notion et Box, eux, n'ont qu'un seul environnement.

## Phase unique — Insertion (`inserer.py`)

Lit `etape6_{dept}_export.csv` (une ligne par géométrie finale, `alert_slug_propose` portant la valeur finale saisie via `outil_validation.html`) et le fichier `.geojson` correspondant dans `etape6_{dept}_geometries/`. S'arrête immédiatement, avant de traiter la moindre ligne, si `etape6_{dept}_export.csv` ou `etape6_{dept}_geometries/` sont introuvables, ou si `PERSONNAL_NOTION_TOKEN`/`NOTION_DATABASE_ID`/`BOX_CLIENT_ID`/`BOX_CLIENT_SECRET`/`BOX_ENTREPRISE_ID` sont absents de l'environnement, ou si les deux variables Strapi de l'environnement ciblé par `--environnement` (`STRAPI_PREPROD_API_TOKEN`/`STRAPI_PREPROD_URL` par défaut, `STRAPI_PROD_API_TOKEN`/`STRAPI_PROD_URL` avec `--environnement prod`) sont absentes (voir "Gestion des erreurs").

Pour chaque ligne :

1. **Validation de l'`alert_slug`** : une valeur vide, ou encore terminée par `-` (proposition mécanique de `outil_validation.html` jamais complétée par l'opérateur — voir `etape-6-conception-technique.md`), n'est pas exploitable. **Depuis le 20/10/2026, ce contrôle porte sur l'export entier et il est bloquant** (format `uid` Strapi, unicité, géométrie présente) : au moindre problème, rien n'est envoyé — voir "Correctif du 20/10/2026" en tête de document.
2. **Strapi** (`client_strapi.py`) — construit le payload à partir des colonnes déjà granulaires de l'étape 6 (voir `etape-6-conception-technique.md`, "Contrat de données") :
   - `alert_slug` ← `alert_slug_propose`
   - `content` ← `message_content`, encapsulé dans un unique `<p>...</p>`, chaque `\n` remplacé par `<br>` (voir "Conversion `content`" ci-dessous)
   - `source` ← `strapi_source`
   - `reference` ← `strapi_reference`
   - `label` ← `label_propose`
   - `title` ← `titre_propose` (titre court généré par LLM à l'étape 5, validé par l'opérateur). `alert_slug` (champ `uid`, `targetField: title` côté schéma Strapi) est fourni explicitement dans le payload plutôt que dérivé de `title`.
   - Recherche préalable (`trouver_document_id`, voir "Idempotence") : absente → création, `POST {url_environnement}/api/noisezone-alerts?status=draft`, corps `{"data": {...}}`. Présente → mise à jour, `PUT {url_environnement}/api/noisezone-alerts/{documentId}?status=draft` (Strapi 5 — `documentId`, une chaîne, pas l'`id` numérique). `url_environnement` vient de `STRAPI_PREPROD_URL` ou `STRAPI_PROD_URL` selon `--environnement` (voir "Deux environnements Strapi" ci-dessous).
   - Entrée créée **en brouillon** (`draftAndPublish` actif sur ce content-type), jamais publiée automatiquement par le script — l'opérateur relit et publie manuellement dans Strapi. Le paramètre de requête `status=draft` sur `POST`/`PUT` est ce qui garantit ce comportement — voir "Piège : publication automatique" ci-dessous.
3. **Box puis Notion** (`client_box.py` + `client_notion.py`) :
   - Avant le dépôt, le `.geojson` local reçoit la propriété `alert_slug` puis est relu pour vérification (voir "Correctif du 20/10/2026", point 2).
   - Dépôt de la géométrie sur Box (`client_box.televerser_geometrie`) : recherche d'un fichier du même nom dans `--box-folder-id` (index du dossier mis en cache pour le run, voir "Dépôt sur Box" ci-dessous) ; absent → `POST https://upload.box.com/api/2.0/files/content` (création) ; présent → `POST .../files/{id}/content` (nouvelle version, pas de doublon). Retourne `https://app.box.com/file/{id}`.
   - Recherche préalable côté Notion (`trouver_page_id`, `POST /v1/data_sources/{data_source_id}/query` — voir "Sources de données Notion" ci-dessous). Absente → création (`POST /v1/pages`, `parent` = `{"type": "data_source_id", "data_source_id": ...}`). Présente (`page_id`) → mise à jour (`PATCH /v1/pages/{page_id}`).
   - Champs : `Territoire` ← `territoire_propose`, `Description` ← `titre_propose` (même source que `title` Strapi ci-dessus), `alert_slug` ← `alert_slug_propose`, `data` ← lien externe vers le fichier Box (`{"type": "external", "external": {"url": "https://app.box.com/file/..."}}`), pas un fichier uploadé dans Notion.
4. **Journal** (`etape7_{dept}_insertions.csv`, uniquement avec `--envoyer`) : une ligne est ajoutée dès qu'au moins un des deux systèmes (Strapi/Notion) a été créé ou mis à jour avec succès, écrite et vidée sur disque immédiatement après le traitement de la ligne — pas accumulée en mémoire jusqu'à la fin du run. Une interruption en cours de route (timeout, erreur réseau) laisse donc une trace locale des lignes déjà traitées avant l'arrêt.

Strapi et Notion (dépôt Box inclus, préalable à l'écriture Notion) sont traités indépendamment pour une même ligne : un échec sur l'un n'empêche jamais de tenter l'autre (voir "Gestion des erreurs").

## Dépôt sur Box (`client_box.py`)

Authentification Box en Client Credentials Grant, à l'échelle de l'entreprise (`POST https://api.box.com/oauth2/token`, `grant_type=client_credentials` + `box_subject_type=enterprise` + `box_subject_id={BOX_ENTREPRISE_ID}`) — même mécanisme que le `BoxResource` de `dagster/` (`box_sdk_gen`, `BoxCCGAuth`/`CCGConfig`), réimplémenté ici en REST brut (`requests`) pour rester sans dépendance nouvelle. Jeton mis en cache pour le run, renouvelé s'il expire (durée de vie Box : 60 minutes).

Le dossier Box cible (`--box-folder-id`) est un dossier par territoire — jamais résolu automatiquement depuis les données, toujours fourni explicitement par l'opérateur (ex. `398163261000` pour l'Eurométropole de Strasbourg).

**Idempotence côté Box** : au premier appel pour un dossier donné, `client_box` liste ses fichiers (`GET /2.0/folders/{id}/items`) et met l'index nom → id en cache pour le run (un seul listing par dossier, pas un par géométrie). Une géométrie déjà déposée (même nom de fichier, ex. `10.geojson`) reçoit une nouvelle version (`POST .../files/{id}/content`) plutôt qu'un doublon.

**URL retournée** : `https://app.box.com/file/{id}` — l'URL native de la page Box du fichier, pas un *shared link* (`https://.../s/...`) qui nécessiterait d'activer explicitement le partage public du fichier (voir échange de cadrage du 04/09/2026).

## Sources de données Notion (`data_source_id` vs `database_id`)

Depuis la version d'API Notion `2025-09-03`, une base peut contenir plusieurs "sources de données" ; interroger ses lignes et y créer une page se font via un `data_source_id`, distinct du `database_id` et absent comme concept séparé avant cette version. `NOTION_DATABASE_ID` (dans `.env`) reste l'identifiant visible dans l'URL Notion ; `client_notion._data_source_id()` le traduit en `data_source_id` via `GET /v1/databases/{NOTION_DATABASE_ID}` (champ `data_sources`, premier élément — cette base n'en a qu'un seul), mis en cache pour le reste du run.

- **Lecture** (`trouver_page_id`) : `POST /v1/data_sources/{data_source_id}/query`, pas `/v1/databases/{id}/query` (retiré par cette version de l'API).
- **Création** (`creer_ou_mettre_a_jour`) : `parent` = `{"type": "data_source_id", "data_source_id": ...}`, pas `{"database_id": ...}`.
- **Mise à jour** (`PATCH /v1/pages/{page_id}`) : inchangée — une page reste identifiée par son propre `id` une fois créée, indépendamment de sa base parente.

## Deux environnements Strapi (`--environnement`)

`--environnement preprod|prod` (défaut `preprod`) sélectionne, à chaque appel réseau de `client_strapi.py`, la paire de variables à lire : `STRAPI_PREPROD_API_TOKEN`/`STRAPI_PREPROD_URL` ou `STRAPI_PROD_API_TOKEN`/`STRAPI_PROD_URL` (`client_strapi._nom_variable`). Chaque fonction du module qui touche le réseau (`trouver_document_id`, `creer_ou_mettre_a_jour`, `verifier_configuration`) prend `environnement` en paramètre explicite plutôt qu'un état global du module — un run cible un seul environnement du début à la fin, jamais un mélange.

**Historique (04/09/2026)** : jusque-là, une seule paire `STRAPI_API_TOKEN`/`STRAPI_URL` existait, implicitement pointée vers le Strapi préprod. Renommée en `STRAPI_PREPROD_*` pour lever l'ambiguïté, à l'occasion de l'ajout de la paire `STRAPI_PROD_*` (renseignée par l'opérateur quand le Strapi de production est prêt à recevoir des écritures — voir "Configuration requise" ci-dessous). Notion et Box restent partagés entre les deux environnements Strapi : un seul `NOTION_DATABASE_ID` et un seul dossier Box par territoire, aucune notion de préprod/prod de leur côté.

## Piège : publication automatique à la création Strapi

Un `POST`/`PUT` sans le paramètre de requête `status=draft` publie l'entrée immédiatement sur Strapi 5, y compris sans jamais passer `publishedAt` dans le corps de la requête. Il s'agit d'un comportement connu de l'API REST de Strapi 5 : le contrôle fiable du statut de brouillon n'est officiellement documenté que côté API interne *Document Service* (`strapi.documents(...).create({..., status: 'draft'})`), inaccessible à un client REST externe comme celui-ci. Le contournement retenu — passer `status=draft` en paramètre de requête (pas dans le corps JSON) sur `POST` et `PUT` — est appliqué systématiquement par `client_strapi._post`/`_put`.

**Conséquence directe sur la recherche** (voir "Idempotence" ci-dessous) : comme ce script ne crée jamais que des brouillons, une recherche Strapi qui omettrait le paramètre `status` — qui ne porte par défaut que sur les entrées **publiées** — ne trouverait jamais les entrées déjà créées, et déclencherait une nouvelle création à chaque passage au lieu d'une mise à jour.

## Idempotence

Avant toute écriture, l'étape 7 cherche une entrée/page existante par `alert_slug`, de chaque côté — jamais l'inverse. Une ligne déjà insérée qui est relancée (ex. correction d'un message à l'étape 5, nouvel `etape6_{dept}_export.csv`) met donc à jour l'existant au lieu de dupliquer.

- **Strapi** (`trouver_document_id`) : `GET {url_environnement}/api/noisezone-alerts?filters[alert_slug][$eq]={valeur}&status=draft` puis, si rien n'est trouvé, la même requête avec `status=published` (utile si une entrée a été publiée par un opérateur entre deux passages — brouillon et publié peuvent légitimement coexister pour un même `documentId`, voir "Piège : publication automatique" ci-dessus). Une entrée trouvée donne son `documentId` pour la mise à jour ; aucune des deux recherches ne trouvant rien déclenche une création. `url_environnement` dépend de `--environnement` (voir "Deux environnements Strapi" ci-dessus) — une même `alert_slug` peut donc légitimement exister séparément côté préprod et côté prod.
- **Notion** (`trouver_page_id`) : `POST /v1/data_sources/{data_source_id}/query`, filtre `alert_slug` (propriété `rich_text`) égal à la valeur — même logique. Notion n'a pas de notion de statut brouillon/publié sur une ligne de base de données : une seule recherche suffit.

`etape7_{dept}_insertions.csv` n'est qu'un journal de traçabilité pour l'opérateur (voir "Contrat de données") — jamais relu par le script : la source de vérité est systématiquement l'état réel de Strapi/Notion au moment de l'exécution, plus robuste qu'un fichier local qui pourrait être perdu, désynchronisé, ou absent sur une autre machine.

**Limite connue** : une mise à jour écrase le contenu existant sans distinguer une entrée encore en brouillon d'une entrée déjà publiée et éventuellement retouchée à la main dans Strapi — voir `ameliorations-identifiees.md`, "Une mise à jour Strapi écrase le contenu sans détecter une retouche manuelle post-publication".

**Historique** : une première version de la recherche Strapi ne passait pas le paramètre `status`, ce qui a fait recréer en doublon plusieurs dizaines d'entrées déjà existantes avant la correction décrite ci-dessus (recherche en deux temps `draft` puis `published`) — voir `ameliorations-identifiees.md`, "Doublons Strapi résiduels d'un bug d'idempotence désormais corrigé", pour le nettoyage résiduel encore nécessaire côté admin Strapi.

## Conversion `content` (texte → HTML)

`message_content` (texte brut, retours à la ligne `\n`) devient `content` en l'encapsulant dans un unique `<p>...</p>`, chaque `\n` remplacé par `<br>` (`client_strapi.convertir_content_html`). Ni gras, ni listes structurées (`<ul>/<li>`) : la saisie manuelle observée applique du gras sur les citations réglementaires exactes, non reproduit ici — voir `ameliorations-identifiees.md` pour la piste envisagée et pourquoi elle est reportée.

## Mode dry-run

Comportement par défaut de `inserer.py`, sans `--envoyer` : aucune requête d'écriture (`POST`/`PUT`/`PATCH`) n'est faite, ni sur Strapi, ni sur Notion, ni sur Box — seules les recherches en lecture (voir "Idempotence") sont exécutées, pour afficher un dry-run fidèle à l'état réel. Le script affiche, pour chaque ligne, ce qu'il ferait ("créerait" ou "mettrait à jour {documentId}/{page_id}", d'après la recherche live) — y compris les valeurs exactes des champs qui seraient envoyés, pour permettre une relecture avant tout envoi réel. Aucun fichier n'est écrit ni modifié en dry-run (ni journal, ni fichier d'erreurs, ni `.geojson`) — les erreurs éventuelles sont seulement affichées. Le dry-run signale aussi, pour une entrée Strapi existante, si elle est déjà publiée (la mise à jour ne touchera que son brouillon).

## Gestion des erreurs

Même principe que les étapes précédentes : un échec isolé sur une ligne (ex. Strapi, Notion ou Box indisponible, payload rejeté, `alert_slug` incomplet) n'empêche jamais le traitement des autres lignes — tracé dans `etape7_{dept}_erreurs.csv` (supprimé plutôt que laissé vide si rien à signaler). Un échec Box (ex. dossier introuvable, jeton expiré) est tracé côté `notion` (le dépôt Box précède l'écriture Notion dans le même bloc `_traiter_notion`, voir "Phase unique"). `inserer.py` s'arrête immédiatement, avant de traiter la moindre ligne, si `etape6_{dept}_export.csv` ou `etape6_{dept}_geometries/` sont introuvables, ou si `PERSONNAL_NOTION_TOKEN`/`NOTION_DATABASE_ID`/`BOX_CLIENT_ID`/`BOX_CLIENT_SECRET`/`BOX_ENTREPRISE_ID` sont absents de l'environnement, ou si les deux variables Strapi de l'environnement ciblé par `--environnement` sont absentes (voir "Deux environnements Strapi") — rien d'exploitable sans eux.

**Échec partiel Strapi/Notion pour une même ligne** : si l'insertion Strapi réussit mais l'insertion Notion échoue (ou l'inverse), la ligne est tracée en erreur pour la partie échouée, et journalisée pour la partie réussie (une ligne est journalisée dès qu'au moins un des deux identifiants est obtenu — voir "Phase unique" ci-dessus). Un second passage n'a besoin d'aucun état local pour ne pas dupliquer la partie déjà réussie : la recherche par `alert_slug` (voir "Idempotence") la retrouve à chaque exécution et ne retente que la partie manquante.

## Contrat de données

`etape7_{dept}_insertions.csv` (journal, une ligne par création/mise à jour réussie d'au moins un système — voir "Idempotence" : jamais relu par le script, uniquement pour la traçabilité de l'opérateur) :

| Colonne | Détail |
|---|---|
| `id_geometrie` | reprise de `etape6_{dept}_export.csv`. |
| `alert_slug` | clé de correspondance entre les deux systèmes et avec `etape6_{dept}_export.csv`. |
| `environnement` | `preprod` ou `prod` — Strapi ciblé par ce run (ajouté le 20/10/2026). |
| `action_strapi` | `cree` ou `mis_a_jour` — vide si l'insertion Strapi a échoué (ajouté le 20/10/2026). |
| `strapi_document_id` | `documentId` Strapi de l'entrée créée ou mise à jour — vide si l'insertion Strapi a échoué. |
| `action_notion` | `cree` ou `mis_a_jour` — vide si l'insertion Notion a échoué (ajouté le 20/10/2026). |
| `notion_page_id` | identifiant de page Notion créée ou mise à jour — vide si l'insertion Notion a échoué. |
| `date_traitement` | date de l'écriture (création ou mise à jour) pour cette ligne. |

`etape7_{dept}_erreurs.csv` : mêmes colonnes que les fichiers d'erreurs des étapes précédentes (`identifiant`, `source`, `message`, `date_traitement`) :
- `source` vaut `strapi` ou `notion` pour un échec d'appel API — `identifiant` porte alors l'`alert_slug` ;
- `source` ne vaut plus `validation` depuis le 20/10/2026 : un `alert_slug` invalide arrête désormais le run entier avant tout appel API (liste des problèmes en console), au lieu d'être tracé ligne par ligne.

## Dépendances retenues

- `requests` — déjà présent (étape 1), réutilisé pour les appels REST Strapi, Notion et Box.
- `python-dotenv` — déjà présent (étape 2/5), pour charger `STRAPI_PREPROD_API_TOKEN`/`STRAPI_PREPROD_URL`/`STRAPI_PROD_API_TOKEN`/`STRAPI_PROD_URL`/`PERSONNAL_NOTION_TOKEN`/`NOTION_DATABASE_ID`/`BOX_CLIENT_ID`/`BOX_CLIENT_SECRET`/`BOX_ENTREPRISE_ID` depuis `.env`.
- `tenacity` — déjà présent (étape 1), même politique de nouvelle tentative que `resolution_territoire.py`/`communes.py` pour les trois clients.
- Aucune dépendance nouvelle : ni SDK Strapi, ni SDK Notion officiel, ni `box_sdk_gen` (utilisé côté `dagster/`) — REST brut via `requests`, cohérent avec le reste du pipeline.

## Validation

Testé en conditions réelles sur `067-plui-strasbourg` : dry-run (recherche Strapi et Notion vérifiée, aucune écriture), puis envoi réel sur une géométrie isolée (contenu relu et vérifié conforme des deux côtés — `content`/`source`/`reference`/`label`/`title` côté Strapi, `Territoire`/`Description`/`alert_slug`/géométrie jointe côté Notion), puis généralisation au département complet (28 géométries, `alert_slug` saisis via `outil_validation.html`) : les 28 lignes sont créées/à jour sur Strapi et sur Notion, sans nouveau doublon depuis le correctif décrit dans "Idempotence".

**Évolution du 04/09/2026** : la pièce jointe Notion (upload direct du `.geojson`) est remplacée par un dépôt sur Box (`client_box.py`) puis un lien externe dans la propriété `data` — voir "Dépôt sur Box" ci-dessus. Les 28 pages Notion de l'Eurométropole de Strasbourg, créées avec l'ancien format, sont archivées puis réinsérées avec le nouveau.
