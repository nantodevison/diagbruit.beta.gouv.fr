# Étape 4 — Conception technique : construction des géométries

*Document de cadrage technique, faisant suite à `etape-4-construction-geometries-diagbruit.md` et à `etape-3-conception-technique.md`. Version issue des échanges du 17/08/2026. Révisé le 17/08/2026, lors de l'implémentation réelle : le paramètre `partition` de la couche `document` de l'API Carto GPU attend un format `<DU/PSMV>_<INSEE/SIREN>`, pas `id_gpu` (vérifié contre le swagger réel puis en réel sur le PLUi et le PSMV de l'Eurométropole de Strasbourg). Cette valeur (`partition_gpu`) est désormais précalculée à l'étape 3 plutôt que reconstruite ici — voir `etape-3-conception-technique.md`, "Calcul de `partition_gpu`", et "Phase 1 — Préparation" ci-dessous.*

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
│   └── synthese_geometries.py           # Phase 3 — fusionne + contrôle qualité + vérification/reprojection CRS → etape4_{dept}.gpkg
└── output/
    ├── etape1_{dept}.csv
    ├── etape2_{dept}.csv
    ├── etape3_{dept}.csv
    ├── etape4_{dept}_a_completer.gpkg       # sortie de preparer_geometries.py ; édité manuellement dans QGIS (Phase 2)
    ├── etape4_{dept}.gpkg                   # sortie de synthese_geometries.py — contrat pour l'étape 5/6 (couche unique "geometries")
    ├── etape4_{dept}_non_traitees.csv       # occurrences jamais géoréférencées, si non vide
    └── etape4_{dept}_erreurs.csv            # échecs d'appel API Carto GPU (Phase 1) + géométries rejetées au contrôle qualité (Phase 3), si non vide
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

Code réel de `sources_gpu.py` (mis à jour ici le 17/08/2026 pour rester synchronisé avec l'implémentation, après la levée du point d'attention ci-dessous — les tentatives/délais reprennent le pattern exact des étapes 1 à 3, `retry_if_exception_type` + `reraise=True` inclus, plutôt qu'une version simplifiée) :

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
    `partition` — vérifié en réel le 17/08/2026 sur le PLUi et le PSMV de
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

Pour chaque entité de `occurrences_a_georeferencer` (déjà pré-remplie en attributs, géométrie vide) : sélectionner la ligne dans la table attributaire, passer en mode édition, utiliser l'outil de digitalisation avec la fonction **"Ajouter une partie"** pour dessiner directement la géométrie de l'entité sélectionnée, en s'appuyant sur `lien_web_document` (ouvrir le PDF), `reference_precise` (aller au bon article ou à la bonne page) et `zone_reglementaire_mentionnee`/`justification` (savoir ce qu'on cherche à représenter). QGIS écrit directement dans le GeoPackage à chaque sauvegarde — pas d'export séparé à gérer.

**Recommandation de validation** (même logique que le test Playwright de l'étape 3) : avant tout usage réel, tester ce flux avec un jeu de données factice couvrant les cas limites (une occurrence avec un attribut vide, une occurrence dont le tracé recouvre volontairement une géométrie de `geometries_administratives`, une occurrence volontairement laissée sans géométrie) pour s'assurer que la Phase 3 les traite correctement.

## Phase 3 — Synthèse (`synthese_geometries.py`)

Lit `etape4_{dept}_a_completer.gpkg` (deux couches). Sépare `occurrences_a_georeferencer` en deux lots selon que la géométrie est renseignée ou non :

- **géométrie vide** → écrites à part dans `etape4_{dept}_non_traitees.csv` (attributs seuls, pas de géométrie à exporter), exclues de la suite — même logique que les occurrences non traitées de l'étape 3 : jamais silencieusement ignorées, toujours listées pour reprise.
- **géométrie renseignée** → passent au contrôle qualité avec les entités de `geometries_administratives`.

**Contrôle qualité** (`controle_qualite.py`), appliqué à chaque géométrie avant écriture dans le fichier final. Écart par rapport à la version initiale de ce document : les deux appelants (`preparer_geometries.py` et `synthese_geometries.py`) manipulent déjà des géométries Shapely via `geopandas`, jamais du GeoJSON brut — la fonction prend donc directement une géométrie Shapely (ou `None`) plutôt qu'un GeoJSON à convertir en interne. Conséquence directe : la vérification "géométrie vide/absente" doit passer en premier (un `geom.geom_type` sur `None` ferait planter la fonction), avant la vérification de type :

```python
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

TYPES_AUTORISES = ("Polygon", "MultiPolygon")


def controler_geometrie(geom: BaseGeometry | None):
    """Renvoie (geometrie_corrigee, erreur). erreur est None si tout est en ordre."""
    if geom is None or geom.is_empty:
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

Une géométrie qui échoue au contrôle qualité part elle aussi dans `etape4_{dept}_erreurs.csv`, plutôt que de bloquer l'écriture du reste du fichier — **dans le même fichier** que celui éventuellement déjà écrit par `preparer_geometries.py` (Phase 1, échecs d'appel API) : `synthese_geometries.py` relit ce fichier s'il existe et complète la liste plutôt que de l'écraser, pour qu'un enchaînement Phase 1 → Phase 2 → Phase 3 ne fasse jamais disparaître une erreur déjà consignée.

Fusionne enfin les géométries validées des deux couches d'origine en une seule couche finale (nommée `geometries`), et écrit `etape4_{dept}.gpkg` — le contrat de données pour l'étape 5/6. Le CRS est vérifié (et reprojeté si besoin) en EPSG:4326 avant écriture, pour garantir que le fichier final est homogène même si une des sources a, par erreur, répondu dans un autre système de coordonnées.

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
| `justification` | reprise de `etape3_{dept}.csv`. |
| `validation_manuelle_commentaire` | reprise de `etape3_{dept}.csv`. |
| `statut_verification_finale` | reprise de `etape3_{dept}.csv` — `validé` / `corrigé` / `validé automatique` / `aucune occurrence trouvée`. |
| `date_traitement` | date de génération de la géométrie (Phase 1 pour `geometries_administratives`, Phase 3 pour une entité issue de `occurrences_a_georeferencer` — distincte de la `date_traitement` des étapes précédentes, conservée telle quelle par ailleurs). |

## Gestion des erreurs

Même principe que les trois étapes précédentes : aucun échec isolé (appel API Carto GPU, géométrie invalide, entité jamais géoréférencée) n'interrompt le traitement du reste du département. `preparer_geometries.py` et `synthese_geometries.py` s'arrêtent en revanche avec un message explicite si `etape3_{dept}.csv` (ou, pour la phase 3, `etape4_{dept}_a_completer.gpkg`) est introuvable — l'absence du fichier d'entrée entier ne laisse rien d'exploitable en aval, contrairement à un échec isolé sur une ligne.

## Dépendances retenues

- `requests`, `tenacity` — repris à l'identique des étapes précédentes, pour les appels à l'API Carto GPU.
- **`geopandas`** (et ses dépendances : `shapely`, `pyogrio` pour la lecture/écriture GeoPackage, `pandas` en transitif) — écart assumé par rapport au principe "pas de `pandas`" tenu aux étapes 1 à 3. Ce principe avait du sens pour des exports CSV ligne à ligne, où `pandas` n'aurait rien apporté ; il n'a plus lieu d'être ici, où la tâche (union de géométries, écriture GeoPackage multi-couches, vérification de validité OGC) est fondamentalement du traitement géospatial — le domaine que `geopandas`/`shapely` couvrent, et que la bibliothèque standard ne couvre pas du tout. Réimplémenter cette logique à la main serait un travail disproportionné pour un POC, à l'inverse de l'esprit de simplicité qui a justifié d'éviter `pandas` ailleurs.

## Point d'attention levé lors de l'implémentation

*Résolu le 17/08/2026 — laissé ici pour traçabilité plutôt que supprimé.*

Le nom exact du paramètre de filtrage de la couche `document` de l'API Carto GPU par identifiant n'avait pas été vérifié contre le swagger en vigueur au moment de la rédaction initiale de ce document. Vérification faite sur `https://apicarto.ign.fr/api/doc/gpu.yml` (spec OpenAPI réelle du module GPU) : le paramètre s'appelle bien `partition`, comme pressenti — mais son format est `<DU/PSMV>_<INSEE/SIREN>`, pas `id_gpu`. Un appel `partition={id_gpu}` a été testé en réel et renvoie 0 résultat.

`id_gpu` (l'identifiant renvoyé par `www.geoportail-urbanisme.gouv.fr/api/document`, capturé à l'étape 1) et `partition` (l'identifiant attendu par `apicarto.ign.fr/api/gpu/document`) sont donc deux identifiants distincts pour le même document, sur deux API différentes du même écosystème GPU. La correspondance entre les deux n'est stockée nulle part dans le GPU lui-même : elle se reconstruit à partir de colonnes déjà présentes dans `etape1_{dept}.csv` (`niveau_couverture`, `code_siren_epci`, `code_insee_commune`, `statut`) — voir `etape-3-conception-technique.md`, "Calcul de `partition_gpu`", pour le détail du calcul, désormais fait à l'étape 3 plutôt qu'ici. Vérifié en réel sur le PLUi et le PSMV de l'Eurométropole de Strasbourg (département 067) : chaque valeur `partition_gpu` calculée renvoie exactement une feature, dont `properties.id` correspond bien à l'`id_gpu` d'origine.

## Prochaine étape

Étape 5 — rédaction du ton des messages associés aux occurrences validées des documents significatifs, à partir de `etape4_{dept}.gpkg` et du contenu textuel de `etape3_{dept}.csv`.
