# Plan d'action — Automatisation de l'intégration des règles d'urbanisme liées au bruit dans diagBruit

*Document de cadrage — version issue des échanges du 11/08/2026. Chaque étape fera l'objet d'un échange dédié pour le détail de mise en œuvre. Étapes 3, 4 et 5 précisées lors des échanges du 14/08/2026, à l'issue de l'implémentation de l'étape 2 (voir `etape-2-analyse-documents-urbanisme-diagbruit.md` et `etape-2-conception-technique.md`). Révisé le 17/08/2026 : RNU et trou de couverture sont réintégrés dès l'étape 3, pas à l'étape 6 (voir "Points de vigilance retenus").*

## Objectif final

Ajouter automatiquement dans diagBruit de nouvelles règles issues des plans locaux d'urbanisme (PLU, PLUi, RNU, POS, cartes communales...) disponibles sur le Géoportail de l'urbanisme, en complément des informations déjà fournies par diagBruit (plan d'exposition au bruit, classement sonore des voies).

## Les deux échelles du produit

diagBruit fonctionne sur deux échelles distinctes qu'il ne faut pas confondre :

- **Échelle d'intégration d'un territoire** : le **département**. diagBruit n'est pas disponible France entière ; les territoires sont ajoutés progressivement, département par département.
- **Échelle d'utilisation** : la **parcelle cadastrale**. C'est le niveau auquel l'utilisateur final interroge l'outil.

Le présent plan porte sur la **création de la donnée à l'échelle départementale** (le pivot amont), qui sera ensuite consommée à l'échelle parcellaire par une requête SIG d'intersection.

## Sortie visée

Une **couverture SIG complète du département**, composée de surfaces qui traduisent les endroits où s'appliquent des règles d'urbanisme liées au bruit (hors classement sonore et plan d'exposition au bruit, déjà traités par ailleurs).

Règles de construction de cette couverture :
- Plusieurs surfaces peuvent se **chevaucher** si plusieurs règles s'appliquent à un même endroit.
- En revanche, **un seul document d'urbanisme en vigueur** doit être pris en compte par localisation (le PLU, le PLUi, le RNU, le POS ou la carte communale actuellement opposable — jamais une version archivée, et pas de superposition PLU/PLUi puisqu'une commune intégrée à un PLUi n'a normalement plus de PLU propre en vigueur).
- La granularité visée est celle de la **zone réglementaire** (et non la commune), quitte à ce que la construction de cette zone reste manuelle dans un premier temps — auquel cas un message explicite sur l'origine et la précision de la donnée sera nécessaire.

Le pivot fonctionnel : diagBruit interroge cette couverture via une **requête SIG d'intersection** entre la géométrie de la parcelle cadastrale et les géométries des zones précédemment créées.

## Schéma du plan

```mermaid
flowchart TD
    Dept["Code département (3 chiffres)"] --> E1["Étape 1 — Identifier les documents d'urbanisme en vigueur"]
    E1 --> E2["Étape 2 — Analyser les documents : repérage des règles liées au bruit"]
    E2 --> E3["Étape 3 — Validation manuelle des occurrences"]
    E3 -->|"Document non significatif"| E4A["Étape 4 · Phase A — Contour administratif (automatique)"]
    E3 -->|"Document significatif"| E4Bgate{"Étape 4 · Phase B — Portée de l'occurrence"}
    E4Bgate -->|"Limite administrative"| E4B1["Alinéa 1 — Géométrie automatisée"]
    E4Bgate -->|"Limite réglementaire spécifique"| E4B2["Alinéa 2 — Traitement à définir"]
    E4B1 --> E5["Étape 5 — Rédaction du ton du message"]
    E4B2 --> E5
    E4A -->|"Message standard"| E6["Étape 6 — Mise en forme pour ingestion"]
    E5 --> E6
    E6 --> E7["Étape 7 — Stockage"]
    E7 --> Couv[("Couverture SIG départementale diagBruit")]
    Couv -.-> Usage["Utilisation finale : intersection SIG avec la parcelle cadastrale"]
```

*Note du 17/08/2026 : ce schéma reste valable au niveau où il est dessiné (le flux global département → couverture SIG). Il ne détaille pas le cas RNU/trou de couverture, qui rejoint le flux normal dès l'étape 3 plutôt que d'apparaître comme une branche séparée — voir "Points de vigilance retenus" ci-dessous pour le détail.*

## Étapes du plan

1. **Identifier les documents d'urbanisme en vigueur du département**, à partir du code département (3 chiffres), via le Géoportail de l'urbanisme.
2. **Analyser ces documents** (règlements écrits + couches structurées de prescriptions du GPU) pour repérer toute mention de recommandation ou de prescription liée au bruit. Cette phase détermine aussi la **portée géométrique** de chaque règle repérée (administrative ou zone réglementaire spécifique), qui pilote directement l'étape 4.
3. **Validation manuelle des occurrences produites à l'étape 2** : un opérateur relit les occurrences (lignes du CSV `etape2_{dept}.csv`) dont le `statut_verification` vaut `validé` ou `à vérifier (renvoi CSV-PEB potentiel)`. Le grain de la validation est l'occurrence, pas le document entier. Un document dont toutes les occurrences sont écartées — nativement en sortie d'étape 2, ou après validation — devient **non significatif**. Cette même étape réintègre aussi, sous forme de lignes de synthèse, les communes au RNU et les trous de couverture (voir "Points de vigilance retenus").
4. **Création des géométries**, en deux phases :
   - **Phase A — documents non significatifs, communes RNU et trous de couverture** : récupération automatique de la géométrie de contour administratif (commune ou EPCI), sans relecture manuelle.
   - **Phase B — documents significatifs** : la géométrie dépend de la portée de chaque occurrence validée (champ `portee_geometrique`, déterminé à l'étape 2 et corrigeable à l'étape 3).
     - *Alinéa 1* — portée `administrative` : automatisable, par repli sur le contour du document, de la commune ou de l'EPCI.
     - *Alinéa 2* — portée `zone_specifique` : tracé manuel dans un outil SIG (QGIS), faute de source automatique fiable à la granularité de la zone réglementaire.
5. **Rédaction du ton** des messages associés aux occurrences validées des documents significatifs (ton à définir).
6. **Mise en forme** des données selon le format attendu pour ingestion dans la base diagBruit — inclut les gabarits de message pour les documents non significatifs, les communes RNU et les trous de couverture.
7. **Stockage** des données dans le répertoire dédié.

## Points de vigilance retenus

- Utiliser systématiquement le **document d'urbanisme en vigueur** (pas de version archivée), en excluant les superpositions PLU/PLUi.
- Un PLUi n'exclut pas l'existence d'un **PSMV** en parallèle sur certaines communes — à garder en tête.
- Un **document non significatif** (aucune occurrence de bruit retenue) doit toujours préciser la **source du document analysé**, pour la traçabilité.
- **(Révisé le 17/08/2026)** Traitement des communes sous **RNU** : une version antérieure de ce plan prévoyait un message dédié "en amont de l'étape 2", traité isolément à l'étape 6. Ce n'est plus le cas — les communes RNU sont désormais réintégrées dès l'étape 3 (lignes de synthèse construites depuis `etape1_{dept}.csv`) et reçoivent une géométrie dès l'étape 4 (Phase A, au même titre qu'un document non significatif), au lieu d'être traitées à part au moment de la mise en forme finale. Le régime national qu'elles portent n'est pas une absence de règle : l'article R.111-2 du code de l'urbanisme permet de refuser un projet ou de le conditionner à des prescriptions spéciales pour atteinte à la salubrité ou à la sécurité publique, ce qui couvre les nuisances sonores.
- **(Ajouté le 17/08/2026)** Traitement des **trous de couverture** : même trajectoire que le RNU (réintégration à l'étape 3, géométrie à l'étape 4, Phase A), mais sans contenu de règle — c'est une anomalie de données, pas un régime applicable. Un champ dédié (`nature_zone`, voir `etape-3-conception-technique.md`) distingue ce cas des autres à l'intérieur de la Phase A, notamment pour permettre une symbologie SIG différenciée (zones couvertes par une donnée vs. zones à investiguer) dans l'outil de l'étape 4.

## Améliorations retenues

- **A. Couches structurées "prescriptions" du GPU** : à utiliser en complément de la lecture des règlements PDF, comme signal structuré à croiser avec l'analyse IA du texte.
- **B. Pré-filtrage par mots-clés** avant analyse IA complète des règlements, pour réduire le volume traité et faciliter la vérification. La liste des mots-clés reste à définir.

## Prochaine étape

**(Mise à jour du 19/08/2026)** Conception détaillée de l'étape 5 faite — voir `etape-5-redaction-messages-diagbruit.md` et `etape-5-conception-technique.md`. Prochaine étape : implémentation de l'étape 5, en commençant par la Phase 2 (génération des messages par LLM), avant de concevoir l'outil de validation humaine (Phase 3, non conçu à ce stade).

**(Mise à jour du 21/08/2026)** Étapes 5 et 6 implémentées. Cadrage initial de l'étape 7 (automatisation de la saisie Strapi/Notion, aujourd'hui manuelle) démarré — voir `etape-7-stockage-diagbruit.md` — mais bloqué sur plusieurs points ouverts (accès API Strapi/Notion, contenu de la colonne Notion `Description`, pièce jointe géométrie, idempotence) avant de pouvoir passer à une conception technique détaillée puis à l'implémentation.
