# Étape 4 — Améliorations possibles (non mises en œuvre)

*Document de suivi, distinct des documents de cadrage (`etape-4-construction-geometries-diagbruit.md`, `etape-4-conception-technique.md`) : il liste des limites identifiées en utilisant réellement le pipeline, pour lesquelles une correction a été envisagée puis délibérément reportée. Chaque entrée date la décision et le contexte, pour que la même discussion n'ait pas à être refaite de zéro plus tard — dans le même esprit que `etape-2-ameliorations-possibles.md` et `etape-3-ameliorations-possibles.md`.*

## `preparer_geometries.py` n'est pas sûr à relancer après le début de l'édition manuelle (Phase 2)

**Identifié le 18/08/2026**, constaté en réel par l'utilisateur sur le département 067-plui-strasbourg : un relancement de `preparer_geometries.py` après avoir commencé le tracé manuel dans QGIS a corrompu la couche `occurrences_a_georeferencer`.

**Contexte** : `preparer_geometries.py` régénère `etape4_{dept}_a_completer.gpkg` entièrement à partir de `etape3_{dept}.csv` à chaque exécution. La couche `geometries_administratives` est écrite en premier avec `mode="w"` (remplacement propre de cette couche, vérifié sans effet de bord sur l'autre couche). La couche `occurrences_a_georeferencer`, elle, est écrite en second avec `mode="a"` — un choix qui avait du sens pour une écriture initiale dans un fichier tout juste créé par le `mode="w"` de la couche précédente, mais qui devient dangereux dès que le fichier existe déjà avec des données.

**Problème, vérifié empiriquement** (test sur un GeoPackage jetable, deux couches, une édition manuelle simulée puis un second passage avec la même séquence `mode="w"` / `mode="a"` que le vrai script) : `mode="a"` sur une couche déjà existante n'écrase pas son contenu, il **empile** une nouvelle copie complète par-dessus. Concrètement, pour un opérateur qui a déjà commencé à tracer dans QGIS puis relance `preparer_geometries.py` :
- une occurrence déjà tracée se retrouve dupliquée dans la couche (une version tracée, une version vierge fraîchement régénérée, mêmes `id_gpu`/`id_occurrence`) ;
- une occurrence que l'opérateur aurait supprimée de la couche (voir aussi le besoin de mécanisme de rejet ci-dessous, discuté mais non tracé séparément) réapparaît, puisqu'elle est toujours présente dans `etape3_{dept}.csv` et que le script ne sait pas qu'elle a été délibérément retirée.

Le seul palliatif actuel est purement opérationnel : ne jamais relancer `preparer_geometries.py` une fois la Phase 2 commencée, et en cas de relancement accidentel, nettoyer la couche `occurrences_a_georeferencer` à la main (ex. ne garder que les N premières lignes si l'ordre d'écriture est connu) — ce qui suppose de bien identifier quelles lignes sont les originales tracées et lesquelles sont les doublons fraîchement régénérés.

**Pistes de correction envisageables, non retenues pour l'instant** :
- Faire de `preparer_geometries.py` un script *idempotent* vis-à-vis d'un fichier déjà existant : avant d'écrire, lire la couche `occurrences_a_georeferencer` existante (si le fichier est déjà là), ne réécrire/ajouter que les lignes dont l'`id_occurrence` n'y figure pas encore, et laisser intactes celles déjà présentes (tracées ou non). Réglerait le cas d'un re-lancement après ajout de nouvelles occurrences en amont (étape 3 relue), sans toucher au travail déjà fait dans QGIS.
- Refuser purement et simplement de s'exécuter si `etape4_{dept}_a_completer.gpkg` existe déjà, avec un message explicite invitant à supprimer le fichier volontairement avant de relancer — plus simple à implémenter, mais oblige à perdre tout le travail de Phase 2 en cas de besoin réel de régénération (ex. correction d'une erreur de récupération de géométrie automatique après coup).
- Passer `mode="w"` pour les deux couches (empêcherait l'empilement, mais écraserait alors silencieusement tout travail de Phase 2 déjà fait — pas mieux que le problème actuel, juste un mode de défaillance différent).

**Décision** : non corrigé pour l'instant (18/08/2026) — POC, la discipline opérationnelle ("ne jamais relancer après le début de la Phase 2") suffit tant que le pipeline n'est utilisé que par un seul opérateur averti. À reprendre avant tout usage à plusieurs opérateurs ou sur plusieurs départements en parallèle, où l'erreur devient plus probable et plus coûteuse à détecter.

## Pas de mécanisme de rejet ou de fusion pour les occurrences à géométrie manuelle

**Identifié le 17/08/2026**, en anticipant deux besoins réels pendant la Phase 2 : fusionner deux occurrences qui s'avèrent, une fois localisées, décrire la même règle sur le même secteur ; et rejeter une occurrence qu'un opérateur juge finalement hors périmètre en la traçant.

**Contexte** : contrairement à l'étape 3 (bouton "✕ Rejeter" dans `outil_validation.html`, tracé dans `etape3_{dept}_rejetees.csv`, jamais une suppression silencieuse), l'étape 4 n'offre aucun moyen propre d'écarter ou de regrouper une occurrence de la couche `occurrences_a_georeferencer` : la seule option disponible à l'opérateur est de supprimer la ligne directement dans QGIS.

**Problème** : une suppression directe dans le GeoPackage ne laisse aucune trace. `etape3_{dept}.csv` continue de lister l'occurrence comme validée ; rien dans `etape4_{dept}.gpkg`, `_non_traitees.csv` ou `_erreurs.csv` ne permet de savoir plus tard qu'elle a été délibérément écartée plutôt qu'oubliée ou perdue par erreur — et aucune vérification de cohérence n'existe entre le nombre de lignes d'`etape3_{dept}.csv` et la somme des sorties de l'étape 4 pour détecter l'écart. Pour une fusion, le problème est symétrique : l'`id_occurrence` de l'occurrence absorbée disparaît des sorties sans laisser de référence vers la ligne survivante, ce qui rejoint le besoin de référence croisée déjà noté dans `etape-3-ameliorations-possibles.md` ("Détection des occurrences 'doublons'"), découvert ici plus tard dans le pipeline (à la localisation plutôt qu'à la relecture).

**Piste de correction envisageable, non retenue pour l'instant** : un champ ou statut renseigné par l'opérateur dans QGIS plutôt qu'une suppression, exploité par `synthese_geometries.py` pour écrire une ligne dans un `etape4_{dept}_rejetees.csv` dédié (rejet) ou pour reporter la référence de l'occurrence absorbée sur la ligne survivante (fusion) — plutôt que de perdre la trace dans les deux cas.

**Décision** : non mis en œuvre pour l'instant (17/08/2026) — discuté avec l'utilisateur, reporté à une prochaine session de conception dédiée.
