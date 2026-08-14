# Étape 3 — Conception technique : validation manuelle des occurrences
 
*Document de cadrage technique, faisant suite à `etape-3-validation-manuelle.md` et à `etape-2-conception-technique.md`. Révisé le 14/08/2026 après confrontation à la branche `poc-urbanisme-plu` du dépôt (la version initiale avait été écrite d'après `main`, qui ne contient pas encore ce dossier).*
 
## Posture
 
Même sous-dossier du même POC que les étapes 1 et 2 (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, preuve de concept plutôt que composant prêt à intégrer. Un point de posture supplémentaire s'applique spécifiquement à cette étape : l'outil de relecture n'a pas besoin d'être exemplaire ni de couvrir tous les cas limites, seulement de fonctionner avec des outils standards, faciles à installer, et open source (voir échanges du 14/08/2026).
 
Les scripts Python de l'étape 3 suivent aussi une convention déjà en place sur les étapes 1 et 2, repérée en relisant leur code réel : uniquement la bibliothèque standard (`csv`, `pathlib`, `argparse`), pas de dépendance comme `pandas` — une première version de ce document en proposait une, corrigée depuis (voir "Dépendances retenues").
 
## Architecture des dossiers
 
```
poc-urbanisme-plu/
├── docs/                                # cadrage — un doc par étape, miroir de ce qui est écrit ici
├── etape1_identification/               # existant
├── etape2_analyse_reglements/           # existant
├── etape3_validation_manuelle/
│   ├── __init__.py                      # vide, comme etape1_identification/ et etape2_analyse_reglements/
│   ├── contexte_documents.py            # aide partagée : jointure etape1 (nom, communes) par id_gpu
│   ├── preparer_revue.py                # Phase 1 — filtre + enrichit + priorise → etape3_{dept}_a_valider.csv
│   ├── outil_validation.html            # Phase 2 — outil de relecture (manuel, hors ligne de commande)
│   └── synthese_finale.py               # Phase 3 — consolide l'export de l'outil → etape3_{dept}.csv
└── output/                              # non versionné (sauf exceptions déjà présentes sur la branche)
    ├── etape1_{dept}.csv
    ├── etape2_{dept}.csv
    ├── etape3_{dept}_a_valider.csv          # sortie de preparer_revue.py
    ├── etape3_export_outil_{horodatage}.csv # export(s) de l'outil (voir Phase 2) ; synthese_finale.py prend le plus récent
    ├── etape3_{dept}.csv                    # sortie de synthese_finale.py — contrat pour l'étape 4
    ├── etape3_{dept}_rejetees.csv           # audit, si non vide
    └── etape3_{dept}_non_traitees.csv       # occurrences oubliées, si non vide
```
 
Contrairement aux étapes 1 et 2, l'étape 3 n'a pas de `main.py` unique : une relecture humaine s'intercale entre ses deux phases automatisées (`preparer_revue.py` puis `synthese_finale.py`), chacune relançable indépendamment à partir de son fichier d'entrée, dans le même esprit que le reste du POC. Comme `etape1_identification/main.py` et `etape2_analyse_reglements/main.py`, les deux scripts acceptent un `--output-dir` (défaut : `output`, résolu par rapport au dossier courant, pas au fichier du script) — l'usage réel suppose donc de lancer les commandes depuis `poc-urbanisme-plu/` (voir `README.md` du POC).
 
Usage, depuis `poc-urbanisme-plu/` :
```
python -m etape3_validation_manuelle.preparer_revue --dept 033
# ouvrir outil_validation.html dans un navigateur, charger etape3_033_a_valider.csv, relire
python -m etape3_validation_manuelle.synthese_finale --dept 033
```
 
## Phase 1 — Préparation (`preparer_revue.py`)
 
Lit `etape1_{dept}.csv` et `etape2_{dept}.csv` (module `csv` de la bibliothèque standard, encodage `utf-8-sig` — les deux fichiers sont écrits avec un BOM par `etape1_identification/synthese.py` et `etape2_analyse_reglements/synthese.py`). Filtre les occurrences dont `statut_verification` vaut `validé` ou `à vérifier (renvoi CSV-PEB potentiel)`. Enrichit chaque occurrence retenue du nom du document et des communes couvertes (jointure sur `id_gpu`, via `contexte_documents.py`, qui agrège `etape1_{dept}.csv` par `id_gpu`). Calcule une `priorite` numérique (rang de `confiance_extrait` puis rang de `ocr_confiance`, les valeurs faibles en tête) utilisée comme tri par défaut. Écrit `etape3_{dept}_a_valider.csv` (même encodage `utf-8-sig`), trié par document puis par priorité.
 
Un fichier d'entrée manquant lève `FichiersEntreeIntrouvables`, interceptée dans `main()` qui l'affiche sur `stderr` et retourne `1` — même schéma que `Etape1CsvIntrouvable` dans `etape2_analyse_reglements/main.py`.
 
## Phase 2 — Relecture (`outil_validation.html`)
 
Page HTML/CSS/JS autonome, sans dépendance externe (aucun appel réseau, aucune bibliothèque à installer) — elle s'ouvre directement dans un navigateur, aucun serveur requis.
 
**Chargement** : un champ de fichier (ou glisser-déposer) charge `etape3_{dept}_a_valider.csv`, ou un export précédent de l'outil pour reprendre une session interrompue — les deux formats sont compatibles, les colonnes `validation_manuelle_statut`/`validation_manuelle_commentaire` sont ajoutées vides si absentes.
 
**Analyse CSV** : parseur RFC 4180 minimal écrit à la main (champs entre guillemets, guillemets échappés en `""`, champs multi-lignes, BOM UTF-8 toléré en tête de fichier — cohérent avec l'encodage `utf-8-sig` utilisé côté Python) plutôt qu'une bibliothèque tierce — pas de dépendance à installer, pas d'accès CDN nécessaire pour que l'outil fonctionne hors ligne.
 
**Affichage** : occurrences groupées par document (élément `<details>` repliable, avec nom du document et communes en en-tête), triées par priorité par défaut — l'opérateur peut retrier (nom du document, nombre d'occurrences) ou filtrer (par statut de validation, par recherche textuelle libre sur le document/la citation/la zone) depuis la barre d'outils.
 
**Édition** : tous les champs sauf `id_gpu`/`id_occurrence` sont des champs de formulaire éditables (texte, zone de texte, ou liste déroulante pour les champs à valeurs contrôlées comme `nature_occurrence` ou `nature_juridique_piece`). Toute valeur affichée est passée par une fonction d'échappement HTML (`echapperHTML`) avant insertion dans la page — nécessaire car les citations extraites de PDF peuvent contenir des caractères comme `<`, `>` ou `&`, qui casseraient sinon le rendu (bug identifié et corrigé en test, voir "Validation du fonctionnement").
 
**Validation** : deux boutons par occurrence.
- *✓ Valider* — compare les valeurs courantes aux valeurs chargées initialement ; si au moins un champ modifiable diffère, le statut devient `corrigé`, sinon `validé`.
- *✕ Rejeter* — statut `rejeté`, quel que soit l'état des champs.
Un commentaire libre (`validation_manuelle_commentaire`) est possible dans tous les cas, indépendamment du statut.
 
**Sauvegarde** : ni `localStorage` ni `sessionStorage` (non disponibles dans ce type d'outil) — la progression n'existe qu'en mémoire tant qu'elle n'est pas exportée. Un bouton "Exporter" est toujours disponible, et un export automatique se déclenche tous les 10 traitements (constante `SEUIL_EXPORT_AUTO`) pour limiter la perte de progression en cas d'oubli. Chaque export télécharge un CSV horodaté (`etape3_export_outil_{horodatage}.csv`) avec les mêmes colonnes que le fichier chargé, plus les deux colonnes de validation. Une confirmation du navigateur se déclenche si l'onglet se ferme alors que des traitements n'ont pas encore été exportés.
 
## Phase 3 — Synthèse finale (`synthese_finale.py`)
 
Lit `etape1_{dept}.csv` (contexte), `etape2_{dept}.csv` (référence complète de tous les `id_gpu` traités à l'étape 2) et le dernier export de l'outil — les trois avec `encoding="utf-8-sig"`, qui tolère aussi bien un BOM (fichiers Python) qu'un fichier téléchargé par le navigateur.
 
Le nom réel produit par l'outil (`etape3_export_outil_{horodatage}.csv`, voir Phase 2) ne porte pas le code département — l'outil est générique, réutilisable pour n'importe quel département — et chaque export (manuel ou automatique) crée un nouveau fichier plutôt que d'écraser le précédent. `synthese_finale.py` ne demande donc pas ce nom en entrée : il liste `output/etape3_export_outil_*.csv` et retient celui dont l'horodatage encodé dans le nom (`AAAAMMJJ_HHMMSS`) est le plus grand. Une première version de ce document (et du code) attendait un nom fixe `etape3_{dept}_export_outil.csv`, jamais produit en pratique — corrigé après un premier usage réel de l'outil, où `synthese_finale.py` échouait avec `fichier(s) d'entrée introuvable(s)`.
 
Sépare les occurrences exportées en trois lots : non traitées (`validation_manuelle_statut` vide — écrites à part dans `etape3_{dept}_non_traitees.csv`, exclues de la suite), retenues (`validé` ou `corrigé`) et rejetées (écrites à part dans `etape3_{dept}_rejetees.csv`, pour traçabilité, jamais supprimées).
 
Calcule ensuite, pour chaque `id_gpu` connu d'`etape2_{dept}.csv`, s'il est significatif (au moins une occurrence retenue) ou non. Les documents non significatifs — qu'ils n'aient jamais eu d'occurrence, ou que toutes leurs occurrences aient été rejetées ou non traitées — reçoivent une seule ligne de synthèse (`statut_verification_finale = "aucune occurrence trouvée"`), enrichie via `contexte_documents.py` à partir d'`etape1_{dept}.csv` directement (et non de l'export, car ces documents peuvent n'y jamais apparaître).
 
Concatène les deux ensembles (occurrences retenues + synthèses de documents non significatifs) et écrit `etape3_{dept}.csv`. Un export d'outil sans la colonne `validation_manuelle_statut` lève `ExportOutilInvalide` (fichier chargé par erreur), tout fichier d'entrée manquant lève `FichiersEntreeIntrouvables` — les deux interceptées dans `main()`, qui affiche le message sur `stderr` et retourne `1`.
 
## Contrat de données
 
Pas d'obligation d'isomorphisme avec `etape2_{dept}.csv` (voir échanges du 14/08/2026) : seules `id_gpu` et `id_occurrence` doivent rester stables, pour permettre à un traitement automatisé ultérieur de rejoindre `etape3_{dept}.csv` avec `etape1_{dept}.csv`/`etape2_{dept}.csv` si une colonne non reprise ici s'avérait nécessaire. Toute colonne modifiable par l'opérateur (voir "Édition en une seule passe" dans `etape-3-validation-manuelle.md`) doit en revanche être présente avec sa valeur finale dans `etape3_{dept}.csv` — une jointure vers `etape2_{dept}.csv` récupérerait sinon la valeur d'origine, potentiellement corrigée depuis en étape 3.
 
Colonnes de `etape3_{dept}.csv` :
 
| Colonne | Détail |
|---|---|
| `id_gpu` | clé de jointure |
| `id_occurrence` | vide sur une ligne de synthèse "document non significatif" |
| `statut_verification_finale` | `validé` / `corrigé` / `aucune occurrence trouvée` |
| `nom_document`, `communes` | contexte documentaire, récupéré d'`etape1_{dept}.csv` |
| `type_piece_source`, `lien_web_document`, `reference_type`, `reference_precise`, `zone_reglementaire_mentionnee`, `extrait_significatif`, `contexte_documentaire`, `confiance_extrait`, `justification`, `nature_occurrence`, `nature_juridique_piece`, `nature_sonore_zone`, `ocr_utilise`, `ocr_confiance` | valeur finale (potentiellement corrigée en étape 3), vide sur une ligne de synthèse |
| `validation_manuelle_statut`, `validation_manuelle_commentaire` | décision de l'opérateur |
 
`nature_juridique_piece` (déduite mécaniquement à l'étape 2 à partir de `type_piece_source`) est reprise ici comme les autres colonnes de contenu — modifiable dans l'outil au même titre que le reste, par souci de simplicité d'implémentation (un seul type de champ de formulaire pour toutes les colonnes non identifiantes) plutôt que par nécessité métier.
 
## Gestion des erreurs et cas particuliers
 
Dans le même esprit que les étapes 1 et 2 (aucun échec isolé ne bloque tout le traitement), `synthese_finale.py` ne fait jamais l'hypothèse que la relecture est complète : les occurrences non traitées sont explicitement séparées et documentées (`etape3_{dept}_non_traitees.csv`) plutôt que silencieusement comptées comme validées ou perdues. `preparer_revue.py` et `synthese_finale.py` s'arrêtent avec un message explicite si un fichier d'entrée attendu est introuvable — contrairement à un échec isolé sur une ligne, l'absence d'un fichier d'entrée entier ne laisse rien d'exploitable en aval.
 
## Validation du fonctionnement
 
L'ensemble du pipeline (`preparer_revue.py` → `outil_validation.html` → `synthese_finale.py`) a été testé de bout en bout à deux reprises :
 
1. **Données factices** : un département fictif à quatre documents couvrant les cas limites (occurrences à valider avec caractères piégeux pour le rendu HTML, document jamais soumis à relecture, document dont l'unique occurrence reste rejetée, occurrence laissée non traitée). Le test automatisé (Playwright, simulant le chargement du CSV, l'édition de champs et les clics de validation/rejet dans un vrai navigateur) a permis de détecter et corriger un bug réel : le tri des documents par priorité traitait `priorite = 0` (le cas le plus prioritaire) comme une valeur absente, à cause d'un test de vérité JavaScript (`0 || 99` vaut `99`) plutôt que d'un test de présence (`Number.isFinite`).
2. **Données réelles** : `etape1_067.csv` et `etape2_067.csv`, tels que présents sur la branche `poc-urbanisme-plu` (17 occurrences, un seul document intercommunal couvrant 33 communes). A confirmé la jointure des communes, l'encodage `utf-8-sig` (BOM en entrée et en sortie), le nouveau champ `nature_juridique_piece`, ainsi que le déclenchement de l'export automatique après 10 traitements.
## Dépendances retenues
 
- Bibliothèque standard uniquement (`csv`, `pathlib`, `argparse`) pour `contexte_documents.py`, `preparer_revue.py` et `synthese_finale.py` — aucune dépendance supplémentaire par rapport à `requirements.txt` existant, cohérent avec le choix déjà fait aux étapes 1 et 2 d'éviter `pandas` pour un export ligne à ligne simple (voir `etape-1-conception-technique.md`, "Dépendances retenues").
- Aucune dépendance pour `outil_validation.html` : HTML/CSS/JavaScript natif, aucune installation, aucun accès réseau requis pour l'utiliser.
## Prochaine étape
 
Conception détaillée de l'étape 4 (assignation de géométrie), en particulier son alinéa 2 encore ouvert (occurrences à portée sur une zone réglementaire spécifique).