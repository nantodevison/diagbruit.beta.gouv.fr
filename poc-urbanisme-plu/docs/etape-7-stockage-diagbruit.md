# Étape 7 — Stockage : insertion automatisée dans Strapi et Notion

*Document de cadrage initial — tous les points ouverts sont désormais tranchés (voir chaque section datée ci-dessous) ; la conception technique détaillée est dans `etape-7-conception-technique.md`, qui fait foi pour l'implémentation. Suite de `etape-6-mise-en-forme-diagbruit.md` et `etape-6-conception-technique.md`. Version issue des échanges des 21-24/08/2026.*

## Objectif

Automatiser, à partir des livrables de l'étape 6 (`etape6_{dept}_export.csv`, complété par l'opérateur via `outil_validation.html` — `alert_slug_propose` porte désormais la valeur finale — et `etape6_{dept}_geometries/`), les deux actions aujourd'hui faites à la main par la partie métier (voir `etape-6-mise-en-forme-diagbruit.md`, "Rappel du circuit métier actuel") :

1. créer (ou mettre à jour) l'entrée Strapi (préprod) portant le message d'une zone et son `alert_slug` ;
2. créer (ou mettre à jour) l'entrée Notion correspondante (base "Données réglementaires locales (PLU, PPBE, …)"), avec le même `alert_slug` et la géométrie en pièce jointe.

**Ce que cette étape ne change pas** : la partie développement continue de relier les deux (Strapi/Notion) pour les mettre à disposition de diagBruit — voir `etape-6-mise-en-forme-diagbruit.md`, point 3 du circuit. L'ingestion directe dans le pipeline Dagster/PostGIS reste hors scope, pour la même raison qu'à l'étape 6.

## Schéma Strapi (point 1, tranché le 23/08/2026, confirmé le 24/08/2026)

Lu directement dans `cms/src/api/noisezone-alert/content-types/noisezone-alert/schema.json`, et confirmé par une capture d'écran de la saisie manuelle réelle :

| Champ | Type | Détail |
|---|---|---|
| `alert_slug` | `uid`, cible `title` | **requis** — Strapi refuse nativement un doublon (contrainte d'unicité native, utile pour l'idempotence, voir point 5). |
| `title` | `string` | non requis par le schéma, mais rempli en pratique (phrase courte, ex. "Autoriser les murs au lieu des clôtures..."). **Renseigné par l'insertion automatique depuis le 24/08/2026** (voir `etape-5-ameliorations-possibles.md`, "Génération LLM d'un titre court") : `titre_propose`, généré par LLM à l'étape 5 et validé par l'opérateur — auparavant laissé vide, à compléter manuellement. |
| `content` | HTML (CKEditor) | le message. |
| `source` | `string` | **requis**, défaut `"Plan Local d'Urbanisme"`. Confirmé le 24/08/2026 : correspond à `type_piece_source`/`nature` (déjà utilisé à l'étape 6, voir `etape-6-conception-technique.md`, "Contrat de données", colonne `strapi_source`). |
| `reference` | `string` | **requis**. |
| `label` | enum `ZONE SOUMISE AU BRUIT` / `ZONE CALME` | **requis**, défaut `ZONE SOUMISE AU BRUIT`. |
| — | — | `draftAndPublish` activé : toute entrée créée par l'API reste en brouillon tant qu'elle n'est pas explicitement publiée — l'opérateur relit et publie. |

## Champs granulaires désormais produits par l'étape 6 (décidé le 24/08/2026)

**Changement d'architecture** : plutôt que de faire relire par l'étape 7 `etape4_{dept}.gpkg`, `etape5_{dept}.gpkg`, `etape5_{dept}_documents_par_synthese.csv` et `etape5_{dept}_occurrences.csv` pour reconstituer les champs Strapi/Notion granulaires (option envisagée initialement), cette logique a été déplacée dans `generer_export.py` (étape 6) — cohérent avec son rôle ("mise en forme pour ingestion") et avec la convention du projet qu'une étape ne consomme que le fichier produit par l'étape précédente (`etape-1-conception-technique.md`, "Décision 2"). Voir `etape-6-conception-technique.md`, "Écart avec le schéma Strapi réel", pour le détail technique.

`etape6_{dept}_export.csv` porte donc désormais, en plus des colonnes déjà connues, `message_content`/`strapi_source`/`strapi_reference`/`label_propose` (→ `content`/`source`/`reference`/`label` Strapi) et, depuis le 24/08/2026, `titre_propose` (→ `title` Strapi **et** `Description` Notion, voir "Colonne Description" ci-dessous) — **l'étape 7 n'a plus besoin de lire que `etape6_{dept}_export.csv` et `etape6_{dept}_geometries/`**, plus aucun fichier antérieur.

Pour ne jamais perdre la saisie manuelle déjà faite (`alert_slug_propose`), `generer_export.py` reprend désormais ces valeurs d'un export précédent si `etape6_{dept}_export.csv` existe déjà au moment de la régénération — voir `etape-6-conception-technique.md`, "Reprise à la régénération".

**Déduplication** (voir `etape-6-conception-technique.md`, "Pourquoi la déduplication est correcte") : `strapi_source`/`strapi_reference` sont dédupliqués avant jointure. Une valeur répétée dans `etape5_{dept}_documents_par_synthese.csv` correspond souvent à des occurrences distinctes (alinéas différents d'un même article), mais la fusion de ces occurrences en une seule synthèse est déjà validée par l'opérateur à l'étape 5 — répéter la même référence dans un champ de synthèse pour le lecteur final n'apporte donc rien, une fois cette fusion actée. (`titre_propose` n'est pas concerné : ce n'est pas un assemblage de plusieurs valeurs, mais un texte unique généré par LLM.)

**`content` reste à convertir en HTML** (pas encore fait) : `message_content` est du texte brut avec retours à la ligne (`\n`), `content` attend du HTML (CKEditor). Conversion envisagée (24/08/2026) : un seul `<p>` englobant tout le texte, avec chaque `\n` remplacé par `<br>` — préserve les sauts de ligne (importants, voir `ton_de_voix.py`, "Phrases courtes, énumérations privilégiées") sans multiplier les balises. Votre saisie manuelle ajoute aussi du gras sur les citations réglementaires exactes dans `content` (capture d'écran du 24/08/2026) — **non reproduit par l'automatisation dans un premier temps**, voir `etape-5-ameliorations-possibles.md`, "Pas de mise en forme (gras, listes) capturée lors de la correction manuelle des messages", pour la piste envisagée (un bandeau de mise en forme dans `outil_validation.html` à l'étape 5, en amont) et pourquoi elle n'est pas retenue pour l'instant.

## Accès Notion (point 2, tranché le 23/08/2026, confirmé le 24/08/2026)

Vérifié par un appel direct à l'API (`GET /v1/databases/{id}`, script jetable, non versionné) :
- `PERSONNAL_NOTION_TOKEN` (tel quel dans votre `.env` — remarquez l'orthographe à deux "N", conservée pour ne pas vous faire retoucher le fichier) se lit bien depuis `poc-urbanisme-plu/.env`.
- L'identifiant tiré de votre URL (`54b3a944682d8392bac70192370486ab`) **est directement un identifiant de base de données** Notion, exploitable tel quel par l'API. Ajouté à votre `.env` sous `NOTION_DATABASE_ID`.
- Le schéma retourné confirme exactement `etape-6-mise-en-forme-diagbruit.md` : `alert_slug` (texte, **pas de contrainte d'unicité native**, contrairement à Strapi — voir point 5), `Description` (texte), `data` (fichiers), `Territoire` (titre).
- **Confirmé le 24/08/2026** : malgré le suffixe `(1)` dans son titre technique (marque habituelle d'une base dupliquée dans Notion), c'est bien la base de travail de l'équipe.

## Colonne `Description` (point 3) — validé le 24/08/2026, révisé le 24/08/2026

Initialement : citations de l'étape 3 (`extrait_significatif`), dédupliquées et jointes par `" / "` en cas de groupe fusionné à plusieurs occurrences.

**Révision, même jour** (voir `etape-5-ameliorations-possibles.md`, "Génération LLM d'un titre court à l'étape 5") : des citations réglementaires brutes ne constituent pas un "résumé libre, à usage interne Notion" lisible. Remplacé par `titre_propose` — un titre court (quelques mots) généré par LLM à l'étape 5 à partir du `message_synthese` déjà validé, avec son propre circuit de correction humaine, et réutilisé tel quel pour `title` côté Strapi (voir "Schéma Strapi" ci-dessus). Produit par l'étape 6 dans la colonne `titre_propose` de `etape6_{dept}_export.csv`.

## Pièce jointe géométrie (point 4) — testé le 23/08/2026, fonctionne avec un ajustement

Testé en réel (création d'un objet *file upload* + envoi du contenu d'un `.geojson` de l'étape 6, sans jamais l'attacher à une page de la base partagée — donc sans rien écrire de visible pour l'équipe) :

1. `POST /v1/file_uploads` (`Notion-Version: 2026-03-11`) avec `{"filename": ..., "content_type": ...}` → renvoie un `id` et une `upload_url`.
2. `POST {upload_url}` en `multipart/form-data`, champ `file`.
3. Une fois attaché à une page (non testé en réel, pour ne pas créer d'entrée visible sans votre accord — voir "Prochaine étape") : propriété de type `files`, valeur `{"type": "file_upload", "file_upload": {"id": "..."}}`.

**Point bloquant contourné** : l'extension `.geojson` est **explicitement refusée** par l'API (`"Provided filename has an extension that is not supported"`). Contournement testé et fonctionnel : envoyer le même contenu en le renommant `{id_geometrie}.json` avec `content_type: application/json` — accepté sans problème, le contenu (du GeoJSON valide) n'a pas besoin d'être modifié, seuls le nom de fichier et le type déclaré changent.

Autre point à noter : un fichier envoyé sans être attaché à une page expire au bout d'une heure — pas de risque de laisser des objets orphelins dans Notion si l'étape 7 échoue entre l'envoi et l'attachement.

## Idempotence (point 5)

Proposition concrète, votre décision restant de confirmer/ajuster :

- **Strapi** : `alert_slug` est un champ `uid`, avec contrainte d'unicité native. Tenter la création (`POST /api/noisezone-alerts`) ; si Strapi répond une erreur d'unicité, retrouver l'entrée existante (`GET /api/noisezone-alerts?filters[alert_slug][$eq]=...`) et la mettre à jour (`PUT`) plutôt que de considérer ça comme un échec.
- **Notion** : pas de contrainte d'unicité native sur `alert_slug` (simple texte) — il faut donc systématiquement chercher avant d'écrire : `POST /v1/databases/{id}/query` avec un filtre `alert_slug` égal à la valeur, créer une page si rien n'est trouvé, sinon mettre à jour (`PATCH /v1/pages/{id}`) la page trouvée.

Dans les deux cas : rechercher avant d'écrire, jamais l'inverse — une ligne déjà insérée qui est relancée (ex. correction d'un message à l'étape 5, nouvel `etape6_{dept}_export.csv`) met à jour l'existant au lieu de dupliquer.

## Point de vigilance transverse

Cette étape écrit dans des systèmes partagés, visibles par toute l'équipe métier (CMS préprod, base Notion collective) — jamais anodin comme un fichier `output/` local. Un mode `--dry-run` (afficher ce qui serait créé/mis à jour sans appeler les API) sera la valeur par défaut, l'envoi réel nécessitant un choix explicite.

## Architecture provisoire envisagée (non implémentée)

```
poc-urbanisme-plu/
└── etape7_stockage/
    ├── __init__.py
    ├── client_strapi.py        # créer/mettre à jour une entrée par alert_slug
    ├── client_notion.py        # créer/mettre à jour une page par alert_slug + upload de la géométrie
    └── inserer.py              # phase unique, lit etape6_{dept}_export.csv + etape6_{dept}_geometries/,
                                 # --dry-run par défaut
```

## Accès Strapi (testé le 24/08/2026, en lecture seule — aucune écriture)

`STRAPI_API_TOKEN`/`STRAPI_URL` reçus et déposés dans `.env`. Deux problèmes trouvés en testant (requêtes `GET` uniquement, jamais d'écriture) :

1. **URL** : `STRAPI_URL` était renseignée avec un chemin complet et incorrect (`.../api/noisezone-alert`, singulier → 404). Corrigée en base seule (`https://cms.preprod.diagbruit.fr`), cohérente avec `fastapi/.env.example` (`STRAPI_URL=http://localhost:1337`, sans chemin) — c'est le code qui doit ajouter `/api/noisezone-alerts`, **au pluriel** (`pluralName` du schéma, voir "Schéma Strapi" ci-dessus), pas la variable d'environnement qui doit le porter.
2. **Jeton** : `GET /api/noisezone-alerts` fonctionne **sans** jeton (lecture publique déjà ouverte sur ce content-type, cohérent avec `fastapi/app/utils/strapi.py` qui lit sans authentification) mais renvoyait **403 Forbidden avec** le jeton initial (`create`/`update` seulement, sans `find`/`findOne`). **Corrigé le 24/08/2026** : le jeton a été mis à jour côté Strapi pour ajouter `find`/`findOne` (toujours sans `delete`) — revérifié en réel, `GET .../noisezone-alerts?filters[alert_slug][$eq]=...` fonctionne désormais et renvoie l'entrée (avec son `documentId`) ou une liste vide. L'idempotence peut donc s'appuyer sur une recherche live, voir `etape-7-conception-technique.md`, "Idempotence".

Tous les points ouverts sont désormais tranchés — conversion HTML validée (un seul `<p>`, `<br>` par retour à la ligne), accès Strapi/Notion confirmés. Conception technique détaillée : voir `etape-7-conception-technique.md`.

## Prochaine étape

Voir `etape-7-conception-technique.md`, "Prochaine étape" — implémentation de `etape7_stockage/`, puis un premier test réel limité à une seule géométrie, avec accord explicite avant toute généralisation.
