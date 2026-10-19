# Étape 6 — Mise en forme pour transmission à la partie développement

*Document de cadrage détaillé de l'étape 6 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-5-redaction-messages-diagbruit.md` et `etape-5-conception-technique.md`.*

**Entrée** : `etape5_{dept}.gpkg` (couche unique `messages`, une ligne par géométrie finale — voir `etape-5-conception-technique.md`, "Contrat de données") et `etape5_{dept}_documents_par_synthese.csv` (un document par ligne, clé étrangère `id_geometrie_synthese`).

Le plan global prévoyait initialement que cette étape porte aussi les "gabarits de message pour les documents non significatifs, les communes RNU et les trous de couverture" — ces trois textes fixes sont finalement intégrés directement à l'étape 5 (voir `etape-5-redaction-messages-diagbruit.md`, "Messages fixes"), pas ici.

## Circuit métier

Le circuit reste, comme avant l'automatisation de l'analyse (étapes 1 à 5), le suivant :
1. La partie métier remplit le CMS Strapi (préprod) avec le message d'une zone, associé à un `alert_slug` unique.
2. La partie métier crée une entrée dans une base Notion, avec le même `alert_slug` et la géométrie associée (fichier joint).
3. La partie développement relie les deux pour mettre les géométries et messages à disposition de l'application diagBruit.

L'étape 6 ne cherche donc pas à ingérer directement une base de données de production : elle prépare, à partir des messages validés à l'étape 5, tout ce dont la partie métier a besoin pour réaliser rapidement les étapes 1 et 2 ci-dessus, sans ressaisie ni calcul manuel.

Deux pistes alternatives ont été écartées avant de retenir ce circuit :
- Le pipeline d'ingestion automatisé de diagBruit (Dagster → dbt → PostgreSQL/PostGIS → FastAPI, voir `README.md` et `CLAUDE.md` du dépôt) sert un usage interne à l'équipe de développement, pas la partie métier : Strapi n'y est qu'un éditeur du texte des préconisations ("recommendation content management"), les géométries vivant entièrement dans PostGIS. Ce n'est donc pas la cible de cette étape.
- La base Notion réelle utilisée par la partie métier ("Données réglementaires locales (PLU, PPBE, …)", sous `Bdd Strapi > Bdd Sources`) confirme que Notion n'est utilisé que comme espace de coordination avec les développeurs (dépôt de l'`alert_slug` et de la géométrie), pas comme un maillon du pipeline Dagster. C'est donc bien ce circuit manuel que vise l'étape 6.

## Structure de la base Notion

| Colonne Notion | Type | Contenu |
|---|---|---|
| `Territoire` | titre | nom lisible de l'EPCI ou de la commune, ex. "Bordeaux Métropole" |
| `Description` | texte | résumé libre, à usage interne Notion — distinct du message final |
| `alert_slug` | texte | identifiant, voir "Format de l'alert_slug" ci-dessous |
| `data` | fichier | géométrie jointe (un fichier par ligne) |

## Format de l'alert_slug

Format constaté sur les entrées réelles de la base : `alert-{Territoire sans espaces ni accents}-{terme métier court}`, par exemple `alert-BordeauxMetropole-lgv`, `alert-RennesMetropole-habillage-pac`, `alert-MetropoleEuropeenneLille-isolation-et-financement`.

Deux parties, deux traitements très différents :
- **La partie territoire** est mécanique : `Territoire` avec ligatures translittérées (`œ` → `oe`…) et accents retirés, puis **seuls `A-Z a-z 0-9` conservés** — espaces, apostrophes, tirets des noms composés et tout autre caractère sont supprimés, casse d'origine conservée (ex. "Ville de Lille" → `VilledeLille`, "CC de l'Alsace Bossue" → `CCdelAlsaceBossue`, "CC de Hanau-La Petite Pierre" → `CCdeHanauLaPetitePierre`). Raison (décision du 13/10/2026) : `-` est le séparateur du slug, un tiret à l'intérieur d'un nom empêcherait de le découper. C'est plus strict que le champ Strapi `uid`, qui admet `A-Z a-z 0-9 - _ . ~` (règle de Strapi 5.13.0, appliquée seulement à la publication, pas au brouillon). Entièrement automatisable — c'est ce que produit `generer_export.py` (voir `etape-6-conception-technique.md`, "Contrat de données").
- **La partie "terme métier"** n'est **pas** une extraction ni un résumé du message ou de la description — c'est un terme technique du vocabulaire urbanisme/acoustique (`exhaussement`, `secteur-patrimonial-remarquable`, `speer3`, `pacte`...), qui n'apparaît parfois même pas dans le texte source. Exemple : la description "Réaliser des protections phoniques le long des voies bruyantes" donne le slug `exhaussement`, un terme absent du texte. Une génération automatique (LLM ou règle) risquerait de proposer un terme plausible mais faux : cette partie est donc laissée entièrement à la saisie de l'opérateur, dans `outil_validation.html` (voir `etape-6-conception-technique.md`, "Phase 2 — Outil de validation") — le script se limite à assembler la partie territoire, déjà calculée, en attente du terme métier.

**Convention du terme métier (décision du 19/10/2026)** : CamelCase, sans tiret (ex. `TraitementPaysager`, `LupsteinZoneUa`) — le tiret est réservé au séparateur des champs du slug. Les termes historiques en minuscules avec tirets (`habillage-pac`, Eurométropole) ne sont pas à imiter. Quand un même terme reviendrait pour deux communes d'un même territoire (cas fréquent d'un code de zone comme `ZoneUa`), la commune est placée devant le terme. Une proposition automatique des termes métier est prévue, voir `etape-6-conception-technique.md`, "Évolution prévue".

**Exception : les cas sans contenu métier (décision du 13/10/2026).** Pour les géométries sans règle bruit à nommer, le slug est rempli automatiquement en entier : `alert-{Territoire}-{Commune}{Suffixe}`, la commune étant slugifiée comme le territoire. Le cas est déterminé par `nature_zone` (étape 4), pas par le titre (texte validé à la main, qui peut avoir été retouché) :

| `nature_zone` | Titre associé | Suffixe | Exemple |
|---|---|---|---|
| `rnu` | Règlement National de l'Urbanisme applicable | `RNU` | `alert-CCdelAlsaceBossue-AsswillerRNU` |
| `trou_de_couverture` | Absence de document d'urbanisme référencé | `AbsenceGPU` | |
| `document_non_significatif` | Aucune prescription bruit spécifique | `PasDeReferenceBruit` | |
| `document_non_exploitable` | Document non analysable automatiquement | `DocNonAnalysable` | |

Les termes « prescription » et « recommandation » ont un sens précis en urbanisme : ils sont volontairement évités dans les suffixes. La règle ne s'applique qu'aux géométries couvrant **une seule commune** ; un PLUi (plusieurs communes) reste à saisir à la main.

**Statut d'un slug** — chaque `alert_slug_propose` est, à tout moment de la procédure :
- `vide` : aucun caractère (territoire non résolu) ;
- `initialisé` : proposition mécanique, finit par `-` (ex. `alert-CCdelAlsaceBossue-`) ;
- `automatisé` : rempli par la règle ci-dessus — au moins deux `-`, ne finit pas par `-` ;
- `manuel` : complété par l'opérateur — même forme qu'`automatisé`, distingué par comparaison avec ce que produirait la règle automatique.

Seuls les slugs `manuel` sont conservés quand `generer_export.py` est relancé ; les autres sont recalculés (voir `etape-6-conception-technique.md`, "Reprise à la régénération").

Points de vigilance relevés sur les données existantes, non reproduits comme règles :
- une entrée utilise `_` au lieu de `-` comme séparateur (`alert-RennesMetropole_charte_bretagne_dechet`) — incohérence de saisie manuelle, pas un format à imiter ;
- deux entrées partagent une racine commune avec un suffixe numérique de désambiguïsation (`vigilance-air-bruit-3` / `vigilance-air-bruit-1-2`) — cas à anticiper si deux géométries du même territoire portent un terme métier identique.

## Calcul du territoire

Ni `etape4_{dept}.gpkg` ni `etape5_{dept}.gpkg` ne portent de code INSEE ou de code SIREN d'EPCI pour une occurrence `occurrence_locale` — seule la colonne `communes` (texte libre, noms de commune) est disponible ; les codes ne sont renseignés qu'aux cas `rnu`/`trou_de_couverture` (voir `etape-4-conception-technique.md`, "Contrat de données").

Le territoire est donc **proposé automatiquement, jamais imposé** :
1. pour chaque commune de `communes`, résolution du code INSEE via l'API Découpage administratif (`geo.api.gouv.fr`, `GET /communes?nom={nom}&codeDepartement={dept}` — même principe qu'à l'étape 1, désambiguïsation par le département déjà connu du traitement) ;
2. récupération du `codeEpci` de chaque commune trouvée, puis de son nom via `GET /epcis/{siren}?fields=nom` ;
3. si toutes les communes de la ligne partagent le même EPCI : ce nom est proposé comme `territoire_propose`. Si elles diffèrent, ou si aucun EPCI n'est trouvé (commune isolée) : repli sur le(s) nom(s) de commune(s) tel(s) quel(s) ;
4. échec de résolution (nom introuvable, API indisponible) : `territoire_propose` reste vide, à charge de l'opérateur.

Cette proposition reste **modifiable dans le CSV final**, avant que l'opérateur ne saisisse le terme métier du slug.

## Assemblage du message pour Strapi

```
Message : {corps du message}
Docs sources : {liste, séparés par " / "}
références : {liste, séparés par " / ", même ordre que les documents}
```

Assemblage déterministe (pas de nouvel appel LLM), à partir de `message_synthese` (validé à l'étape 5) et de `etape5_{dept}_documents_par_synthese.csv` — donnée déjà fiable, jamais régénérée par un LLM. Le champ `nature` de ce fichier (repris tel quel de `type_piece_source`, calculé à l'étape 4) identifie chaque entrée de la liste "Docs sources" — pas de colonne `nom_document` séparée.

## Export des géométries

Un fichier `.geojson` par géométrie finale, nommé par `id_geometrie` (identifiant stable, indépendant de l'`alert_slug` qui n'existe pas encore complètement à ce stade du traitement) — à joindre manuellement au champ `data` de la ligne Notion correspondante, une fois celle-ci créée.

## Livrables de l'étape 6

- **`etape6_{dept}_export.csv`** — une ligne par géométrie finale, prête à guider la saisie Strapi + Notion (voir `etape-6-conception-technique.md`, "Contrat de données", pour le détail des colonnes).
- **`etape6_{dept}_geometries/`** — un fichier `.geojson` par géométrie finale.

## Écarté de cette étape

**Automatisation de la saisie Strapi par API** : techniquement réalisable — Strapi expose une API REST, un script Python pourrait créer les entrées directement avec un jeton d'API. Non retenue à cette étape, faute de visibilité à ce stade sur le schéma exact du content-type Strapi et sur les droits d'API disponibles côté préprod. Cette automatisation est reprise à l'étape 7, qui insère directement les entrées Strapi et Notion à partir de `etape6_{dept}_export.csv` et `etape6_{dept}_geometries/` (voir `etape-7-conception-technique.md`).

**Ingestion directe dans le pipeline Dagster/PostGIS** : écartée pour la même raison qu'au circuit métier ci-dessus — ce pipeline sert un usage interne à l'équipe de développement, pas celui que la partie métier emprunte pour transmettre une nouvelle règle.

## Prochaine étape

Étape 7 — automatisation de l'insertion dans Strapi et Notion à partir de `etape6_{dept}_export.csv` et `etape6_{dept}_geometries/` (voir `etape-7-conception-technique.md`).
