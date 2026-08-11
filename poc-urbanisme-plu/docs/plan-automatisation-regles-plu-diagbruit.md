# Plan d'action — Automatisation de l'intégration des règles d'urbanisme liées au bruit dans diagBruit
 
*Document de cadrage — version issue des échanges du 11/08/2026. Chaque étape fera l'objet d'un échange dédié pour le détail de mise en œuvre.*
 
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
 
## Étapes du plan
 
1. **Identifier les documents d'urbanisme en vigueur du département**, à partir du code département (3 chiffres), via le Géoportail de l'urbanisme.
2. **Analyser ces documents** (règlements écrits + couches structurées de prescriptions du GPU) pour repérer toute mention de recommandation ou de prescription liée au bruit.
3. **Cas 1 — aucune mention trouvée** : délimiter la zone couverte par le document (récupérée sur le Géoportail de l'urbanisme) et produire un message standard, en explicitant clairement la source du document pris en compte.
4. **Cas 2 — mentions trouvées** : délimiter la zone concernée par la mention (granularité zone, pas commune) et rédiger un message spécifique selon un ton à définir.
5. **Vérification** des informations produites (délimitation + message) avant intégration.
6. **Mise en forme** des données selon le format attendu pour ingestion dans la base diagBruit.
7. **Stockage** des données dans le répertoire dédié.
## Points de vigilance retenus
 
- Utiliser systématiquement le **document d'urbanisme en vigueur** (pas de version archivée), en excluant les superpositions PLU/PLUi.
- Un PLUi n'exclut pas l'existence d'un **PSMV** en parallèle sur certaines communes — à garder en tête.
- Le cas "aucune mention bruit" (cas 1) doit toujours préciser la **source du document analysé**, pour la traçabilité.
- Prévoir un traitement pour les communes sous **RNU** (rattachées au cas 1).
## Améliorations retenues
 
- **A. Couches structurées "prescriptions" du GPU** : à utiliser en complément de la lecture des règlements PDF, comme signal structuré à croiser avec l'analyse IA du texte.
- **B. Pré-filtrage par mots-clés** avant analyse IA complète des règlements, pour réduire le volume traité et faciliter la vérification. La liste des mots-clés reste à définir.
## Prochaine étape
 
Détailler l'**étape 1** : définir le processus permettant de créer, à l'échelle départementale, la liste des documents d'urbanisme en vigueur à analyser.