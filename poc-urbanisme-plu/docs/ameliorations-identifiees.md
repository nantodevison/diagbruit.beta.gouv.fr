# Améliorations identifiées (non mises en œuvre)

*Document unique recensant, pour l'ensemble du POC, les limites connues du
code actuel pour lesquelles une correction a été envisagée mais n'a pas été
retenue à ce stade. Chaque chapitre précise l'étape ou les étapes du pipeline
concernées, indique le contexte et le problème, puis la ou les pistes de
correction envisageables. Les chapitres sont classés par ordre croissant des
étapes auxquelles ils se rapportent. Distinct des documents de cadrage
métier et de conception technique de chaque étape, qui décrivent le
fonctionnement retenu plutôt que ses limites.*

## Répétition dans `contexte_documentaire` quand la citation déborde sur le contexte

**Étape concernée : 2.**

**Contexte** : la colonne `contexte_documentaire` du CSV de synthèse concatène, dans l'ordre de lecture du document, `contexte_avant` + `extrait_significatif` (la citation choisie par le modèle) + `contexte_apres`. Il s'agit d'une concaténation simple, sans logique de déduplication.

**Problème** : le modèle est invité à puiser sa citation dans le passage *et* dans son contexte immédiat quand la règle y déborde (c'est précisément ce qui corrige les citations tronquées par le découpage mécanique en blocs). Quand `extrait_significatif` recouvre effectivement une partie de `contexte_avant` ou `contexte_apres`, cette portion se retrouve donc affichée deux fois dans `contexte_documentaire`. Exemple réel (département 067, pièce `246700488_orientations_amenagement_1_20260206.pdf`) :

> "...les constructions situées dans les zones de bruit liées aux infrastructures de transport **les constructions situées dans les zones de bruit liées aux infrastructures de transport** terrestre feront l'objet de dispositifs d'isolation acoustique."

**Impact** : cosmétique, pas fonctionnel. La répétition reste immédiatement reconnaissable par un relecteur humain et ne change ni la classification ni les autres colonnes. N'affecte pas la fiabilité de la vérification humaine, seulement son confort de lecture sur certaines lignes.

**Piste de correction** : avant concaténation, détecter le chevauchement entre le début/la fin d'`extrait_significatif` et la fin de `contexte_avant` / le début de `contexte_apres` (recherche de la plus longue sous-chaîne commune aux deux bornes), et tronquer le contexte de la portion déjà couverte par la citation. Priorité jugée secondaire face à un simple défaut de confort de lecture.

## `confiance_extrait` mélange deux raisons différentes de valoir "faible"

**Étape concernée : 2.**

**Contexte** : `confiance_extrait` mesure la clarté/l'autonomie de la citation choisie par le modèle (`extrait_significatif`) — un fragment coupé, ou mélangeant deux sujets, vaut "faible". Le prompt de classification demande aussi de taguer "faible" une règle par ailleurs parfaitement claire mais qui ne concerne qu'un projet d'infrastructure de transport (hors périmètre habituel de diagBruit : construction de bâtiments, aménagement urbain).

**Problème** : ces deux situations n'ont rien à voir (l'une est un défaut d'extraction, l'autre une question de pertinence du sujet) mais partagent la même valeur de colonne. Un relecteur qui filtre sur `confiance_extrait = "faible"` pour prioriser sa vérification ne peut pas distinguer les deux cas sans ouvrir `justification` et la lire.

**Palliatif en place** : le prompt exige explicitement que `justification` précise laquelle des deux raisons s'applique quand `confiance_extrait = "faible"` — l'information reste donc disponible, seulement pas dans une colonne filtrable dédiée.

**Piste de correction** : séparer les deux notions dans deux colonnes distinctes, par exemple garder `confiance_extrait` pour la seule clarté de la citation, et ajouter un champ dédié (booléen ou enum, ex. `hors_perimetre_batiment`) pour le critère de périmètre diagBruit. Plus facilement filtrable/triable dans le CSV, au prix d'une colonne supplémentaire et d'un ajustement du schéma de structured output. Non retenu pour l'instant, cohérent avec la posture POC (ajouter une colonne seulement quand l'usage réel le justifie) ; à reconsidérer si la relecture humaine montre que le mélange gêne effectivement le tri des résultats.

## Périmètre des pièces analysées limité à quatre types de fichiers

**Étape concernée : 2.**

**Contexte** : `resolution_pieces.py` (phase 1) ne retient, parmi tous les fichiers d'un document GPU, que ceux dont le nom correspond sans ambiguïté au règlement écrit, à l'OAP, au PADD ou au règlement d'un PSMV. Le rapport de présentation, les plans graphiques, les pièces de procédure et les servitudes annexées sont exclus de l'analyse.

**Impact** : une règle liée au bruit rédigée exclusivement dans une pièce hors de ce périmètre (par exemple un rapport de présentation qui développerait une prescription non reprise dans le règlement écrit) ne serait pas détectée. Le périmètre retenu couvre les pièces à vocation réglementaire, où une prescription ou recommandation opposable est normalement rédigée ; rien n'empêche de l'élargir si l'analyse s'avère trop restrictive à l'usage.

**Piste de correction** : élargir la liste de motifs de `resolution_pieces.py` (par exemple au rapport de présentation) si des cas réels montrent des règles liées au bruit absentes du périmètre actuel.

## `preparer_geometries.py` n'est pas sûr à relancer après le début de l'édition manuelle (Phase 2)

**Étape concernée : 4.**

**Contexte** : `preparer_geometries.py` régénère `etape4_{dept}_a_completer.gpkg` entièrement à partir de `etape3_{dept}.csv` à chaque exécution. La couche `geometries_administratives` est écrite avec `mode="w"` (remplacement propre). La couche `occurrences_a_georeferencer`, elle, est écrite avec `mode="a"` — un choix qui a du sens pour une écriture initiale dans un fichier tout juste créé, mais qui devient dangereux dès que le fichier existe déjà avec des données.

**Problème, vérifié empiriquement** : `mode="a"` sur une couche déjà existante n'écrase pas son contenu, il **empile** une nouvelle copie complète par-dessus. Concrètement, pour un opérateur qui a déjà commencé à tracer dans QGIS puis relance `preparer_geometries.py` :
- une occurrence déjà tracée se retrouve dupliquée dans la couche (une version tracée, une version vierge fraîchement régénérée, mêmes `id_gpu`/`id_occurrence`) ;
- une occurrence que l'opérateur aurait supprimée de la couche réapparaît, puisqu'elle est toujours présente dans `etape3_{dept}.csv` et que le script ne sait pas qu'elle a été délibérément retirée.

Le seul palliatif actuel est purement opérationnel : ne jamais relancer `preparer_geometries.py` une fois la Phase 2 commencée, et en cas de relancement accidentel, nettoyer la couche `occurrences_a_georeferencer` à la main.

**Pistes de correction envisageables, non retenues pour l'instant** :
- Rendre `preparer_geometries.py` idempotent vis-à-vis d'un fichier déjà existant : avant d'écrire, lire la couche `occurrences_a_georeferencer` existante (si le fichier est déjà là), ne réécrire/ajouter que les lignes dont l'`id_occurrence` n'y figure pas encore, et laisser intactes celles déjà présentes (tracées ou non). Réglerait le cas d'un relancement après ajout de nouvelles occurrences en amont (étape 3 relue), sans toucher au travail déjà fait dans QGIS.
- Refuser purement et simplement de s'exécuter si `etape4_{dept}_a_completer.gpkg` existe déjà, avec un message explicite invitant à supprimer le fichier volontairement avant de relancer — plus simple à implémenter, mais oblige à perdre tout le travail de Phase 2 en cas de besoin réel de régénération.
- Passer `mode="w"` pour les deux couches — empêcherait l'empilement, mais écraserait alors silencieusement tout travail de Phase 2 déjà fait, ce n'est pas mieux, juste un mode de défaillance différent.

**Accepté pour ce POC** : la discipline opérationnelle ("ne jamais relancer après le début de la Phase 2") suffit tant que le pipeline n'est utilisé que par un seul opérateur averti. À corriger avant tout usage à plusieurs opérateurs ou sur plusieurs départements en parallèle, où l'erreur devient plus probable et plus coûteuse à détecter.

## Pas de mécanisme de rejet pour les occurrences à géométrie manuelle

**Étape concernée : 4.**

**Contexte** : contrairement à l'étape 3 (bouton "✕ Rejeter" dans `outil_validation.html`, tracé dans `etape3_{dept}_rejetees.csv`, jamais une suppression silencieuse), l'étape 4 n'offre aucun moyen propre d'écarter une occurrence de la couche `occurrences_a_georeferencer` qu'un opérateur juge finalement hors périmètre en la traçant : la seule option disponible est de supprimer la ligne directement dans QGIS.

**Problème** : une suppression directe dans le GeoPackage ne laisse aucune trace. `etape3_{dept}.csv` continue de lister l'occurrence comme validée ; rien dans `etape4_{dept}.gpkg`, `_non_traitees.csv` ou `_erreurs.csv` ne permet de savoir plus tard qu'elle a été délibérément écartée plutôt qu'oubliée ou perdue par erreur — et aucune vérification de cohérence n'existe entre le nombre de lignes d'`etape3_{dept}.csv` et la somme des sorties de l'étape 4 pour détecter l'écart.

**Piste de correction envisageable, non retenue pour l'instant** : un champ ou statut renseigné par l'opérateur dans QGIS plutôt qu'une suppression, exploité par `synthese_geometries.py` pour écrire une ligne dans un `etape4_{dept}_rejetees.csv` dédié plutôt que de perdre la trace.

**Accepté pour ce POC**, reporté à une prochaine session de conception dédiée.

## Pas de mise en forme (gras, listes) capturée lors de la correction manuelle des messages

**Étapes concernées : 5 (capture) et 7 (conversion en aval).**

**Contexte** : le champ `content` du content-type Strapi (`cms/src/api/noisezone-alert/content-types/noisezone-alert/schema.json`) attend du HTML riche (éditeur CKEditor). Une saisie manuelle réelle montre que l'opérateur met en gras les citations réglementaires exactes dans `content`. `outil_validation.html` (étape 5, Phase 3) permet de corriger le message dans un simple `<textarea>` — texte brut, sans aucune option de mise en forme. Le message final reste donc toujours du texte brut : au mieux des retours à la ligne et des puces en tirets ("- ...") — rien qui distingue explicitement "ceci doit apparaître en gras" d'un texte normal.

**Problème** : à l'étape 7, la conversion de ce texte brut en HTML pour `content` (Strapi) ne peut se faire que par une heuristique mécanique — un unique `<p>`, chaque retour à la ligne remplacé par `<br>` (`client_strapi.convertir_content_html`) — qui ne peut pas reproduire une mise en forme que l'opérateur aurait appliquée à la main (gras, vraie liste `<ul>/<li>`). Le texte source, à l'étape 5, ne porte tout simplement pas cette information : elle ne peut pas être reconstituée automatiquement en aval, quelle que soit l'heuristique choisie à l'étape 7.

**Pistes de correction envisageables, non retenues pour l'instant** :
- Ajouter un bandeau de mise en forme minimal (gras, liste à puces) au-dessus du champ de correction dans `outil_validation.html`, Phase 3 de l'étape 5 — l'opérateur appliquerait directement la mise en forme au moment de la relecture, avec une sortie qui la porte (HTML minimal, ou une syntaxe légère type Markdown `**gras**`/`- puce` à interpréter ensuite à l'étape 7). Réglerait le problème à la source plutôt que de tenter de le deviner en aval. Implique de revoir le contrat de données de l'étape 5 (le message ne serait alors plus strictement du texte brut) et son impact sur les usages actuels en aval — l'étape 6 assemble aussi le message Strapi en texte brut.
- Alternative plus légère : n'introduire qu'une convention Markdown minimale (`**...**` pour le gras, `- ` déjà utilisé pour les puces), sans changer `outil_validation.html` lui-même, la conversion HTML de l'étape 7 sachant alors interpréter ces marqueurs. Reste à vérifier si les opérateurs l'adopteraient spontanément sans un bandeau qui la facilite — sinon la convention resterait lettre morte.

**Décision** : non mis en œuvre pour l'instant — l'étape 7 se contente dans un premier temps d'une conversion mécanique simple, sans mise en forme. À reprendre si l'écart de qualité entre la saisie manuelle et l'automatisation s'avère gênant à l'usage.

## Une mise à jour Strapi écrase le contenu sans détecter une retouche manuelle post-publication

**Étape concernée : 7.**

**Contexte** : avant toute écriture, l'étape 7 cherche une entrée Strapi existante par `alert_slug` (brouillon puis, si absent, publié) ; une ligne déjà insérée qui est relancée (ex. correction d'un message à l'étape 5, nouvel `etape6_{dept}_export.csv`) met donc à jour l'existant au lieu de dupliquer.

**Problème** : une mise à jour écrase le contenu existant sans distinguer une entrée encore en brouillon d'une entrée déjà publiée et éventuellement retouchée à la main dans Strapi (ex. `title` peaufiné après publication) — la recherche par `alert_slug` renvoie bien l'entrée, mais rien ne permet de savoir si son contenu a été modifié depuis côté Strapi.

**Piste de correction** : à définir si le besoin se confirme — par exemple comparer un horodatage de dernière modification connu côté script à celui renvoyé par Strapi avant d'écraser, ou avertir l'opérateur plutôt qu'écraser silencieusement.

**Risque accepté** pour un usage à volume limité ; à revoir si des retouches manuelles après publication deviennent fréquentes.

## Doublons Strapi résiduels d'un bug d'idempotence désormais corrigé

**Étape concernée : 7.**

**Contexte** : une première version de la recherche Strapi (voir "Idempotence" dans `etape-7-conception-technique.md`) ne passait pas le paramètre `status`. Combinée au fait que le script ne crée que des brouillons (une recherche par défaut sur l'API Strapi ne porte que sur les entrées publiées), elle a fait recréer en doublon plusieurs dizaines d'entrées déjà existantes lors d'un passage sur un département complet, avant que la recherche en deux temps (`draft` puis `published`) ne corrige le problème. Notion n'a jamais été affecté (pas de notion de statut publié/brouillon).

**Problème** : d'éventuels doublons résiduels de cet épisode restent à nettoyer manuellement dans l'admin Strapi — le jeton d'API utilisé n'a pas le droit `delete`. Le contenu des deux entrées d'une même paire de doublons est strictement identique, l'une ou l'autre peut être supprimée indifféremment.

**Piste de correction** : soit accorder ponctuellement le droit `delete` au jeton d'API pour un script de nettoyage dédié, soit traiter ce nettoyage manuellement dans l'interface Strapi une fois pour toutes sur les départements déjà traités avec l'ancienne version du script.
