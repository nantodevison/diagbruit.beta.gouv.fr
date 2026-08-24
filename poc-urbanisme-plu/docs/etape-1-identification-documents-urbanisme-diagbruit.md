# Étape 1 — Identifier les documents d'urbanisme en vigueur d'un département
 
*Document de cadrage détaillé de l'étape 1 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`).*
 
**Entrée** : code de département (3 chiffres)
 
## Phase 1 — Référentiel des communes du département
 
Appel à l'API Découpage administratif (`geo.api.gouv.fr`) :
 
```
GET /departements/{code}/communes
```
 
Champs demandés : `nom`, `code` (INSEE), `codeDepartement`, `codeRegion`, `codeEpci` (SIREN de l'EPCI), `anciensCodes`, `deleguees`.
 
Pour chaque commune issue d'une fusion, on constitue la liste des codes INSEE à tester en phase 2 (code actuel + anciens codes), car un document peut être resté publié sous un ancien code.
 
La géométrie des communes n'est pas récupérée à ce stade. Elle est obtenue en phase 2, comme sous-produit de la vérification RNU (voir 2.2), pour vérifier qu'un document intercommunal couvre bien la commune. Une délimitation manuelle de zone, plus poussée, n'intervient que plus tard, pour les communes qui le nécessitent (cas 2 du plan global).
 
En cas d'erreur sur cet appel : message explicite, arrêt du traitement pour le département (pas de référentiel commune = rien d'exploitable en aval).
 
## Phase 2 — Recherche des documents en vigueur
 
### 2.1 — Dédoublonnage des EPCI
 
On regroupe les communes par `codeEpci` unique, pour n'interroger chaque EPCI qu'une seule fois.
 
### 2.2 — Statut RNU / commune fusionnée
 
Pour chaque commune, appel à l'API Carto, module Urbanisme, couche `municipality` :
 
```
GET https://apicarto.ign.fr/api/gpu/municipality?insee={code}
```
 
Cette couche renvoie de façon fiable si la commune est au RNU. Si oui : commune classée **RNU confirmé**, message standard, pas de recherche de document nécessaire.
 
### 2.3 — Recherche du document, EPCI puis commune
 
Pour chaque EPCI unique : appel à l'API Document du GPU avec `grid=<SIREN EPCI>`, `documentFamily=DU`, `status=document.production`. Si un document est trouvé, on vérifie qu'il couvre bien la commune par intersection géométrique (couche `document` de l'API Carto du GPU, avec la géométrie de la commune obtenue en 2.2) — un EPCI peut avoir un PLUi qui ne couvre pas toutes ses communes membres.
 
Pour les communes non couvertes à ce niveau (EPCI sans document, PLUi partiel, ou commune hors EPCI) : même recherche avec `grid=<code INSEE>` (code actuel puis anciens codes le cas échéant).
 
### 2.4 — PSMV en complément
 
Recherche systématique, sur le même maillage, avec `documentFamily=PSMV`. Si un PSMV est trouvé, il s'ajoute au document DU (chevauchement possible), il ne le remplace jamais.
 
### 2.5 — Cas résiduel
 
Si aucun document n'est trouvé et que la commune n'est pas RNU confirmé : on lève une alerte **« trou de couverture GPU »**, distincte de l'alerte RNU, pour investigation manuelle — plutôt que de conclure au RNU par défaut.
 
## Phase 3 — Synthèse CSV
 
| Colonne | Détail |
|---|---|
| `nom_commune` | |
| `code_insee_commune` | code actuel (ancien code utilisé précisé si pertinent) |
| `code_siren_epci` | |
| `nom_document` | |
| `nature_document` | PLU, PLUi, PLUm, POS, CC, PSMV ; vide si RNU confirmé ou trou de couverture |
| `id_gpu` | identifiant du document au sens du GPU — c'est ce qui permet à l'étape 2 de récupérer, via `document-details`, l'ensemble des pièces écrites (règlement, OAP, PADD, annexes...), pas seulement le règlement ; vide si RNU confirmé ou trou de couverture |
| `date_approbation` | date d'approbation/mise à jour du document ; vide si RNU confirmé ou trou de couverture |
| `niveau_couverture` | EPCI ou commune ; vide si RNU confirmé ou trou de couverture |
| `date_traitement` | date d'exécution du run |
| `statut` | document trouvé / RNU confirmé / PSMV additionnel / trou de couverture |

Une commune donne une ligne par document trouvé (un DU et un PSMV se cumulent sans jamais se remplacer, une commune peut donc apparaître sur deux lignes) ; une commune RNU confirmé ou en trou de couverture donne une seule ligne, sans document, pour que chaque commune du département reste traçable dans le CSV.

En complément, un fichier `etape1_{dept}_erreurs.csv` liste les échecs isolés survenus pendant le traitement (voir "Gestion des erreurs" ci-dessous) : commune ou EPCI concerné, phase où l'échec est survenu, type d'erreur et message.
 
## Gestion des erreurs
 
Le traitement n'est jamais bloqué par un échec isolé (timeout, 404...). Chaque erreur est empilée dans un fichier séparé (commune, phase, type d'erreur), pendant que le reste du département continue à être traité. Quelques tentatives avec délai progressif sont prévues avant de considérer un appel comme définitivement en échec, l'API GPU n'ayant pas de garantie de disponibilité contractuelle pour les usages tiers.
 
## Prochaine étape
 
Conception technique de la mise en œuvre (choix des outils, structure du code, format exact des fichiers de sortie et d'erreurs).
 