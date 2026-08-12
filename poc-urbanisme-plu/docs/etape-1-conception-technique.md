# Conception technique — POC automatisation des règles PLU (diagBruit)
 
*Document de cadrage technique — décisions issues des échanges du 11/08/2026, faisant suite à `plan-automatisation-regles-plu-diagbruit.md` et `etape-1-identification-documents-urbanisme-diagbruit.md`.*
 
## Contexte et posture du projet
 
Ce code est écrit par un spécialiste acoustique, pas par un développeur de l'équipe diagBruit (actuellement en congés). L'objectif n'est **pas** de produire un composant prêt à intégrer au produit, mais une **preuve de concept solide et robuste**, qui démontre que le pipeline d'identification/analyse fonctionne et produit une donnée exploitable. L'intégration propre au produit (structure de code définitive, stockage en base, tests automatisés, CI...) relève du métier de l'équipe technique et sera traitée par elle à la reprise du projet.
 
Cette posture guide toutes les décisions ci-dessous : on préfère la simplicité et l'absence de risque pour l'existant à l'optimisation ou à l'alignement complet sur les standards du produit.
 
## Décision 1 — Le POC vit hors des dossiers du produit
 
Le code est placé dans un dossier autonome à la racine du dépôt, **`poc-urbanisme-plu/`**, en dehors de `fastapi/` et `dagster/`.
 
**Pourquoi :** `dagster/` a son propre gestionnaire de dépendances (`uv`), sa propre structure d'assets et son propre environnement virtuel. Un non-développeur qui y touche risque de casser l'environnement de travail de l'équipe pendant son absence. Un dossier autonome, avec son propre environnement Python simple, est complètement isolé : impossible de casser l'existant, facile à déplacer ou supprimer le jour où les développeurs choisissent leur propre découpage d'intégration.
 
## Décision 2 — Un sous-dossier par étape du plan global
 
Chaque étape du plan global (`plan-automatisation-regles-plu-diagbruit.md`) devient un sous-dossier autonome, qui :
- prend en entrée le(s) fichier(s) produit(s) par l'étape précédente (jamais un état en mémoire d'un programme qui enchaînerait tout) ;
- produit son propre fichier de sortie, stocké dans un dossier `output/` commun.
```
poc-urbanisme-plu/
├── README.md
├── requirements.txt
│
├── etape1_identification/
│   ├── main.py                    # point d'entrée : python -m etape1_identification.main --dept 033
│   ├── communes.py                # Phase 1 — API Géo (référentiel communes)
│   ├── documents_urbanisme.py     # Phase 2 — API GPU + API Carto (RNU, DU, PSMV)
│   └── synthese.py                # Phase 3 — écriture CSV + fichier d'erreurs
│
├── etape2_analyse_reglements/     # à concevoir plus tard
│   └── ...
│
├── etape3_delimitation_zones/     # à concevoir plus tard
│   └── ...
│
└── output/
    ├── etape1_{dept}.csv
    ├── etape1_{dept}_erreurs.csv
    └── ...                        # fichiers des étapes suivantes, à venir
```
 
**Pourquoi ce découpage plutôt qu'un programme unique qui enchaîne tout :**
- Il reflète la façon dont le plan global a été conçu (chaque étape fait l'objet d'un échange dédié) — le code suit la même logique, sans jamais retoucher une étape déjà validée pour concevoir la suivante.
- Chaque étape reste relançable seule à partir de son fichier d'entrée.
- Le point de contact entre deux étapes est un fichier CSV lisible et vérifiable manuellement (tableur), ce qui matérialise l'étape de vérification humaine prévue au plan global avant intégration.
- Une erreur dans une étape n'affecte jamais le code des étapes précédentes : aucune dépendance de code entre les dossiers, seulement une dépendance de données.
**Conséquence pour la conception des CSV** : chaque fichier de sortie doit être pensé comme un **contrat de données stable** pour l'étape suivante, pas seulement comme un rapport de contrôle.
 
*Précision (issue des échanges du 12/08/2026) : le point d'entrée réel de l'étape 2 est la colonne `id_gpu` de l'étape 1, pas un lien direct vers un fichier. L'étape 2 doit donc démarrer par un appel à `document-details` de l'API du GPU pour résoudre cet `id_gpu` en une liste de pièces (règlement écrit, OAP, PADD, PSMV le cas échéant) et leurs URLs — cette résolution est une sous-étape à part entière de l'étape 2, pas un acquis de l'étape 1.*
 
## Décision 3 — Sortie fichiers (CSV), pas base de données
 
Contrairement au reste du produit (qui stocke tout en PostGIS via Dagster/dbt), le POC écrit ses résultats en fichiers CSV dans `output/`, non versionnés (`.gitignore`).
 
**Pourquoi :** aligner le POC sur le pattern PostGIS du produit demanderait de comprendre et manipuler l'infrastructure Dagster/dbt existante — hors de portée pour une preuve de concept menée par un non-développeur, et risqué pour l'environnement de travail de l'équipe absente. Le chargement éventuel en base, une fois le POC validé, relève de l'intégration produit et sera traité par l'équipe technique selon ses propres standards (probablement sous forme d'un nouveau domaine d'assets Dagster, au même niveau que `bdnb`, `noisemap`, `osm`, `peb`, `soundclassification`).
 
## Décision 4 — Gestion des erreurs : jamais bloquante
 
Aucune fonction d'appel API ne doit lever d'exception qui interrompt tout le traitement. En cas d'échec (après quelques tentatives avec délai progressif), la fonction retourne un résultat "erreur" structuré. `main.py` empile ces erreurs et poursuit le traitement du reste du département, plutôt que de s'arrêter. Les erreurs accumulées sont écrites dans un fichier séparé (`etape1_{dept}_erreurs.csv`), consultable indépendamment.
 
## Dépendances retenues
 
- `requests` — appels HTTP, suffisant pour ce POC (pas besoin d'un client plus élaboré).
- `csv` (bibliothèque standard) — écriture des fichiers de sortie, pas besoin de `pandas` pour un export ligne à ligne simple.
- `tenacity` (à confirmer) — gestion des tentatives avec délai progressif, plutôt que de réimplémenter cette logique à la main.
## Ce que ça donnera à l'équipe technique, plus tard
 
Le découpage en dossiers par étape se transpose naturellement en assets Dagster chaînés (un asset par étape, avec dépendances explicites) le jour où l'équipe reprend le sujet — sans que cette anticipation nous impose quoi que ce soit maintenant. Le POC fournit une donnée propre et un contrat clair à chaque étape ; le choix de l'orchestration finale appartient aux développeurs.