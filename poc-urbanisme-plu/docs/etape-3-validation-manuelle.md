# Étape 3 — Validation manuelle des occurrences liées au bruit

*Document de cadrage détaillé de l'étape 3 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-2-analyse-documents-urbanisme-diagbruit.md` et `etape-2-conception-technique.md`. Révisé le 17/08/2026 suite à la conception de l'étape 4 : réintégration des communes RNU et des trous de couverture directement à cette étape (et non plus à l'étape 6), ajout des champs `nature_zone` et `code_insee_commune`.*

**Entrée** : le CSV `etape2_{dept}.csv` produit par l'étape 2, dans son intégralité — y compris les lignes dont `statut_verification` vaut `aucune occurrence trouvée`. Ces lignes ne sont jamais présentées à l'opérateur, mais restent nécessaires au calcul final (voir "Agrégation par document" plus bas). **(Précision du 17/08/2026)** `etape1_{dept}.csv` est également une entrée directe de cette étape, pas seulement une source de contexte pour l'enrichissement : les lignes `RNU confirmé` et `trou de couverture`, qui n'existent nulle part dans `etape2_{dept}.csv`, y sont lues pour être réintégrées dans le pipeline (voir "RNU et trou de couverture : réintégration dans le pipeline").

## Principe

L'étape 2 produit une classification automatique, occurrence par occurrence : est-ce une règle liée au bruit, avec quelle citation, quelle confiance. L'étape 3 fait relire cette classification par un opérateur humain avant que la donnée ne serve de base à la construction de géométries (étape 4) et de messages (étape 5).

Deux objectifs guident sa conception : produire en sortie un tableau fiable des occurrences que diagBruit doit effectivement mentionner (objectif métier), et permettre à l'opérateur de traiter le plus grand nombre d'occurrences possible dans le temps disponible (objectif de productivité). C'est l'étape la plus délicate du plan jusqu'ici, parce qu'elle met un humain, pas un appel API, au centre du traitement.

## Grain de la validation

La validation porte sur l'occurrence — une ligne du CSV d'étape 2 — pas sur le document. Un même document (`id_gpu`) peut ainsi avoir certaines occurrences retenues et d'autres écartées.

## Filtre de présentation

Seules les occurrences dont `statut_verification` vaut `validé` ou `à vérifier (renvoi CSV-PEB potentiel)` sont présentées à l'opérateur — les deux seules valeurs associées à une classification `retenu=true` en étape 2. Les lignes `aucune occurrence trouvée` ne nécessitent aucune relecture : elles recevront directement une géométrie automatique à l'étape 4. **(Précision du 17/08/2026)** Les communes RNU et les trous de couverture ne passent pas non plus par l'outil de relecture, et pour la même raison : il n'y a rien à faire lire à un opérateur (pas de citation extraite d'un PDF à vérifier) — voir la section dédiée ci-dessous.

## Contexte enrichi

L'`id_gpu` est un identifiant opaque pour un opérateur humain. Chaque occurrence présentée est enrichie, par jointure avec `etape1_{dept}.csv`, du nom du document et de la ou des communes qu'il couvre — pour qu'un opérateur puisse juger de la plausibilité d'une occurrence sans rouvrir un autre fichier.

## Priorisation

Les occurrences sont regroupées par document, pour que l'opérateur garde le contexte d'un règlement en tête pendant sa relecture. Au sein d'un document, elles sont ordonnées en mettant en avant celles qui méritent le plus d'attention : `confiance_extrait` faible et/ou `ocr_confiance` faible en tête. L'opérateur peut aussi retrier ou filtrer librement dans l'outil (voir `etape-3-conception-technique.md`).

## Édition en une seule passe

*Révisé le 14/08/2026, suite à un premier usage réel de l'outil.*

Les champs de classification (`zone_reglementaire_mentionnee`, `portee_geometrique`, `statut_verification`, `nature_occurrence`, `nature_juridique_piece`, `nature_sonore_zone`, etc.) sont modifiables directement par l'opérateur au moment de la relecture — pour éviter une double passe ("je repère une erreur" puis "je vais la corriger ailleurs"). **(Ajout du 17/08/2026)** `portee_geometrique` rejoint la liste des champs à liste déroulante (comme `nature_occurrence` ou `nature_juridique_piece`) : c'est lui qui, en sortie de cette étape, décide si une occurrence recevra une géométrie automatique ou un tracé manuel à l'étape 4 — un mauvais classement par le modèle en phase 4 de l'étape 2 (ex. une règle en réalité limitée à une zone "UA" classée à tort "administrative") doit donc pouvoir être corrigé ici, avant que son sort géométrique ne soit scellé. Le champ libre `validation_manuelle_commentaire` sert aussi, en pratique, à noter des éléments utiles à la future reformulation du message (étape 5), pas seulement à justifier une décision.

`extrait_significatif` et `contexte_documentaire`, en revanche, sont des informations issues telles quelles du document source : elles ne sont **pas** destinées à être modifiées par l'opérateur, même si leur découpage peut être imparfait (voir "Repérage de la citation dans son contexte" dans `etape-3-conception-technique.md`). L'outil les affiche en lecture seule, réunis dans un seul bloc "Citation significative et contexte" avec la citation surlignée dans son contexte — sans zone de saisie associée.

## États de validation

Chaque occurrence reçoit un nouveau champ `validation_manuelle_statut`, à trois valeurs :

- **validé** — l'opérateur confirme l'occurrence sans y toucher.
- **corrigé** — l'opérateur a modifié au moins un champ avant de confirmer l'occurrence.
- **rejeté** — l'opérateur écarte l'occurrence (ce n'est finalement pas une règle de bruit dans le périmètre diagBruit).
Un champ `validation_manuelle_commentaire`, libre et facultatif, permet de préciser une décision.

Une occurrence rejetée n'est jamais supprimée du CSV de sortie — elle est conservée à part, pour la traçabilité, dans le même esprit que le reste du pipeline (cf. les lignes `aucune occurrence trouvée` de l'étape 2, déjà conservées pour la même raison).

**(Précision du 17/08/2026)** `validation_manuelle_statut` ne concerne que les occurrences réellement soumises à l'outil de relecture. Les lignes de synthèse — documents non significatifs, RNU, trous de couverture — n'y passent jamais : `validation_manuelle_statut` y reste vide par construction, et c'est le champ distinct `statut_verification_finale` (voir "Agrégation par document" et la section RNU ci-dessous) qui porte leur statut final.

## Agrégation par document

Un document dont aucune occurrence n'est retenue — qu'il n'en ait jamais eu (`aucune occurrence trouvée` nativement en sortie d'étape 2) ou que toutes celles présentées à l'opérateur aient été rejetées ou laissées non traitées — est considéré **non significatif**. Il donne lieu, en sortie d'étape 3, à une seule ligne de synthèse (`statut_verification_finale = "aucune occurrence trouvée"`, `nature_zone = "document_non_significatif"`), plutôt qu'à autant de lignes que d'occurrences écartées.

## RNU et trou de couverture : réintégration dans le pipeline

*Section ajoutée le 17/08/2026, suite aux échanges sur l'étape 4.*

Une version précédente du plan (voir `etape-2-analyse-documents-urbanisme-diagbruit.md`, version antérieure au 17/08/2026) prévoyait de traiter les communes RNU et les trous de couverture directement à l'étape 6, sans passer par les étapes 3 et 4. Ce n'était pas tenable : la couverture SIG finale de diagBruit doit couvrir tout le département, RNU et trous de couverture compris, et une géométrie ne peut être construite qu'à l'étape 4 — qui a besoin d'un CSV d'entrée homogène (`etape3_{dept}.csv`) pour rester simple. C'est donc ici, dans `synthese_finale.py`, que ces deux cas sont désormais réintégrés, sous forme de lignes de synthèse construites directement depuis `etape1_{dept}.csv` — sans jamais passer par l'outil de relecture, puisqu'il n'y a rien à faire vérifier à un humain dans un texte qui n'existe pas.

**RNU confirmé.** Chaque commune `statut = "RNU confirmé"` d'`etape1_{dept}.csv` donne lieu à une ligne de synthèse avec :
- `portee_geometrique = "administrative"` — assigné directement par le script, pas par un modèle : le régime s'applique à l'ensemble du territoire communal, il n'y a pas d'ambiguïté à trancher ;
- `statut_verification_finale = "validé automatique"` — nouvelle valeur, distincte de `validé` (voir "États de validation" ci-dessus) : elle rend explicite qu'aucun opérateur n'a relu cette ligne, contrairement à une occurrence extraite d'un vrai document ;
- `justification` pré-remplie citant l'article R.111-2 du code de l'urbanisme, qui permet à l'autorité compétente de refuser un projet ou de le conditionner à des prescriptions spéciales s'il porte atteinte à la salubrité ou à la sécurité publique — la jurisprudence y range les nuisances sonores (voir `etape-2-analyse-documents-urbanisme-diagbruit.md`) ;
- `nature_zone = "rnu"`.

Le RNU n'a jamais d'`id_gpu` (par définition, aucun document GPU ne le porte) : la ligne utilise à la place `code_insee_commune`, nouvelle colonne (voir "Contrat de données" dans `etape-3-conception-technique.md`), comme clé pour la récupération de géométrie à l'étape 4.

**Trou de couverture.** Chaque commune `statut = "trou de couverture"` donne lieu à une ligne de synthèse avec `nature_zone = "trou_de_couverture"` et `statut_verification_finale = "aucune occurrence trouvée"` (même valeur qu'un document non significatif — la distinction entre les deux cas se lit dans `nature_zone`, pas dans `statut_verification_finale`, pour ne pas multiplier les valeurs d'un champ qui garde par ailleurs le même sens qu'avant). Contrairement au RNU, il n'y a ici aucune règle de fond : la géométrie sert uniquement à visualiser, dans l'outil SIG de l'étape 4, les zones du département où la couverture de données est incomplète — pas à produire un message pour l'utilisateur final de diagBruit. Même clé de repli que le RNU : `code_insee_commune`.

## Occurrences non traitées

Une occurrence présentée à l'opérateur mais jamais statuée (ni validée, ni corrigée, ni rejetée) au moment de la synthèse finale est traitée par précaution comme non retenue — elle n'entre pas dans le calcul de significativité de son document, et elle est listée séparément pour reprise, plutôt que silencieusement ignorée ou comptée comme validée.

## Outil support

La relecture se fait dans une page HTML autonome et réutilisable, chargée avec le CSV du département à traiter (voir `etape-3-conception-technique.md`). Ce choix a été fait après comparaison avec un export markdown et un export xlsx formaté : la page HTML offre le plus de contrôle sur la mise en page (regroupement par document, priorisation, filtres, édition en une passe) sans imposer d'outil supplémentaire à installer — une page web s'ouvre nativement dans un navigateur.

Contrainte technique assumée : sans stockage navigateur possible pour ce type d'outil, la progression n'existe qu'en mémoire tant qu'elle n'a pas été exportée. L'outil combine un export manuel à la demande et un export automatique périodique pour limiter le risque de perte de travail.

## Prochaine étape

Étape 4 — assignation d'une géométrie à chaque ligne produite par cette étape : contour administratif automatique (documents non significatifs, RNU, trous de couverture, occurrences à `portee_geometrique = "administrative"`) ou tracé manuel dans QGIS (occurrences à `portee_geometrique = "zone_specifique"`) — voir `etape-4-construction-geometries-diagbruit.md` et `etape-4-conception-technique.md`.
