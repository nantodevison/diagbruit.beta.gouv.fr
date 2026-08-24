# Étape 4 — Conception technique : construction des géométries

*Document de cadrage technique, faisant suite à `etape-4-construction-geometries-diagbruit.md` et à `etape-3-conception-technique.md`.*

## Posture

Même sous-dossier du même POC que les étapes 1, 2 et 3 (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, isolé du reste du produit, preuve de concept plutôt que composant prêt à intégrer.

Un écart assumé par rapport aux étapes précédentes : cette étape manipule de vraies géométries (récupération, union, validité OGC, écriture GeoPackage), une tâche pour laquelle réimplémenter l'équivalent à la main avec la seule bibliothèque standard serait un travail disproportionné pour un POC — voir "Dépendances retenues" pour le détail de cet écart et sa justification.

## Architecture des dossiers

```
poc-urbanisme-plu/
├── etape1_identification/               # existant
├── etape2_analyse_reglements/           # existant
├── etape3_validation_manuelle/          # existant
├── etape4_geometries/
│   ├── __init__.py                      # vide, comme les modules précédents
│   ├── sources_gpu.py                   # aide partagée : appels API Carto GPU (couches document/municipality)
│   ├── preparer_geometries.py           # Phase 1 — auto : remplit geometries_administratives, prépare occurrences_a_georeferencer
│   ├── controle_qualite.py              # aide partagée : validité OGC et type de géométrie (pas le CRS, vérifié séparément — voir Phase 3)
│   ├── synthese_geometries.py           # Phase 3 — fusionne + contrôle qualité + vérification/reprojection CRS → etape4_{dept}.gpkg
│   └── modele_validation_manuelle.qgz   # projet QGIS de fond de carte pour la Phase 2 — voir "Phase 2 — Édition manuelle (QGIS)"
└── output/
    ├── etape1_{dept}.csv
    ├── etape2_{dept}.csv
    ├── etape3_{dept}.csv
    ├── etape4_{dept}_a_completer.gpkg       # sortie de preparer_geometries.py ; édité manuellement dans QGIS (Phase 2)
    ├── etape4_{dept}.gpkg                   # sortie de synthese_geometries.py — contrat pour l'étape 5/6 (couche unique "geometries")
    ├── etape4_{dept}_non_traitees.csv       # occurrences jamais géoréférencées, si non vide
    └── etape4_{dept}_erreurs.csv            # échecs d'appel API Carto GPU (Phase 1) + géométries rejetées au contrôle qualité + fusions incohérentes (Phase 3), si non vide
```

Comme l'étape 3, l'étape 4 n'a pas de `main.py` unique : le travail manuel dans QGIS (Phase 2) s'intercale entre les deux phases automatisées. Usage, depuis `poc-urbanisme-plu/` :

```
python -m etape4_geometries.preparer_geometries --dept 033
# ouvrir etape4_033_a_completer.gpkg dans QGIS, compléter la couche occurrences_a_georeferencer
python -m etape4_geometries.synthese_geometries --dept 033
```

## Phase 1 — Préparation (`preparer_geometries.py`)

Lit `etape3_{dept}.csv` (module `csv` de la bibliothèque standard, `encoding="utf-8-sig"`, cohérent avec le reste du pipeline). Pour chaque ligne, deux chemins possibles :

- **`portee_geometrique == "zone_specifique"`** → la ligne part telle quelle (tous ses attributs, géométrie laissée vide) dans la couche `occurrences_a_georeferencer`, sans aucun appel réseau.
- **Tous les autres cas** (`portee_geometrique == "administrative"`, ou `nature_zone` en `document_non_significatif` / `rnu` / `trou_de_couverture`) → une géométrie est récupérée automatiquement, via `sources_gpu.py` :
  - si `partition_gpu` est renseigné → appel à la couche `document` de l'API Carto GPU, filtrée sur cette valeur (déjà précalculée à l'étape 3, voir `etape-3-conception-technique.md`, "Calcul de `partition_gpu`"), pour récupérer le périmètre exact du document ;
  - sinon (RNU, trou de couverture — `id_gpu`/`partition_gpu` vides) → appel à la couche `municipality`, déjà utilisée à l'étape 1 pour détecter le RNU, avec `code_insee_commune` en paramètre.

Avant tout appel réseau, les lignes sont dédoublonnées sur `id_gpu` (un PLUi intercommunal a autant de lignes dans `etape3_{dept}.csv` que de communes ou d'occurrences, mais un seul périmètre à récupérer) — même logique que le dédoublonnage déjà appliqué à l'étape 1 (EPCI) et à l'étape 2 (résolution de pièces). C'est `partition_gpu`, retrouvé pour l'`id_gpu` retenu par la déduplication, qui est effectivement passé à l'appel réseau.

Le paramètre de filtrage de la couche `document` par identifiant s'appelle `partition` (conforme à la spec OpenAPI du module GPU, `https://apicarto.ign.fr/api/doc/gpu.yml`), mais attend un format `<DU/PSMV>_<INSEE/SIREN>`, distinct de l'`id_gpu` utilisé partout ailleurs dans le pipeline. `id_gpu` (renvoyé par `www.geoportail-urbanisme.gouv.fr/api/document`, capturé à l'étape 1) et `partition` (attendu par `apicarto.ign.fr/api/gpu/document`) sont donc deux identifiants distincts pour le même document, sur deux API différentes du même écosystème GPU. La correspondance entre les deux n'est stockée nulle part dans le GPU lui-même : elle se reconstruit à partir de colonnes déjà présentes dans `etape1_{dept}.csv` (`niveau_couverture`, `code_siren_epci`, `code_insee_commune`, `statut`) — voir `etape-3-conception-technique.md`, "Calcul de `partition_gpu`", pour le détail du calcul, fait à l'étape 3 plutôt qu'ici.

Code réel de `sources_gpu.py` — les tentatives/délais reprennent le pattern exact des étapes 1 à 3, `retry_if_exception_type` + `reraise=True` inclus, plutôt qu'une version simplifiée :

```python
from dataclasses import dataclass

import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

API_CARTO_GPU = "https://apicarto.ign.fr/api/gpu"


@dataclass
class ResultatGeometrie:
    geometrie_geojson: dict | None
    erreur: str | None


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _get(url, params):
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response


def _unir_features(features):
    """Union géométrique de plusieurs features en une seule géométrie
    GeoJSON — un document peut être renvoyé en plusieurs entités adjacentes
    plutôt qu'une seule."""
    geometries = [shape(feature["geometry"]) for feature in features]
    return mapping(unary_union(geometries))


def recuperer_geometrie_document(partition_gpu):
    """Périmètre d'un document d'urbanisme, via la couche `document` de l'API
    Carto GPU. `partition_gpu` (précalculé à l'étape 3, format
    `<DU/PSMV>_<INSEE/SIREN>`) est la valeur attendue par le paramètre
    `partition` — vérifié en conditions réelles sur le PLUi et le PSMV de
    l'Eurométropole de Strasbourg : chaque appel renvoie exactement une
    feature, dont `properties.id` correspond bien à l'`id_gpu` d'origine.
    """
    try:
        response = _get(f"{API_CARTO_GPU}/document", {"partition": partition_gpu})
    except requests.exceptions.RequestException as exc:
        return ResultatGeometrie(geometrie_geojson=None, erreur=f"appel document indisponible : {exc}")

    features = response.json().get("features", [])
    if not features:
        return ResultatGeometrie(geometrie_geojson=None, erreur="aucune géométrie renvoyée par le GPU")
    return ResultatGeometrie(geometrie_geojson=_unir_features(features), erreur=None)


def recuperer_geometrie_commune(code_insee_commune):
    """Contour d'une commune, via la couche `municipality` — déjà appelée à
    l'étape 1 (etape1_identification/documents_urbanisme.py, `_verifier_rnu`)
    pour détecter le RNU. Ici, c'est sa géométrie qui nous intéresse, pas son
    statut RNU."""
    try:
        response = _get(f"{API_CARTO_GPU}/municipality", {"insee": code_insee_commune})
    except requests.exceptions.RequestException as exc:
        return ResultatGeometrie(geometrie_geojson=None, erreur=f"appel municipality indisponible : {exc}")

    features = response.json().get("features", [])
    if not features:
        return ResultatGeometrie(geometrie_geojson=None, erreur="commune introuvable dans le GPU")
    return ResultatGeometrie(geometrie_geojson=features[0]["geometry"], erreur=None)
```

Un échec (document introuvable dans le GPU, timeout persistant après les tentatives de `tenacity`, réponse vide) n'interrompt jamais le traitement du reste du département : la ligne concernée part dans `etape4_{dept}_erreurs.csv` (identifiant, source interrogée, message d'erreur), et le reste continue — même principe que les trois étapes précédentes.

`preparer_geometries.py` écrit ensuite `etape4_{dept}_a_completer.gpkg`, avec ses deux couches (`geometries_administratives`, `occurrences_a_georeferencer`) au schéma identique — voir "Contrat de données" plus bas.

## Phase 2 — Édition manuelle (QGIS)

Aucun script : l'opérateur ouvre `etape4_{dept}_a_completer.gpkg` dans QGIS, charge les deux couches. `geometries_administratives` sert de fond de carte de référence pendant le travail — elle permet de vérifier au passage que le pré-remplissage automatique a l'air correct (bonne occasion de repérer une géométrie qui semble étrange avant même la synthèse finale).

**Fond de carte recommandé** : `modele_validation_manuelle.qgz`, un projet QGIS de base à réutiliser plutôt qu'à reconstruire à chaque département — fortement conseillé pour repérer précisément les limites d'une zone réglementaire (parcelle par parcelle) pendant le tracé. Il charge :
- les parcelles cadastrales (flux WFS de la Géoplateforme, service "Parcellaire express", table `parcelle`), filtrées sur le département 67 pour limiter le volume de données — symbologie trait pointillé noir fin ;
- les communes, au format surfacique (flux WFS du GPU), filtrées sur le département 67 — symbologie trait pointillé gris foncé épais ;
- un fond de photographies aériennes (flux WMTS de la Géoplateforme, service Orthophotos — `https://data.geopf.fr/annexes/ressources/wmts/ortho.xml`) ;
- un fond OpenStreetMap.

**Avant de l'utiliser sur un autre département que le 067**, penser à mettre à jour les filtres départementaux des deux couches WFS (parcelles, communes) — sans quoi elles resteraient limitées au département 67 quel que soit le département réellement travaillé.

Pour chaque entité de `occurrences_a_georeferencer` (déjà pré-remplie en attributs, géométrie vide) : sélectionner la ligne dans la table attributaire, passer en mode édition, utiliser l'outil de digitalisation avec la fonction **"Ajouter une partie"** pour dessiner directement la géométrie de l'entité sélectionnée, en s'appuyant sur `lien_web_document` (ouvrir le PDF), `reference_precise` (aller au bon article ou à la bonne page) et `zone_reglementaire_mentionnee`/`justification` (savoir ce qu'on cherche à représenter). QGIS écrit directement dans le GeoPackage à chaque sauvegarde — pas d'export séparé à gérer.

Si, en traçant, l'opérateur constate que deux occurrences décrivent en réalité la même règle sur le même secteur (voir "Mécanisme de fusion" plus bas), renseigner `fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence` sur l'occurrence membre plutôt que de la tracer une deuxième fois — la géométrie peut alors rester vide pour cette ligne. Si cette vérification révèle par ailleurs que `nature_sonore_zone` est manifestement erronée sur l'une des deux occurrences (classification automatique de l'étape 2 prise en défaut), l'opérateur peut la corriger directement dans le gpkg — voir "Contrat de données", `nature_sonore_zone`.

**Recommandation de validation** (même logique que le test Playwright de l'étape 3) : avant tout usage réel, tester ce flux avec un jeu de données factice couvrant les cas limites (une occurrence avec un attribut vide, une occurrence dont le tracé recouvre volontairement une géométrie de `geometries_administratives`, une occurrence volontairement laissée sans géométrie) pour s'assurer que la Phase 3 les traite correctement.

## Phase 3 — Synthèse (`synthese_geometries.py`)

Lit `etape4_{dept}_a_completer.gpkg` (deux couches). Sépare `occurrences_a_georeferencer` en deux lots selon que la géométrie est renseignée ou non — sauf exception, voir plus bas :

- **géométrie vide, et aucune fusion déclarée** → écrites à part dans `etape4_{dept}_non_traitees.csv` (attributs seuls, pas de géométrie à exporter), exclues de la suite — même logique que les occurrences non traitées de l'étape 3 : jamais silencieusement ignorées, toujours listées pour reprise.
- **géométrie renseignée, ou géométrie vide avec une fusion déclarée** (`fusionne_avec_id_occurrence` renseigné — voir "Mécanisme de fusion" ci-dessous) → passent au contrôle qualité avec les entités de `geometries_administratives`.

**Contrôle qualité** (`controle_qualite.py`), appliqué à chaque géométrie avant écriture dans le fichier final. La fonction prend directement une géométrie Shapely (ou `None`) plutôt qu'un GeoJSON à convertir en interne, cohérent avec le fait que les deux appelants (`preparer_geometries.py` et `synthese_geometries.py`) manipulent déjà des géométries Shapely via `geopandas`, jamais du GeoJSON brut. Conséquence directe : la vérification "géométrie vide/absente" doit passer en premier (un `geom.geom_type` sur `None` ferait planter la fonction), avant la vérification de type. Un paramètre `autorise_vide` permet à l'appelant, après ses propres vérifications de cohérence, d'accepter une géométrie vide plutôt que de la rejeter systématiquement — cas d'une occurrence membre d'un groupe fusionné, dont la localisation est portée par le meneur :

```python
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

TYPES_AUTORISES = ("Polygon", "MultiPolygon")


def controler_geometrie(geom: BaseGeometry | None, autorise_vide: bool = False):
    """Renvoie (geometrie_corrigee, erreur). erreur est None si tout est en ordre."""
    if geom is None or geom.is_empty:
        if autorise_vide:
            return None, None
        return None, "géométrie vide"

    if geom.geom_type not in TYPES_AUTORISES:
        return None, f"type de géométrie inattendu : {geom.geom_type}"

    if not geom.is_valid:
        # make_valid corrige la plupart des cas courants (auto-intersection,
        # anneau non fermé) sans intervention manuelle ; si le résultat n'est
        # toujours pas un polygone exploitable, on part en erreur plutôt que
        # d'écrire une géométrie douteuse dans le livrable final.
        geom = make_valid(geom)
        if geom.geom_type not in TYPES_AUTORISES:
            return None, "géométrie invalide, non corrigible automatiquement"

    return geom, None
```

Une géométrie qui échoue au contrôle qualité part elle aussi dans `etape4_{dept}_erreurs.csv`, plutôt que de bloquer l'écriture du reste du fichier — **dans le même fichier** que celui éventuellement déjà écrit par `preparer_geometries.py` (Phase 1, échecs d'appel API) : `synthese_geometries.py` relit ce fichier s'il existe et complète la liste plutôt que de l'écraser, pour qu'un enchaînement Phase 1 → Phase 2 → Phase 3 ne fasse jamais disparaître une erreur déjà consignée. Cette reprise ne concerne toutefois que les erreurs de Phase 1 : les erreurs de contrôle qualité et de fusion (voir "Mécanisme de fusion" ci-dessous), elles, sont toujours recalculées à neuf et jamais reprises d'une exécution antérieure — contrairement à `preparer_geometries.py`, `synthese_geometries.py` est amené à être relancé plusieurs fois (ex. ajustement itératif d'une fusion dans QGIS), et reprendre ses propres erreurs d'une exécution à l'autre les dupliquerait à chaque relance, en plus de faire indéfiniment resurgir une erreur déjà corrigée entre-temps. Pour la même raison, `etape4_{dept}_erreurs.csv` et `etape4_{dept}_non_traitees.csv` sont supprimés (pas seulement laissés tels quels) si une exécution ne trouve plus rien à y consigner — un fichier de la Phase 3 reflète toujours l'état de la dernière exécution, jamais un mélange d'anciens et de nouveaux constats.

Avant le contrôle qualité, chaque occurrence déclarant une fusion (voir "Mécanisme de fusion" ci-dessous) est vérifiée : une fusion cohérente autorise une géométrie vide pour cette occurrence (elle n'est alors plus routée vers `_non_traitees.csv`) ; une fusion incohérente part en erreur, et l'occurrence n'est conservée dans le livrable que si elle a par ailleurs sa propre géométrie.

Fusionne enfin les géométries validées des deux couches d'origine en une seule couche finale (nommée `geometries`), et écrit `etape4_{dept}.gpkg` — le contrat de données pour l'étape 5/6. Le CRS est vérifié (et reprojeté si besoin) en EPSG:4326 avant écriture, pour garantir que le fichier final est homogène même si une des sources a, par erreur, répondu dans un autre système de coordonnées.

## Mécanisme de fusion

*Répond à un besoin identifié pendant le tracé manuel du département 067 (Eurométropole de Strasbourg) — voir `ameliorations-identifiees.md`, "Pas de mécanisme de rejet pour les occurrences à géométrie manuelle" pour le besoin symétrique de rejet, non couvert ici.*

**Besoin** : plusieurs occurrences peuvent, une fois localisées, s'avérer décrire la même règle sur le même secteur — même objectif de lutte contre le bruit (`nature_sonore_zone`), même localisation — avec des citations différentes (`extrait_significatif`, `contexte_documentaire`, `justification`), y compris entre deux pièces distinctes d'un même document (ex. règlement écrit et OAP). Sans mécanisme dédié, chacune produirait sa propre géométrie et, en aval, son propre message — redondant pour l'utilisateur final de diagBruit.

**Principe retenu** : ne jamais fusionner les géométries elles-mêmes — le chevauchement de géométries est déjà un non-problème assumé par le pipeline (voir `etape-4-construction-geometries-diagbruit.md`, "Chevauchement des géométries"). La fusion ne fait que relier des occurrences entre elles ; le regroupement effectif (un seul message plutôt qu'un par occurrence) revient à l'étape 5, pas à celle-ci.

**Déclaration par l'opérateur (Phase 2)** : deux nouvelles colonnes, présentes dans les deux couches (mêmes colonnes partout, voir "Contrat de données") — `fusionne_avec_id_gpu` et `fusionne_avec_id_occurrence`. Vides par défaut (écrites ainsi par `preparer_geometries.py`), elles sont renseignées à la main dans QGIS par l'opérateur, sur une occurrence *membre*, avec l'`id_gpu`/`id_occurrence` de l'occurrence *meneuse* du groupe — jamais l'inverse. Un meneur n'a pas de statut déclaré séparément : c'est simplement toute occurrence référencée par au moins un `fusionne_avec_id_occurrence` d'une autre ligne (0 référence = occurrence indépendante ordinaire, plusieurs références = groupe à plusieurs membres). Ce choix de référence (le couple `id_gpu` + `id_occurrence` du meneur, plutôt qu'un identifiant de groupe inventé) reprend la conclusion déjà actée pour le besoin équivalent identifié à l'étape 3 (voir `ameliorations-identifiees.md`, "Détection des occurrences 'doublons'").

Une occurrence membre (`fusionne_avec_id_occurrence` renseigné) n'a pas besoin de sa propre géométrie : sa localisation est portée par le meneur, ce qui évite à l'opérateur de retracer deux fois le même secteur.

**Vérification automatique (Phase 3, `synthese_geometries.py`)** : toute fusion déclarée est revérifiée avant d'être acceptée, jamais prise sur la seule foi de l'opérateur pour les critères vérifiables automatiquement. Une fusion est valide si, et seulement si :
- le meneur référencé existe (recherché dans les deux couches par `id_gpu` + `id_occurrence`) ;
- le meneur n'est lui-même membre d'aucun autre groupe — **pas de chaînage**, une seule profondeur de référence autorisée ;
- membre et meneur ont tous deux `nature_zone == "occurrence_locale"` — la fusion est réservée aux occurrences porteuses d'une vraie règle, pas aux lignes de synthèse (`document_non_significatif` / `rnu` / `trou_de_couverture`), qui n'ont pas de contenu de règle distinct à combiner et partagent souvent un `lien_web_document` identique sans rapport géographique (ex. toutes les communes RNU du département pointent vers la même fiche Légifrance) — cette restriction est d'autant plus nécessaire que `lien_web_document` lui-même n'est pas un critère vérifié (voir ci-dessous) ;
- `nature_sonore_zone` est identique entre membre et meneur, et non vide — valeur lue dans le gpkg, donc l'éventuelle correction faite par l'opérateur (voir "Contrat de données") est bien celle prise en compte ;
- le meneur a lui-même une géométrie (non vide) — un groupe ne peut pas être privé de localisation.

`lien_web_document` n'est **pas** vérifié automatiquement : le critère serait trop restrictif en usage réel, une même règle pouvant être citée dans deux pièces distinctes d'un même document, avec deux liens différents. Comme la **localisation** (le critère "même secteur"), c'est un jugement humain assumé de l'opérateur en Phase 2, jamais recontrôlé par le code.

Une fusion invalide part dans `etape4_{dept}_erreurs.csv` (source `"fusion"`). Si le membre a par ailleurs sa propre géométrie (cas d'une fusion mal déclarée sur une occurrence par ailleurs correctement tracée), elle est tout de même conservée comme occurrence indépendante dans le livrable final — la géométrie n'est jamais perdue pour une erreur de métadonnées. `fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence` restent néanmoins tels quels sur cette ligne (pas effacés) : c'est l'entrée dans `etape4_{dept}_erreurs.csv` qui signale que la référence n'a pas été retenue, pas l'état des colonnes dans le gpkg final.

**Sortie** : chaque occurrence d'un groupe garde sa propre ligne dans `etape4_{dept}.gpkg` (géométrie propre pour le meneur et tout membre qui en a une, géométrie vide pour un membre qui s'appuie sur celle du meneur), avec `fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence` renseignés pour la retrouver. L'étape 5 reconstruit un groupe par simple requête attributaire sur ces deux colonnes, sans avoir besoin d'un identifiant de groupe matérialisé séparé.

## Contrat de données

`etape4_{dept}.gpkg` porte une unique couche, nommée `geometries` — c'est le nom à utiliser pour l'ouvrir depuis un code Python (`geopandas.read_file(chemin, layer="geometries")`) ou pour la retrouver dans le panneau de couches de QGIS. Ses colonnes sont identiques à celles des deux couches intermédiaires de `etape4_{dept}_a_completer.gpkg` (`geometries_administratives` et `occurrences_a_georeferencer`), pour que leur fusion soit une simple concaténation :

| Colonne | Détail |
|---|---|
| `id_geometrie` | entier auto-incrémenté, généré par `preparer_geometries.py` — unique sur l'ensemble du fichier `etape4_{dept}_a_completer.gpkg` (un seul compteur partagé entre les deux couches, pas un compteur par couche), pour qu'un opérateur QGIS puisse référencer une géométrie précise sans manipuler `id_gpu`/`id_occurrence`, y compris après la fusion des deux couches en une seule à la Phase 3. |
| `id_gpu`, `id_occurrence` | reprises de `etape3_{dept}.csv` telles quelles, vides dans les mêmes conditions (RNU, trou de couverture, lignes de synthèse). |
| `code_insee_commune` | reprise de `etape3_{dept}.csv` — renseignée uniquement pour RNU et trou de couverture. |
| `nature_zone` | reprise de `etape3_{dept}.csv` — `occurrence_locale` / `rnu` / `document_non_significatif` / `trou_de_couverture`. |
| `portee_geometrique` | reprise de `etape3_{dept}.csv`. |
| `nom_document`, `communes` | reprises de `etape3_{dept}.csv`, pour qu'un opérateur SIG identifie une géométrie sans rouvrir le CSV. |
| `type_piece_source`, `reference_type`, `reference_precise` | reprises de `etape3_{dept}.csv`, vides sauf `occurrence_locale`. |
| `lien_web_document` | reprise de `etape3_{dept}.csv` pour `occurrence_locale` et `document_non_significatif` ; vide pour `trou_de_couverture` ; pointe vers la fiche Légifrance de l'article R.111-2 pour `rnu` (`https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000031721316`), plutôt que vers un document qui n'existe pas. |
| `zone_reglementaire_mentionnee` | reprise de `etape3_{dept}.csv`, vide sauf `occurrence_locale`. |
| `nature_sonore_zone` | reprise de `etape3_{dept}.csv` — `lutte_bruit_existant` / `preservation_zone_calme` / `autre` (voir `etape-2-analyse-documents-urbanisme-diagbruit.md`). Critère central du mécanisme de fusion, voir "Mécanisme de fusion" ci-dessus. **Corrigible par l'opérateur en Phase 2** (contrairement aux autres colonnes reprises telles quelles) si la classification automatique de l'étape 2 s'avère erronée à l'usage — par exemple deux occurrences qu'un opérateur sait devoir fusionner mais dont l'une porte une valeur visiblement fausse. Une fois corrigée dans le gpkg, c'est cette valeur qui fait référence pour la suite du pipeline (vérification de fusion en Phase 3, puis étape 5) : `synthese_geometries.py` ne relit jamais `etape3_{dept}.csv` pour ce champ, seulement le gpkg — la correction n'est donc jamais écrasée par une relecture de la source d'origine. Aucune trace séparée de la correction n'est conservée (pas de colonne "valeur d'origine") ; discipline opérationnelle jugée suffisante pour ce POC. |
| `justification` | reprise de `etape3_{dept}.csv`. |
| `validation_manuelle_commentaire` | reprise de `etape3_{dept}.csv`. |
| `statut_verification_finale` | reprise de `etape3_{dept}.csv` — `validé` / `corrigé` / `validé automatique` / `aucune occurrence trouvée`. |
| `fusionne_avec_id_gpu`, `fusionne_avec_id_occurrence` | jamais reprises de `etape3_{dept}.csv` — vides à la sortie de `preparer_geometries.py`, renseignées par l'opérateur en Phase 2 pour désigner le meneur d'un groupe fusionné. Voir "Mécanisme de fusion" ci-dessus. |
| `date_traitement` | date d'écriture de la ligne par `preparer_geometries.py` (Phase 1), pour les deux couches — y compris pour une entité de `occurrences_a_georeferencer` : c'est donc la date de création de la ligne vide, avant tracé manuel, pas celle du tracé effectif. `synthese_geometries.py` (Phase 3) ne la modifie jamais : la valeur écrite en Phase 1 traverse la Phase 2 et la Phase 3 sans changer. Distincte de la `date_traitement` des étapes précédentes, conservée telle quelle par ailleurs. |

## Gestion des erreurs

Même principe que les trois étapes précédentes : aucun échec isolé (appel API Carto GPU, géométrie invalide, fusion incohérente, entité jamais géoréférencée) n'interrompt le traitement du reste du département. `preparer_geometries.py` et `synthese_geometries.py` s'arrêtent en revanche avec un message explicite si `etape3_{dept}.csv` (ou, pour la phase 3, `etape4_{dept}_a_completer.gpkg`) est introuvable — l'absence du fichier d'entrée entier ne laisse rien d'exploitable en aval, contrairement à un échec isolé sur une ligne.

## Dépendances retenues

- `requests`, `tenacity` — repris à l'identique des étapes précédentes, pour les appels à l'API Carto GPU.
- **`geopandas`** (et ses dépendances : `shapely`, `pyogrio` pour la lecture/écriture GeoPackage, `pandas` en transitif) — écart assumé par rapport au principe "pas de `pandas`" tenu aux étapes 1 à 3. Ce principe avait du sens pour des exports CSV ligne à ligne, où `pandas` n'aurait rien apporté ; il n'a plus lieu d'être ici, où la tâche (union de géométries, écriture GeoPackage multi-couches, vérification de validité OGC) est fondamentalement du traitement géospatial — le domaine que `geopandas`/`shapely` couvrent, et que la bibliothèque standard ne couvre pas du tout. Réimplémenter cette logique à la main serait un travail disproportionné pour un POC, à l'inverse de l'esprit de simplicité qui a justifié d'éviter `pandas` ailleurs.

## Prochaine étape

Étape 5 — rédaction du ton des messages associés aux occurrences validées des documents significatifs, à partir de `etape4_{dept}.gpkg` et du contenu textuel de `etape3_{dept}.csv`. Devra exploiter `fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence` (voir "Mécanisme de fusion" plus haut) pour composer un seul message par groupe fusionné plutôt qu'un par occurrence — c'est là, pas à l'étape 4, que le regroupement textuel doit avoir lieu.
