# Étape 7 — Stockage : insertion automatisée dans Strapi et Notion

*Document de cadrage de l'étape 7 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-6-mise-en-forme-diagbruit.md` et `etape-6-conception-technique.md`. La conception technique détaillée est dans `etape-7-conception-technique.md`, qui fait foi pour l'implémentation.*

## Objectif

Automatiser, à partir du livrable de l'étape 6 (`etape6_{dept}_export.csv`, complété par l'opérateur via `outil_validation.html` — `alert_slug_propose` y porte la valeur finale — et `etape6_{dept}_geometries/`), les deux actions jusqu'ici faites à la main par la partie métier (voir `etape-6-mise-en-forme-diagbruit.md`, "Rappel du circuit métier actuel") :

1. créer (ou mettre à jour) l'entrée Strapi (préprod) portant le message d'une zone et son `alert_slug` ;
2. créer (ou mettre à jour) l'entrée Notion correspondante (base "Données réglementaires locales (PLU, PPBE, …)"), avec le même `alert_slug` et la géométrie en pièce jointe.

Cette étape est implémentée (`etape7_stockage/`) et a été utilisée en conditions réelles sur `067-plui-strasbourg` (28 géométries) : les entrées Strapi et Notion de ce périmètre sont créées et à jour.

**Ce que cette étape ne change pas** : la partie développement continue de relier les deux systèmes (Strapi/Notion) pour les mettre à disposition de diagBruit — voir `etape-6-mise-en-forme-diagbruit.md`, point 3 du circuit. L'ingestion directe dans le pipeline Dagster/PostGIS reste hors scope, pour la même raison qu'à l'étape 6.

## Schéma Strapi

Content-type `noisezone-alert` (`cms/src/api/noisezone-alert/content-types/noisezone-alert/schema.json`) :

| Champ | Type | Détail |
|---|---|---|
| `alert_slug` | `uid`, cible `title` | requis — contrainte d'unicité native, à la base de l'idempotence côté Strapi (voir "Idempotence" ci-dessous). |
| `title` | `string` | phrase courte résumant la zone (ex. "Autoriser les murs au lieu des clôtures..."). Renseigné automatiquement à partir de `titre_propose`, un titre généré par LLM à l'étape 5 et validé par l'opérateur. |
| `content` | HTML (CKEditor) | le message, converti depuis le texte brut produit à l'étape 6 (voir "Mise en forme du message" ci-dessous). |
| `source` | `string` | requis, défaut `"Plan Local d'Urbanisme"` — correspond à `strapi_source`, déjà produit par l'étape 6. |
| `reference` | `string` | requis — `strapi_reference`, déjà produit par l'étape 6. |
| `label` | enum `ZONE SOUMISE AU BRUIT` / `ZONE CALME` | requis, défaut `ZONE SOUMISE AU BRUIT`. |
| — | — | `draftAndPublish` actif : toute entrée créée par l'insertion automatique reste en brouillon — l'opérateur relit et publie manuellement dans Strapi. |

## Colonnes granulaires produites par l'étape 6

`etape6_{dept}_export.csv` porte, en plus des colonnes de repérage (`id_geometrie`, `territoire_propose`, `alert_slug_propose`, `nom_fichier_geometrie`…), les colonnes déjà mises en forme pour les deux systèmes cibles : `message_content`/`strapi_source`/`strapi_reference`/`label_propose` (→ `content`/`source`/`reference`/`label` Strapi) et `titre_propose` (→ `title` Strapi **et** `Description` Notion, voir ci-dessous). L'étape 7 n'a besoin de lire que ce fichier et `etape6_{dept}_geometries/` — aucun fichier antérieur du pipeline.

## Mise en forme du message

`message_content` est du texte brut avec retours à la ligne (`\n`) ; `content` (Strapi) attend du HTML. La conversion encapsule tout le texte dans un unique `<p>`, chaque `\n` devenant `<br>` — cela préserve les sauts de ligne (voir `ton_de_voix.py`, "Phrases courtes, énumérations privilégiées") sans multiplier les balises. La saisie manuelle observée met aussi en gras les citations réglementaires exactes dans `content` : cette mise en forme n'est pas reproduite par l'automatisation (voir `ameliorations-identifiees.md` pour la piste envisagée et pourquoi elle n'est pas retenue pour l'instant).

## Accès Notion

La base "Données réglementaires locales (PLU, PPBE, …)" porte `alert_slug` (texte, **sans** contrainte d'unicité native, contrairement à Strapi), `Description` (texte), `data` (fichiers), `Territoire` (titre).

## Colonne `Description` (Notion)

`titre_propose` — le même titre court généré par LLM et validé par l'opérateur qui alimente `title` côté Strapi (voir "Schéma Strapi" ci-dessus). Des citations réglementaires brutes avaient été envisagées pour ce champ, mais ne constituent pas un résumé lisible pour un usage interne Notion — écarté au profit du titre court.

## Pièce jointe géométrie

La géométrie de la zone (`.geojson`, produite à l'étape 6) est envoyée à Notion comme pièce jointe de la page (propriété `data`). L'API Notion refuse l'extension `.geojson` ; le fichier est donc envoyé tel quel, seulement renommé en `.json` — le contenu (du GeoJSON valide) n'a pas besoin d'être modifié. Un fichier envoyé sans être attaché à une page expire au bout d'une heure : pas de risque d'objets orphelins dans Notion si l'étape 7 échoue entre l'envoi et l'attachement.

## Idempotence

Avant toute écriture, l'étape 7 cherche une entrée/page existante par `alert_slug`, de chaque côté — jamais l'inverse :
- **Strapi** : `alert_slug` est un champ `uid` unique — une entrée trouvée est mise à jour, sinon elle est créée.
- **Notion** : `alert_slug` est un simple champ texte, sans contrainte d'unicité — la recherche préalable est donc la seule protection contre les doublons.

Relancer l'étape 7 sur le même `etape6_{dept}_export.csv` (par exemple après une correction de message à l'étape 5) met donc à jour les entrées déjà créées plutôt que d'en créer de nouvelles.

## Configuration requise

Quatre variables d'environnement, dans `poc-urbanisme-plu/.env` :
- `STRAPI_URL` — l'origine seule (ex. `https://cms.preprod.diagbruit.fr`), sans chemin : le code ajoute lui-même `/api/noisezone-alerts` (au pluriel).
- `STRAPI_API_TOKEN` — jeton avec les droits `find`/`findOne`/`create`/`update` sur `noisezone-alert` (la lecture, `find`/`findOne`, est nécessaire à l'idempotence ci-dessus).
- `PERSONNAL_NOTION_TOKEN` — orthographe (deux "N") conservée telle quelle depuis le `.env` existant.
- `NOTION_DATABASE_ID` — identifiant de la base Notion, tel que visible dans son URL.

Sans l'une de ces quatre variables, `inserer.py` s'arrête avant de traiter la moindre ligne.

## Point de vigilance transverse

Cette étape écrit dans des systèmes partagés, visibles par toute l'équipe métier (CMS préprod, base Notion collective) — jamais anodin comme un fichier `output/` local. Un mode dry-run (afficher ce qui serait créé/mis à jour, sans appeler les API en écriture) est la valeur par défaut de `inserer.py` ; l'envoi réel nécessite le drapeau explicite `--envoyer`.

## Limite connue

Une mise à jour écrase le contenu existant côté Strapi sans distinguer une entrée encore en brouillon d'une entrée déjà publiée et éventuellement retouchée à la main (ex. `title` peaufiné après publication). Risque accepté pour un usage à volume limité ; à revoir si des retouches manuelles après publication deviennent fréquentes — voir `etape-7-conception-technique.md`, "Idempotence".
