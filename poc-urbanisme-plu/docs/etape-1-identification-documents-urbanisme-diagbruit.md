# Étape 1 — Identifier les documents d'urbanisme en vigueur d'un département
 
*Document de cadrage détaillé de l'étape 1 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Version issue des échanges du 11/08/2026.*
 
**Entrée** : code de département (3 chiffres)
 
## Phase 1 — Référentiel des communes du département
 
Appel à l'API Découpage administratif (`geo.api.gouv.fr`) :
 
```
GET /departements/{code}/communes
```
 
Champs demandés : `nom`, `code` (INSEE), `codeDepartement`, `codeRegion`, `codeEpci` (SIREN de l'EPCI), `anciensCodes`, `deleguees`.
 
Pour chaque commune issue d'une fusion, on constitue la liste des codes INSEE à tester en phase 2 (code actuel + anciens codes), car un document peut être resté publié sous un ancien code.
 
La géométrie des communes n'est pas récupérée à ce stade — elle sera demandée plus tard, uniquement pour les communes nécessitant une délimitation manuelle de zone (cas 2 du plan global).
 
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
 
Pour chaque EPCI unique : appel à l'API Document du GPU avec `grid=<SIREN EPCI>`, `documentFamily=DU`, `status=document.production`, pagination gérée. Si un document est trouvé, on vérifie (via `document-details`) que la commune concernée est bien couverte par son périmètre — un EPCI peut avoir un PLUi qui ne couvre pas toutes ses communes membres.
 
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
| `nature_document` | PLU, PLUi, PLUm, POS, CC, RNU, PSMV |
| `id_gpu` | identifiant du document au sens du GPU |
| `date_approbation` | date d'approbation/mise à jour du document |
| `niveau_couverture` | EPCI ou commune |
| `lien_reglement` | lien direct vers le PDF du règlement écrit (pas l'archive CNIG complète — c'est ce dont l'étape 2 du plan global aura besoin) |
| `date_traitement` | date d'exécution du run |
| `statut` | document trouvé / RNU confirmé / PSMV additionnel / trou de couverture |
 
## Gestion des erreurs
 
Le traitement n'est jamais bloqué par un échec isolé (timeout, 404...). Chaque erreur est empilée dans un fichier séparé (commune, phase, type d'erreur), pendant que le reste du département continue à être traité. Quelques tentatives avec délai progressif sont prévues avant de considérer un appel comme définitivement en échec, l'API GPU n'ayant pas de garantie de disponibilité contractuelle pour les usages tiers.
 
## Prochaine étape
 
Conception technique de la mise en œuvre (choix des outils, structure du code, format exact des fichiers de sortie et d'erreurs).