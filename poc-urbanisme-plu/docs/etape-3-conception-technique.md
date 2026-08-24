# Étape 3 — Conception technique : validation manuelle des occurrences

*Document de cadrage technique, faisant suite à `etape-3-validation-manuelle.md` et à `etape-2-conception-technique.md`. Décrit le code réel du dossier `etape3_validation_manuelle/` de la branche `poc-urbanisme-plu`. `synthese_finale.py` réintègre les communes RNU et les trous de couverture (lus directement depuis `etape1_{dept}.csv`) en plus des occurrences validées ; le contrat de données de `etape3_{dept}.csv` porte en conséquence les colonnes `nature_zone`, `code_insee_commune`, `portee_geometrique` et `partition_gpu` — cette dernière, une valeur précalculée nécessaire à la récupération de géométrie de document, voir "Calcul de `partition_gpu`" plus bas et `etape-4-conception-technique.md`.*

## Posture

Même sous-dossier du même POC que les étapes 1 et 2 (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, preuve de concept plutôt que composant prêt à intégrer. Un point de posture supplémentaire s'applique spécifiquement à cette étape : l'outil de relecture n'a pas besoin d'être exemplaire ni de couvrir tous les cas limites, seulement de fonctionner avec des outils standards, faciles à installer, et open source.

Les scripts Python de l'étape 3 suivent aussi une convention déjà en place sur les étapes 1 et 2 : uniquement la bibliothèque standard (`csv`, `pathlib`, `argparse`), pas de dépendance comme `pandas` (voir "Dépendances retenues").

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
│   └── synthese_finale.py               # Phase 3 — consolide l'export de l'outil + RNU/trou de couverture → etape3_{dept}.csv
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

Les communes RNU et les trous de couverture ne sont jamais soumis à l'opérateur, donc jamais présents dans `etape3_{dept}_a_valider.csv`. Leur réintégration se fait entièrement en phase 3, ci-dessous.

## Phase 2 — Relecture (`outil_validation.html`)

Page HTML/CSS/JS autonome, sans dépendance externe (aucun appel réseau, aucune bibliothèque à installer) — elle s'ouvre directement dans un navigateur, aucun serveur requis.

**Chargement** : un champ de fichier (ou glisser-déposer) charge `etape3_{dept}_a_valider.csv`, ou un export précédent de l'outil pour reprendre une session interrompue — les deux formats sont compatibles, les colonnes `validation_manuelle_statut`/`validation_manuelle_commentaire` sont ajoutées vides si absentes.

**Analyse CSV** : parseur RFC 4180 minimal écrit à la main (champs entre guillemets, guillemets échappés en `""`, champs multi-lignes, BOM UTF-8 toléré en tête de fichier — cohérent avec l'encodage `utf-8-sig` utilisé côté Python) plutôt qu'une bibliothèque tierce — pas de dépendance à installer, pas d'accès CDN nécessaire pour que l'outil fonctionne hors ligne.

**Affichage** : occurrences groupées par document (élément `<details>` repliable, avec nom du document et communes en en-tête), triées par priorité par défaut — l'opérateur peut retrier (nom du document, nombre d'occurrences) ou filtrer (par statut de validation, par recherche textuelle libre sur le document/la citation/la zone) depuis la barre d'outils.

**Édition** : huit champs sont de véritables champs de formulaire éditables (fonction `rendreOccurrence`) — `zone_reglementaire_mentionnee` (texte), `justification` (zone de texte), cinq listes déroulantes pour les champs à valeurs contrôlées (`nature_occurrence`, `nature_juridique_piece`, `nature_sonore_zone`, `statut_verification`, `portee_geometrique`), et `validation_manuelle_commentaire` (texte, dans la zone de validation). Les autres colonnes du CSV chargé (`type_piece_source`, `lien_web_document`, `reference_type`, `reference_precise`, `confiance_extrait`, `ocr_utilise`, `ocr_confiance`, `priorite`, `communes`, `nom_document`) n'ont pas de champ de saisie : elles sont affichées en lecture seule (badges, lien) ou simplement conservées telles quelles pour l'export. `extrait_significatif` et `contexte_documentaire` sont affichés en lecture seule dans le bloc "Citation significative et contexte" (voir plus bas). `id_gpu`/`id_occurrence` ne sont affichés nulle part dans le formulaire.

`CHAMPS_MODIFIABLES`, la constante JS qui sert à détecter un statut `corrigé` (voir "Validation" plus bas), liste aussi `type_piece_source`, `reference_type`, `reference_precise`, `ocr_utilise`, `ocr_confiance` et `confiance_extrait` : en pratique ces six colonnes ne peuvent jamais différer de leur valeur d'origine puisqu'aucun champ de formulaire ne permet de les modifier — seuls les huit champs listés ci-dessus peuvent réellement déclencher un passage à `corrigé`.

Toute valeur affichée est passée par une fonction d'échappement HTML (`echapperHTML`) avant insertion dans la page — nécessaire car les citations extraites de PDF peuvent contenir des caractères comme `<`, `>` ou `&`, qui casseraient sinon le rendu (voir "Validation du fonctionnement").

**Validation** : deux boutons par occurrence.
- *✓ Valider* — compare les valeurs courantes aux valeurs chargées initialement ; si au moins un champ modifiable diffère, le statut devient `corrigé`, sinon `validé`.
- *✕ Rejeter* — statut `rejeté`, quel que soit l'état des champs.
Un commentaire libre (`validation_manuelle_commentaire`) est possible dans tous les cas, indépendamment du statut.

**Sauvegarde** : ni `localStorage` ni `sessionStorage` (non disponibles dans ce type d'outil) — la progression n'existe qu'en mémoire tant qu'elle n'est pas exportée. Un bouton "Exporter" est toujours disponible, et un export automatique se déclenche tous les 10 traitements (constante `SEUIL_EXPORT_AUTO`) pour limiter la perte de progression en cas d'oubli. Chaque export télécharge un CSV horodaté (`etape3_export_outil_{horodatage}.csv`) avec les mêmes colonnes que le fichier chargé, plus les deux colonnes de validation. Une confirmation du navigateur se déclenche si l'onglet se ferme alors que des traitements n'ont pas encore été exportés.

## Phase 3 — Synthèse finale (`synthese_finale.py`)

Lit `etape1_{dept}.csv` (contexte **et** source directe des lignes RNU/trou de couverture), `etape2_{dept}.csv` (référence complète de tous les `id_gpu` traités à l'étape 2) et le dernier export de l'outil — les trois avec `encoding="utf-8-sig"`, qui tolère aussi bien un BOM (fichiers Python) qu'un fichier téléchargé par le navigateur.

Le nom réel produit par l'outil (`etape3_export_outil_{horodatage}.csv`, voir Phase 2) ne porte pas le code département — l'outil est générique, réutilisable pour n'importe quel département — et chaque export (manuel ou automatique) crée un nouveau fichier plutôt que d'écraser le précédent. `synthese_finale.py` ne demande donc pas ce nom en entrée : il liste `output/etape3_export_outil_*.csv` et retient celui dont l'horodatage encodé dans le nom (`AAAAMMJJ_HHMMSS`) est le plus grand, plutôt qu'un nom fixe, qui obligerait l'opérateur à renommer manuellement son export avant de lancer le script.

Sépare les occurrences exportées en trois lots : non traitées (`validation_manuelle_statut` vide — écrites à part dans `etape3_{dept}_non_traitees.csv`, exclues de la suite), retenues (`validé` ou `corrigé`) et rejetées (écrites à part dans `etape3_{dept}_rejetees.csv`, pour traçabilité, jamais supprimées).

Calcule ensuite, pour chaque `id_gpu` connu d'`etape2_{dept}.csv`, s'il est significatif (au moins une occurrence retenue) ou non. Les documents non significatifs — qu'ils n'aient jamais eu d'occurrence, ou que toutes leurs occurrences aient été rejetées ou non traitées — reçoivent une seule ligne de synthèse (`statut_verification_finale = "aucune occurrence trouvée"`, `nature_zone = "document_non_significatif"`), enrichie via `contexte_documents.py` à partir d'`etape1_{dept}.csv` directement (et non de l'export, car ces documents peuvent n'y jamais apparaître).

**Réintégration RNU et trou de couverture.** Après ce calcul de significativité, `synthese_finale.py` parcourt `etape1_{dept}.csv` une seconde fois pour construire deux nouveaux lots de lignes de synthèse, totalement indépendants d'`etape2_{dept}.csv` puisque ces communes n'y apparaissent jamais :
- pour chaque ligne `statut = "RNU confirmé"` : `nature_zone = "rnu"`, `portee_geometrique = "administrative"`, `statut_verification_finale = "validé automatique"`, `code_insee_commune` repris tel quel, `justification` pré-remplie avec un texte fixe citant l'article R.111-2 du code de l'urbanisme (constante `JUSTIFICATION_RNU` du module) ;
- pour chaque ligne `statut = "trou de couverture"` : `nature_zone = "trou_de_couverture"`, `statut_verification_finale = "aucune occurrence trouvée"`, `code_insee_commune` repris tel quel, tous les autres champs de contenu vides.

Ces deux lots ne passent jamais par `contexte_documents.py` (pas d'`id_gpu` à joindre) : `nom_document` reste vide, `communes` est renseigné directement avec `nom_commune` de la ligne d'origine.

**Calcul de `partition_gpu`.** Pour chaque `id_gpu` distinct rencontré dans `etape1_{dept}.csv` (une seule fois, indépendamment du nombre de communes qu'il couvre), `synthese_finale.py` construit la valeur `partition_gpu` :
- la famille (`DU` ou `PSMV`) se déduit de `statut` : `PSMV additionnel` → `PSMV`, tout autre statut avec `id_gpu` (`document trouvé`) → `DU` ;
- le code se déduit de `niveau_couverture` : `EPCI` → `code_siren_epci` (constant pour toutes les communes d'un même document intercommunal) ; `commune` → `code_insee_commune`, dont l'éventuelle annotation `"{code} (ancien code {ancien_code})"` (voir `etape1_identification/synthese.py`, `_code_insee_avec_origine`) est d'abord réduite à `ancien_code` seul — c'est sous cet ancien code, pas le code actuel de la commune fusionnée, que le document est resté indexé côté GPU.

Cette valeur est portée par chaque ligne `occurrence_locale` et `document_non_significatif` qui référence cet `id_gpu` ; elle reste vide pour les lignes RNU et trou de couverture, qui n'ont pas de document GPU et récupèrent leur géométrie autrement à l'étape 4 (couche `municipality`, via `code_insee_commune`).

Concatène l'ensemble (occurrences retenues + synthèses de documents non significatifs + synthèses RNU + synthèses trou de couverture) et écrit `etape3_{dept}.csv`. Un export d'outil sans la colonne `validation_manuelle_statut` lève `ExportOutilInvalide` (fichier chargé par erreur), tout fichier d'entrée manquant lève `FichiersEntreeIntrouvables` — les deux interceptées dans `main()`, qui affiche le message sur `stderr` et retourne `1`.

## Contrat de données

Pas d'obligation d'isomorphisme avec `etape2_{dept}.csv` : seules `id_gpu` et `id_occurrence` doivent rester stables **pour les occurrences issues d'un document réel** — voir la nuance RNU/trou de couverture ci-dessous — pour permettre à un traitement automatisé ultérieur de rejoindre `etape3_{dept}.csv` avec `etape1_{dept}.csv`/`etape2_{dept}.csv` si une colonne non reprise ici s'avérait nécessaire. Toute colonne modifiable par l'opérateur (voir "Édition en une seule passe" dans `etape-3-validation-manuelle.md`) doit en revanche être présente avec sa valeur finale dans `etape3_{dept}.csv` — une jointure vers `etape2_{dept}.csv` récupérerait sinon la valeur d'origine, potentiellement corrigée depuis en étape 3.

Colonnes de `etape3_{dept}.csv` :

| Colonne | Détail |
|---|---|
| `id_gpu` | clé de jointure pour une occurrence issue d'un document réel. **Vide pour RNU et trou de couverture** (par définition, ces communes n'ont pas de document GPU) — voir `code_insee_commune` ci-dessous. |
| `partition_gpu` | valeur exacte attendue par le paramètre `partition` de la couche `document` de l'API Carto GPU (`apicarto.ign.fr/api/gpu/document`), au format `<DU/PSMV>_<INSEE/SIREN>` — voir `etape-4-conception-technique.md`, "Sources de géométrie". Précalculée ici plutôt qu'à l'étape 4, à partir de colonnes déjà présentes dans `etape1_{dept}.csv` (`niveau_couverture`, `code_siren_epci`, `code_insee_commune`, `statut`) : `id_gpu` seul ne suffit pas, ce n'est pas la valeur attendue par ce paramètre (vérifié en réel : un appel `partition={id_gpu}` renvoie 0 résultat). Vide pour RNU, trou de couverture (pas de document GPU) et document non significatif issu d'un `id_gpu` introuvable dans `etape1_{dept}.csv` (cas normalement impossible, `etape2_{dept}.csv` étant lui-même dérivé d'`etape1_{dept}.csv`). |
| `id_occurrence` | vide sur une ligne de synthèse, quelle qu'elle soit (document non significatif, RNU, trou de couverture). |
| `code_insee_commune` | vide pour une occurrence issue d'un document réel (l'information est dans `communes`, potentiellement plusieurs communes) ; renseigné uniquement pour RNU et trou de couverture, qui sont toujours au grain d'une seule commune — sert de clé de repli pour la récupération de géométrie à l'étape 4, en l'absence d'`id_gpu`. |
| `nature_zone` | `occurrence_locale` / `rnu` / `document_non_significatif` / `trou_de_couverture` — origine de la ligne, déterminante pour le choix du processus de géométrie à l'étape 4. |
| `portee_geometrique` | `administrative` / `zone_specifique` / vide. Repris tel quel (potentiellement corrigé par l'opérateur) pour `occurrence_locale` ; assigné directement à `"administrative"` par le script pour `rnu` ; vide pour `document_non_significatif` et `trou_de_couverture` (ce ne sont pas des règles, la géométrie de contour leur est de toute façon assignée sans conditionner sur ce champ). |
| `statut_verification_finale` | `validé` / `corrigé` / `validé automatique` / `aucune occurrence trouvée`. `validé automatique` est réservé aux lignes RNU — il rend explicite qu'aucun opérateur ne les a relues, contrairement à `validé`/`corrigé` qui supposent un passage par l'outil. |
| `nom_document`, `communes` | contexte documentaire. `nom_document` vide pour RNU/trou de couverture (pas de document) ; `communes` toujours renseigné, y compris pour RNU/trou de couverture (une seule commune dans ce cas, reprise directement d'`etape1_{dept}.csv`). |
| `zone_reglementaire_mentionnee`, `justification`, `nature_occurrence`, `nature_juridique_piece`, `nature_sonore_zone` | pour `occurrence_locale`, valeur finale — potentiellement corrigée par l'opérateur, ce sont de véritables champs de formulaire dans `outil_validation.html` (voir Phase 2). Vide sur une ligne de synthèse "document non significatif" ou "trou de couverture". **Exception : `justification`, pré-remplie pour RNU** (texte fixe citant l'article R.111-2 du code de l'urbanisme). |
| `type_piece_source`, `lien_web_document`, `reference_type`, `reference_precise`, `extrait_significatif`, `contexte_documentaire`, `confiance_extrait`, `ocr_utilise`, `ocr_confiance` | pour `occurrence_locale`, valeur reprise telle quelle de l'étape 2 — aucun champ de formulaire ne permet à l'opérateur de les modifier dans `outil_validation.html` (voir Phase 2). Vide sur une ligne de synthèse "document non significatif" ou "trou de couverture". |
| `validation_manuelle_statut`, `validation_manuelle_commentaire` | décision de l'opérateur ; vides par construction pour les trois types de lignes de synthèse (document non significatif, RNU, trou de couverture), qui ne passent jamais par l'outil. |

`nature_juridique_piece` (déduite mécaniquement à l'étape 2 à partir de `type_piece_source`) fait partie des champs à liste déroulante modifiables dans l'outil au même titre que `nature_occurrence` ou `nature_sonore_zone` — un choix de simplicité d'implémentation (un seul type de champ pour toutes les colonnes de classification) plutôt qu'une nécessité métier.

## Gestion des erreurs et cas particuliers

Dans le même esprit que les étapes 1 et 2 (aucun échec isolé ne bloque tout le traitement), `synthese_finale.py` ne fait jamais l'hypothèse que la relecture est complète : les occurrences non traitées sont explicitement séparées et documentées (`etape3_{dept}_non_traitees.csv`) plutôt que silencieusement comptées comme validées ou perdues. `preparer_revue.py` et `synthese_finale.py` s'arrêtent avec un message explicite si un fichier d'entrée attendu est introuvable — contrairement à un échec isolé sur une ligne, l'absence d'un fichier d'entrée entier ne laisse rien d'exploitable en aval.

## Validation du fonctionnement

L'ensemble du pipeline (`preparer_revue.py` → `outil_validation.html` → `synthese_finale.py`) a été testé de bout en bout à deux reprises :

1. **Données factices** : un département fictif à quatre documents couvrant les cas limites (occurrences à valider avec caractères piégeux pour le rendu HTML, document jamais soumis à relecture, document dont l'unique occurrence reste rejetée, occurrence laissée non traitée). Le test automatisé (Playwright, simulant le chargement du CSV, l'édition de champs et les clics de validation/rejet dans un vrai navigateur) a permis de détecter et corriger un bug réel : le tri des documents par priorité traitait `priorite = 0` (le cas le plus prioritaire) comme une valeur absente, à cause d'un test de vérité JavaScript (`0 || 99` vaut `99`) plutôt que d'un test de présence (`Number.isFinite`).
2. **Données réelles** : `etape1_067.csv` et `etape2_067.csv`, tels que présents sur la branche `poc-urbanisme-plu` (17 occurrences, un seul document intercommunal couvrant 33 communes). A confirmé la jointure des communes, l'encodage `utf-8-sig` (BOM en entrée et en sortie), le champ `nature_juridique_piece`, ainsi que le déclenchement de l'export automatique après 10 traitements.

Aucun de ces deux jeux de test ne couvre de commune RNU ni de trou de couverture : la génération des lignes de synthèse correspondantes (voir "Réintégration RNU et trou de couverture" ci-dessus) n'a pas été vérifiée de bout en bout par un test automatisé — à faire avant tout usage réel visant ces cas.

## Dépendances retenues

- Bibliothèque standard uniquement (`csv`, `pathlib`, `argparse`) pour `contexte_documents.py`, `preparer_revue.py` et `synthese_finale.py` — aucune dépendance supplémentaire par rapport à `requirements.txt` existant, cohérent avec le choix déjà fait aux étapes 1 et 2 d'éviter `pandas` pour un export ligne à ligne simple (voir `etape-1-conception-technique.md`, "Dépendances retenues").
- Aucune dépendance pour `outil_validation.html` : HTML/CSS/JavaScript natif, aucune installation, aucun accès réseau requis pour l'utiliser.

## Prochaine étape

Étape 4 — construction des géométries associées à chaque ligne de `etape3_{dept}.csv`, selon `nature_zone` et `portee_geometrique` (voir `etape-4-construction-geometries-diagbruit.md` et `etape-4-conception-technique.md`).
