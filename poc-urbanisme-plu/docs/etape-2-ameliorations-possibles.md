# Étape 2 — Améliorations possibles (non mises en œuvre)

*Document de suivi, distinct des documents de cadrage (`etape-2-analyse-documents-urbanisme-diagbruit.md`, `etape-2-conception-technique.md`) : il liste des limites identifiées en relisant des résultats réels, pour lesquelles une correction a été envisagée puis délibérément reportée. Chaque entrée date la décision et le contexte, pour que la même discussion n'ait pas à être refaite de zéro plus tard.*

## Répétition dans `contexte_documentaire` quand la citation déborde sur le contexte

**Identifié le 13/08/2026**, en relisant les résultats du département 067 après la mise en œuvre de l'"option 4" (citation verbatim choisie par le modèle — voir `etape-2-conception-technique.md`, section "Appel de classification (Phase 4)").

**Contexte** : la colonne `contexte_documentaire` du CSV de synthèse concatène, dans l'ordre de lecture du document, `contexte_avant` + `extrait_significatif` (la citation choisie par le modèle) + `contexte_apres`. C'est une concaténation volontairement simple, sans logique de déduplication (choix explicite de l'utilisateur lors de la définition de l'"option 4").

**Problème observé** : le modèle est invité à puiser sa citation dans le passage *et* dans son contexte immédiat quand la règle y déborde (c'est précisément ce qui corrige les citations tronquées, voir plus bas). Quand `extrait_significatif` recouvre effectivement une partie de `contexte_avant` ou `contexte_apres`, cette portion se retrouve donc affichée deux fois dans `contexte_documentaire`. Exemple réel (département 067, pièce `246700488_orientations_amenagement_1_20260206.pdf`, ligne `6_...`) :

> "...les constructions situées dans les zones de bruit liées aux infrastructures de transport **les constructions situées dans les zones de bruit liées aux infrastructures de transport** terrestre feront l'objet de dispositifs d'isolation acoustique."

**Impact** : cosmétique, pas fonctionnel. La répétition reste immédiatement reconnaissable par un relecteur humain et ne change ni la classification ni les autres colonnes. N'affecte pas la fiabilité de la vérification humaine, seulement son confort de lecture sur certaines lignes.

**Piste de correction envisageable, non retenue pour l'instant** : avant concaténation, détecter le chevauchement entre le début/la fin d'`extrait_significatif` et la fin de `contexte_avant` / le début de `contexte_apres` (recherche de la plus longue sous-chaîne commune aux deux bornes), et tronquer le contexte de la portion déjà couverte par la citation.

**Décision** : laissé tel quel pour l'instant (13/08/2026) — priorité donnée à la suite de la relecture des résultats plutôt qu'à ce raffinement cosmétique. À reprendre si la gêne s'avère plus importante à l'usage, ou lors d'un futur passage de polish du POC.

## `confiance_extrait` mélange deux raisons différentes de valoir "faible"

**Identifié le 13/08/2026**, en précisant la notion de "règle autonome" dans le prompt de la phase 4 (voir `etape-2-conception-technique.md`, section "Appel de classification (Phase 4)").

**Contexte** : `confiance_extrait` mesurait jusqu'ici uniquement la clarté/l'autonomie de la citation choisie par le modèle (`extrait_significatif`) — un fragment coupé, ou mélangeant deux sujets, valait "faible". Le prompt demande désormais aussi de taguer "faible" une règle par ailleurs parfaitement claire mais qui ne concerne qu'un projet d'infrastructure de transport (hors périmètre habituel de diagBruit : construction de bâtiments, aménagement urbain).

**Problème** : ces deux situations n'ont rien à voir (l'une est un défaut d'extraction, l'autre une question de pertinence du sujet) mais partagent la même valeur de colonne. Un relecteur qui filtre sur `confiance_extrait = "faible"` pour prioriser sa vérification ne peut pas distinguer les deux cas sans ouvrir `justification` et la lire.

**Palliatif retenu pour l'instant** : le prompt exige explicitement que `justification` précise laquelle des deux raisons s'applique quand `confiance_extrait = "faible"` — l'information reste donc disponible, seulement pas dans une colonne filtrable dédiée.

**Piste de correction envisageable, non retenue pour l'instant** : séparer les deux notions dans deux colonnes distinctes, par exemple garder `confiance_extrait` pour la seule clarté de la citation, et ajouter un champ dédié (booléen ou enum, ex. `hors_perimetre_batiment`) pour le critère de périmètre diagBruit. Plus facilement filtrable/triable dans le CSV, au prix d'une colonne supplémentaire et d'un ajustement du schéma de structured output.

**Décision** : choix assumé du champ unique (13/08/2026, décidé avec l'utilisateur avant mise en œuvre) — cohérent avec la posture POC (ajouter une colonne seulement quand l'usage réel le justifie). À reprendre si la relecture humaine montre que le mélange gêne effectivement le tri des résultats.
