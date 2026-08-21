# Étape 6 — Mise en forme pour transmission à la partie développement

*Document de cadrage détaillé de l'étape 6 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-5-redaction-messages-diagbruit.md` et `etape-5-conception-technique.md`. Remplace la note de cadrage initiale, volontairement minimale, rédigée le 20/08/2026 lors de la conception de l'étape 5. Version issue des échanges du 21/08/2026.*

**Entrée** : `etape5_{dept}.gpkg` (couche unique `messages`, une ligne par géométrie finale — voir `etape-5-conception-technique.md`, "Contrat de données") et `etape5_{dept}_documents_par_synthese.csv` (un document par ligne, clé étrangère `id_geometrie_synthese`).

## Rappel du circuit métier actuel

*Point clarifié le 21/08/2026, après vérification directe du dépôt GitHub officiel de diagBruit et de la base Notion utilisée par la partie métier — voir "Points vérifiés" ci-dessous pour le détail de cette vérification.*

Le circuit reste, comme avant l'automatisation de l'analyse (étapes 1 à 5), le suivant :
1. La partie métier remplit le CMS Strapi (préprod) avec le message d'une zone, associé à un `alert_slug` unique.
2. La partie métier crée une entrée dans une base Notion, avec le même `alert_slug` et la géométrie associée (fichier joint).
3. La partie développement relie les deux pour mettre les géométries et messages à disposition de l'application diagBruit.

L'étape 6 ne cherche donc pas à ingérer directement une base de données de production : elle prépare, à partir des messages validés à l'étape 5, tout ce dont la partie métier a besoin pour réaliser rapidement les étapes 1 et 2 ci-dessus, sans ressaisie ni calcul manuel.

### Points vérifiés le 21/08/2026

Deux pistes explorées avant de confirmer le circuit ci-dessus, toutes deux écartées :

- **Le dépôt GitHub officiel** (`betagouv/diagbruit.beta.gouv.fr`) montre un pipeline d'ingestion automatisé pour les autres couches de données de diagBruit (Dagster → dbt → PostgreSQL/PostGIS → FastAPI, voir `README.md` et `CLAUDE.md` du dépôt). Strapi y est décrit comme un simple éditeur du **texte** des préconisations ("recommendation content management"), les géométries vivant entièrement dans PostGIS. Ce pipeline sert un usage interne à l'équipe de développement, pas la partie métier — écarté comme cible de cette étape.
- **La base Notion réelle** ("Données réglementaires locales (PLU, PPBE, …)", sous `Bdd Strapi > Bdd Sources`) confirme au contraire que Notion n'est utilisé que comme espace de coordination avec les développeurs (dépôt de l'`alert_slug` et de la géométrie), pas comme un maillon du pipeline Dagster. C'est donc bien ce circuit manuel que vise l'étape 6.

## Structure réelle de la base Notion

Consultée directement le 21/08/2026 :

| Colonne Notion | Type | Contenu observé |
|---|---|---|
| `Territoire` | titre | nom lisible de l'EPCI ou de la commune, ex. "Bordeaux Métropole" |
| `Description` | texte | résumé libre, à usage interne Notion — distinct du message final |
| `alert_slug` | texte | identifiant, voir "Format de l'alert_slug" ci-dessous |
| `data` | fichier | géométrie jointe (un fichier par ligne) |

## Format de l'alert_slug

Constaté sur 15 entrées réelles de la base : `alert-{Territoire sans espaces ni accents}-{terme métier court}`, par exemple `alert-BordeauxMetropole-lgv`, `alert-RennesMetropole-habillage-pac`, `alert-MetropoleEuropeenneLille-isolation-et-financement`.

Deux parties, deux traitements très différents :

- **La partie territoire** est mécanique : `Territoire` avec espaces et accents retirés, casse d'origine conservée (ex. "Ville de Lille" → `VilledeLille`). Entièrement automatisable.
- **La partie "terme métier"** n'est **pas** une extraction ni un résumé du message ou de la description — c'est un terme technique du vocabulaire urbanisme/acoustique (`exhaussement`, `secteur-patrimonial-remarquable`, `speer3`, `pacte`...), qui n'apparaît parfois même pas dans le texte source. Exemple frappant : la description "Réaliser des protections phoniques le long des voies bruyantes" donne le slug `exhaussement`, un terme absent du texte. Une génération automatique (LLM ou règle) risquerait de proposer un terme plausible mais faux. **Décidé le 21/08/2026** : cette partie est laissée entièrement à la saisie de l'opérateur — le script ne fait que l'assembler avec la partie territoire une fois saisie.

*Points de vigilance relevés sur les données existantes, non reproduits comme règles* :
- une entrée utilise `_` au lieu de `-` comme séparateur (`alert-RennesMetropole_charte_bretagne_dechet`) — incohérence de saisie manuelle, pas un format à imiter ;
- deux entrées partagent une racine commune avec un suffixe numérique de désambiguïsation (`vigilance-air-bruit-3` / `vigilance-air-bruit-1-2`) — cas à anticiper si deux géométries du même territoire portent un terme métier identique.

## Calcul du territoire

*Absent du pipeline actuel* : ni `etape4_{dept}.gpkg` ni `etape5_{dept}.gpkg` ne portent de code INSEE ou de code SIREN d'EPCI pour une occurrence `occurrence_locale` — seule la colonne `communes` (texte libre, noms de commune) est disponible ; les codes ne sont renseignés qu'aux cas `rnu`/`trou_de_couverture` (voir `etape-4-conception-technique.md`, "Contrat de données").

Le territoire est donc **proposé automatiquement, jamais imposé** :
1. pour chaque commune de `communes`, résolution du code INSEE via l'API Découpage administratif (`geo.api.gouv.fr`, `GET /communes?nom={nom}&codeDepartement={dept}` — même principe qu'à l'étape 1, désambiguïsation par le département déjà connu du traitement) ;
2. récupération du `codeEpci` de chaque commune trouvée, puis de son nom via `GET /epcis/{siren}?fields=nom` ;
3. si toutes les communes de la ligne partagent le même EPCI : ce nom est proposé comme `territoire_propose`. Si elles diffèrent, ou si aucun EPCI n'est trouvé (commune isolée) : repli sur le(s) nom(s) de commune(s) tel(s) quel(s) ;
4. échec de résolution (nom introuvable, API indisponible) : `territoire_propose` reste vide, à charge de l'opérateur.

Cette proposition reste **modifiable dans le CSV final**, avant que l'opérateur ne saisisse le terme métier du slug.

## Assemblage du message pour Strapi

Reprise du formalisme défini le 20/08/2026 :

```
Message : {corps du message}
Docs sources : {liste, séparés par " / "}
références : {liste, séparés par " / ", même ordre que les documents}
```

Assemblage déterministe (pas de nouvel appel LLM), à partir de `message_synthese` (validé à l'étape 5) et de `etape5_{dept}_documents_par_synthese.csv` — donnée déjà fiable, jamais régénérée par un LLM. Le champ `nature` (`type_piece_source`) identifie chaque entrée de la liste "Docs sources" (décision du 20/08/2026, pas de colonne `nom_document` séparée).

## Export des géométries

Un fichier `.geojson` par géométrie finale, nommé par `id_geometrie` (identifiant stable, indépendant de l'`alert_slug` qui n'existe pas encore complètement à ce stade du traitement) — à joindre manuellement au champ `data` de la ligne Notion correspondante, une fois celle-ci créée.

## Livrables de l'étape 6

- **`etape6_{dept}_export.csv`** — une ligne par géométrie finale, prête à guider la saisie Strapi + Notion (voir `etape-6-conception-technique.md`, "Contrat de données", pour le détail des colonnes).
- **`etape6_{dept}_geometries/`** — un fichier `.geojson` par géométrie finale.

## Écarté de cette étape

**Automatisation de la saisie Strapi par API** (question posée le 21/08/2026) : techniquement réalisable — Strapi expose une API REST, un script Python pourrait créer les entrées directement avec un jeton d'API. Non retenu pour cette étape, faute de visibilité sur le schéma exact du content-type Strapi (nom des champs) et sur les droits d'API disponibles côté préprod. Repoussé à une itération ultérieure si la partie développement confirme l'intérêt et fournit l'accès nécessaire.

**Ingestion directe dans le pipeline Dagster/PostGIS** : écarté après vérification — ce pipeline sert un usage interne à l'équipe de développement (voir "Points vérifiés" ci-dessus), pas celui que la partie métier emprunte pour transmettre une nouvelle règle.

## Prochaine étape

Étape 7 — dans son acception initiale ("stockage des données dans le répertoire dédié", voir `plan-automatisation-regles-plu-diagbruit.md`), cette étape est en pratique déjà couverte par la saisie manuelle dans Strapi et Notion à partir des livrables ci-dessus, une fois `description_slug` complété par l'opérateur. Reste ouvert, si le besoin se confirme à l'usage : l'automatisation de la saisie Strapi par API (voir "Écarté de cette étape").
