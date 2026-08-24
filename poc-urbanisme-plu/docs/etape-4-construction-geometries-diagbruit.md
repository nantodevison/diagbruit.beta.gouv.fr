# Étape 4 — Construction des géométries associées aux occurrences validées

*Document de cadrage détaillé de l'étape 4 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-3-validation-manuelle.md` et `etape-3-conception-technique.md`.*

**Entrée** : le CSV `etape3_{dept}.csv` produit par l'étape 3, dans son intégralité — occurrences locales validées, documents non significatifs, communes RNU et trous de couverture. C'est la seule entrée de cette étape : contrairement à l'étape 3, l'étape 4 ne relit jamais `etape1_{dept}.csv` ni `etape2_{dept}.csv` directement — tout ce dont elle a besoin (`nature_zone`, `portee_geometrique`, `code_insee_commune`, `id_gpu`) est déjà consolidé dans `etape3_{dept}.csv`.

## Principe

Chaque ligne de `etape3_{dept}.csv` doit recevoir une géométrie avant de pouvoir entrer dans la couverture SIG départementale de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`, "Sortie visée"). Deux processus radicalement différents cohabitent, et le distinguo se joue entièrement sur le champ `portee_geometrique` (et, pour les cas qui n'ont jamais eu de règle à proprement parler, sur `nature_zone`) :

- **Géométrie automatique** — un contour administratif (commune, EPCI, ou périmètre du document lui-même) suffit. Concerne les documents non significatifs, les communes RNU, les trous de couverture, et les occurrences dont la portée a été jugée `administrative` en étape 2/3.
- **Géométrie manuelle** — la règle ne s'applique qu'à une zone réglementaire précise (ex. une zone "UA"), qui n'a pas de tracé disponible automatiquement. Un opérateur la dessine dans QGIS.

Cette distinction reprend explicitement l'Alinéa 1 / Alinéa 2 déjà posé dans le plan global — elle n'était restée, jusqu'à cette étape, qu'un principe de conception. `portee_geometrique` la rend opérationnelle.

## Chevauchement des géométries : un non-problème assumé

Le plan global pose déjà la règle : *"plusieurs surfaces peuvent se chevaucher si plusieurs règles s'appliquent à un même endroit"*. Cette étape ne cherche donc jamais à fusionner ou à dédupliquer des géométries qui se recouvrent — un PLUi qui porte trois occurrences distinctes (par exemple une portée administrative et deux zones spécifiques) produit trois géométries superposées dans le livrable final, une par occurrence. C'est voulu : la requête SIG d'intersection de l'utilisateur final retrouvera naturellement toutes les règles applicables à sa parcelle, quel que soit le nombre de surfaces qui s'y superposent.

**Cas particulier, distinct de ce non-problème** : il arrive que deux occurrences se recouvrant décrivent en réalité la *même* règle, citée deux fois dans le document source (même secteur, même objectif de lutte contre le bruit — voir `nature_sonore_zone`), plutôt que deux règles différentes. Produire deux géométries superposées dans ce cas ferait apparaître deux messages redondants à l'utilisateur final. Un mécanisme de fusion (voir `etape-4-conception-technique.md`, "Mécanisme de fusion") permet à l'opérateur de relier ces occurrences en Phase 2 sans fusionner leurs géométries — le regroupement du message revient à l'étape 5.

## Réintégration RNU et trou de couverture : pourquoi ici, et pas à part

La décision a été prise à l'étape 3 (voir `etape-3-validation-manuelle.md`) de traiter RNU et trou de couverture comme des lignes de synthèse ordinaires plutôt que comme un cas à part géré au moment de la mise en forme finale (étape 6). La raison est simple : la couverture SIG de diagBruit doit couvrir *tout* le département, y compris les communes RNU (qui portent une règle bien réelle — l'article R.111-2 du code de l'urbanisme) et les trous de couverture (qui n'en portent pas, mais dont l'absence de donnée doit rester visible plutôt que silencieuse). Différer leur géométrie à une étape ultérieure aurait revalidé une deuxième fois, pour ces deux cas particuliers, tout le travail déjà fait ici pour les documents non significatifs — sans bénéfice.

Le champ `nature_zone` existe précisément pour que cette réintégration ne brouille pas la lecture de la donnée : une fois toutes les géométries produites, un opérateur SIG (ou une symbologie QGIS) peut immédiatement distinguer une vraie règle locale (`occurrence_locale`), un régime national (`rnu`), l'absence de règle sur un document par ailleurs identifié (`document_non_significatif`), et une zone où l'on ne sait tout simplement pas encore ce qui s'applique (`trou_de_couverture`) — ce dernier cas n'étant pas destiné à figurer dans le message final de diagBruit, mais à guider la priorisation du travail de complément de données.

## Sources de géométrie : réutiliser l'existant plutôt qu'ajouter une dépendance

L'étape 1 appelle déjà l'API Carto du Géoportail de l'urbanisme (`https://apicarto.ign.fr/api/gpu`) pour déterminer si une commune est au RNU (couche `municipality`). Cette même API répond en GeoJSON, en WGS84, et expose aussi une couche `document`, qui renvoie le périmètre du document d'urbanisme lui-même — pas seulement des communes qui le composent.

Le choix a été fait de réutiliser cette source plutôt que d'intégrer un nouveau service (par exemple Admin Express de l'IGN, qui aurait aussi fonctionné) :
- la couche `municipality`, déjà appelée à l'étape 1 pour le statut RNU, donne aussi le contour de la commune — la réutiliser pour RNU et trou de couverture ne demande aucune nouvelle intégration technique, seulement un nouvel usage d'un appel déjà en place ;
- la couche `document` renvoie le périmètre réel, tel qu'approuvé, du document — pas une reconstruction par union de communes. C'est important pour un PLUi qui ne couvre pas toutes les communes de son EPCI (cas déjà rencontré à l'étape 1, voir `etape-1-identification-documents-urbanisme-diagbruit.md`) : reconstruire ce périmètre à la main aurait obligé à refaire, à l'étape 4, un travail de vérification que le GPU a déjà fait pour nous.

## Format retenu : GeoPackage plutôt que Shapefile

Le Shapefile a été écarté pour une raison concrète : le format `.dbf` sur lequel il repose limite les noms de champs à 10 caractères, ce qui aurait tronqué et fait entrer en collision des colonnes aussi explicites que `zone_reglementaire_mentionnee` ou `validation_manuelle_commentaire` — des noms volontairement longs depuis l'étape 1, pour rester lisibles par un relecteur non-développeur. Le **GeoPackage** (`.gpkg`) n'a pas cette limite, tient dans un seul fichier (pas de risque de perdre un `.shx`/`.dbf` en cours de route), et surtout permet de ranger **plusieurs couches dans un seul fichier** — ce qui sert directement l'articulation entre géométrie automatique et géométrie manuelle décrite plus bas. Le CRS retenu est le WGS84 (EPSG:4326), cohérent avec les DROM (Admin Express, à défaut d'être la source retenue ici, ne les couvre déjà pas tous de la même façon que la métropole) et avec le format renvoyé nativement par l'API Carto GPU.

## Une couche volontairement "riche", pas minimaliste

Un premier réflexe aurait été de ne stocker dans la couche SIG que les identifiants (`id_gpu`, `id_occurrence`) et la géométrie, en renvoyant tout le contenu textuel vers une jointure avec `etape3_{dept}.csv` au moment de la mise en forme finale (étape 6). Ce choix a été écarté au profit d'une couche qui **duplique** les champs nécessaires à l'opérateur pendant le travail de tracé manuel : `zone_reglementaire_mentionnee`, `portee_geometrique`, `validation_manuelle_commentaire`, `justification`, `lien_web_document`, la description de la pièce source (`type_piece_source`) et de la référence (`reference_type`/`reference_precise`).

La raison est pratique plutôt que théorique : l'opérateur qui dessine une zone spécifique dans QGIS doit pouvoir, sans quitter l'outil ni rouvrir `etape3_{dept}.csv` en parallèle, savoir *quel document ouvrir* (`lien_web_document`), *où chercher dedans* (`reference_precise` — un numéro d'article ou de page) et *ce qu'il cherche à représenter* (`zone_reglementaire_mentionnee`, `justification`). C'est la même logique que l'enrichissement déjà fait à l'étape 3 pour donner à l'opérateur le nom du document et les communes sans qu'il ait à rouvrir un autre fichier — appliquée ici au travail de digitalisation plutôt qu'à la relecture.

## Deux couches, une seule fois éditées

Le fichier produit par la phase automatique, `etape4_{dept}_a_completer.gpkg`, porte deux couches de structure identique (mêmes colonnes, pour que leur fusion finale soit triviale) :

- **`geometries_administratives`** — remplie entièrement par le code : documents non significatifs, communes RNU, trous de couverture, occurrences à portée administrative.
- **`occurrences_a_georeferencer`** — une ligne par occurrence à portée `zone_specifique`, tous les attributs déjà remplis, mais **sans géométrie**. C'est dans cette couche que l'opérateur travaille directement, en sélectionnant chaque entité dans QGIS et en lui ajoutant sa géométrie avec l'outil de digitalisation — sans avoir besoin de retaper le moindre identifiant à la main, puisque la ligne existe déjà.

Comme QGIS écrit directement dans le GeoPackage à mesure du travail, il n'y a pas ici l'équivalent du problème de sauvegarde qu'avait l'outil HTML de l'étape 3 (pas de stockage navigateur disponible) — mais la même discipline de fond reste de mise : ne jamais supposer que le travail manuel est terminé. Une occurrence encore sans géométrie au moment de la synthèse finale est traitée comme "non traitée", pas comme oubliée silencieusement — exactement le principe déjà appliqué aux occurrences non traitées de l'étape 3.

## Contrôle qualité

Avant qu'une géométrie n'entre dans le livrable final (`etape4_{dept}.gpkg`), trois vérifications systématiques : c'est bien un polygone ou un multi-polygone (pas un point, pas une ligne, jamais une géométrie vide), elle est valide au sens du standard OGC (une géométrie invalide — auto-intersection, anneau mal fermé — ferait planter ou fausserait silencieusement une requête d'intersection SIG en aval), et elle est bien exprimée dans le CRS attendu (WGS84). Le détail technique de ces vérifications est dans `etape-4-conception-technique.md`.

## Prochaine étape

Étape 5 — rédaction du ton des messages associés aux occurrences validées des documents significatifs, à partir des géométries produites ici et du contenu textuel de `etape3_{dept}.csv`. Devra regrouper en un seul message les occurrences reliées par le mécanisme de fusion (voir "Chevauchement des géométries" ci-dessus et `etape-4-conception-technique.md`, "Mécanisme de fusion").
