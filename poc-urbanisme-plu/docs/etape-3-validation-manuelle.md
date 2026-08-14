# Étape 3 — Validation manuelle des occurrences liées au bruit
 
*Document de cadrage détaillé de l'étape 3 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-2-analyse-documents-urbanisme-diagbruit.md` et `etape-2-conception-technique.md`. Version issue des échanges du 14/08/2026.*
 
**Entrée** : le CSV `etape2_{dept}.csv` produit par l'étape 2, dans son intégralité — y compris les lignes dont `statut_verification` vaut `aucune occurrence trouvée`. Ces lignes ne sont jamais présentées à l'opérateur, mais restent nécessaires au calcul final (voir "Agrégation par document" plus bas).
 
## Principe
 
L'étape 2 produit une classification automatique, occurrence par occurrence : est-ce une règle liée au bruit, avec quelle citation, quelle confiance. L'étape 3 fait relire cette classification par un opérateur humain avant que la donnée ne serve de base à la construction de géométries (étape 4) et de messages (étape 5).
 
Deux objectifs guident sa conception : produire en sortie un tableau fiable des occurrences que diagBruit doit effectivement mentionner (objectif métier), et permettre à l'opérateur de traiter le plus grand nombre d'occurrences possible dans le temps disponible (objectif de productivité). C'est l'étape la plus délicate du plan jusqu'ici, parce qu'elle met un humain, pas un appel API, au centre du traitement.
 
## Grain de la validation
 
La validation porte sur l'occurrence — une ligne du CSV d'étape 2 — pas sur le document. Un même document (`id_gpu`) peut ainsi avoir certaines occurrences retenues et d'autres écartées.
 
## Filtre de présentation
 
Seules les occurrences dont `statut_verification` vaut `validé` ou `à vérifier (renvoi CSV-PEB potentiel)` sont présentées à l'opérateur — les deux seules valeurs associées à une classification `retenu=true` en étape 2. Les lignes `aucune occurrence trouvée` ne nécessitent aucune relecture : elles recevront directement une géométrie automatique en phase A de l'étape 4 (voir `plan-automatisation-regles-plu-diagbruit.md`).
 
## Contexte enrichi
 
L'`id_gpu` est un identifiant opaque pour un opérateur humain. Chaque occurrence présentée est enrichie, par jointure avec `etape1_{dept}.csv`, du nom du document et de la ou des communes qu'il couvre — pour qu'un opérateur puisse juger de la plausibilité d'une occurrence sans rouvrir un autre fichier.
 
## Priorisation
 
Les occurrences sont regroupées par document, pour que l'opérateur garde le contexte d'un règlement en tête pendant sa relecture. Au sein d'un document, elles sont ordonnées en mettant en avant celles qui méritent le plus d'attention : `confiance_extrait` faible et/ou `ocr_confiance` faible en tête. L'opérateur peut aussi retrier ou filtrer librement dans l'outil (voir `etape-3-conception-technique.md`).
 
## Édition en une seule passe
 
*Révisé le 14/08/2026, suite à un premier usage réel de l'outil.*
 
Les champs de classification (`zone_reglementaire_mentionnee`, `statut_verification`, `nature_occurrence`, `nature_juridique_piece`, `nature_sonore_zone`, etc.) sont modifiables directement par l'opérateur au moment de la relecture — pour éviter une double passe ("je repère une erreur" puis "je vais la corriger ailleurs"). Le champ libre `validation_manuelle_commentaire` sert aussi, en pratique, à noter des éléments utiles à la future reformulation du message (étape 5), pas seulement à justifier une décision.
 
`extrait_significatif` et `contexte_documentaire`, en revanche, sont des informations issues telles quelles du document source : elles ne sont **pas** destinées à être modifiées par l'opérateur, même si leur découpage peut être imparfait (voir "Repérage de la citation dans son contexte" dans `etape-3-conception-technique.md`). L'outil les affiche en lecture seule, réunis dans un seul bloc "Citation significative et contexte" avec la citation surlignée dans son contexte — sans zone de saisie associée.
 
## États de validation
 
Chaque occurrence reçoit un nouveau champ `validation_manuelle_statut`, à trois valeurs :
 
- **validé** — l'opérateur confirme l'occurrence sans y toucher.
- **corrigé** — l'opérateur a modifié au moins un champ avant de confirmer l'occurrence.
- **rejeté** — l'opérateur écarte l'occurrence (ce n'est finalement pas une règle de bruit dans le périmètre diagBruit).
Un champ `validation_manuelle_commentaire`, libre et facultatif, permet de préciser une décision.
 
Une occurrence rejetée n'est jamais supprimée du CSV de sortie — elle est conservée à part, pour la traçabilité, dans le même esprit que le reste du pipeline (cf. les lignes `aucune occurrence trouvée` de l'étape 2, déjà conservées pour la même raison).
 
## Agrégation par document
 
Un document dont aucune occurrence n'est retenue — qu'il n'en ait jamais eu (`aucune occurrence trouvée` nativement en sortie d'étape 2) ou que toutes celles présentées à l'opérateur aient été rejetées ou laissées non traitées — est considéré **non significatif**. Il donne lieu, en sortie d'étape 3, à une seule ligne de synthèse (`statut_verification_finale = "aucune occurrence trouvée"`), plutôt qu'à autant de lignes que d'occurrences écartées.
 
## Occurrences non traitées
 
Une occurrence présentée à l'opérateur mais jamais statuée (ni validée, ni corrigée, ni rejetée) au moment de la synthèse finale est traitée par précaution comme non retenue — elle n'entre pas dans le calcul de significativité de son document, et elle est listée séparément pour reprise, plutôt que silencieusement ignorée ou comptée comme validée.
 
## Outil support
 
La relecture se fait dans une page HTML autonome et réutilisable, chargée avec le CSV du département à traiter (voir `etape-3-conception-technique.md`). Ce choix a été fait après comparaison avec un export markdown et un export xlsx formaté : la page HTML offre le plus de contrôle sur la mise en page (regroupement par document, priorisation, filtres, édition en une passe) sans imposer d'outil supplémentaire à installer — une page web s'ouvre nativement dans un navigateur.
 
Contrainte technique assumée : sans stockage navigateur possible pour ce type d'outil, la progression n'existe qu'en mémoire tant qu'elle n'a pas été exportée. L'outil combine un export manuel à la demande et un export automatique périodique pour limiter le risque de perte de travail.
 
## Prochaine étape
 
Étape 4 — assignation d'une géométrie aux occurrences produites par cette étape (contour administratif pour les documents non significatifs, zone réglementaire ou repli administratif pour les documents significatifs).