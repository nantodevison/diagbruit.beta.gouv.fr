"""Étape 4 — aide partagée : récupération de géométrie via l'API Carto GPU
(couches `document` et `municipality`), voir
`docs/etape-4-conception-technique.md`, "Sources de géométrie" et "Phase 1".

Réutilise l'API Carto GPU déjà appelée à l'étape 1
(`etape1_identification/documents_urbanisme.py`, couche `municipality`) plutôt
que d'intégrer une nouvelle source (ex. Admin Express) — voir
`docs/etape-4-construction-geometries-diagbruit.md`, "Sources de géométrie".

Point réglé lors de l'implémentation (17/08/2026), voir
`docs/etape-4-conception-technique.md`, "Point d'attention levé lors de
l'implémentation" : le paramètre de filtrage de la couche `document` est bien
`partition`, mais il attend un format `<DU/PSMV>_<INSEE/SIREN>`, pas
l'`id_gpu` du reste du pipeline. Cette valeur (`partition_gpu`) est
précalculée à l'étape 3 (`etape3_validation_manuelle/synthese_finale.py`) et
simplement reprise ici.
"""

from __future__ import annotations

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
def _get(url: str, params: dict) -> requests.Response:
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response


def _unir_features(features: list[dict]) -> dict:
    """Union géométrique de plusieurs features en une seule géométrie
    GeoJSON — un document peut être renvoyé en plusieurs entités adjacentes
    plutôt qu'une seule (voir etape-4-conception-technique.md, Phase 1)."""
    geometries = [shape(feature["geometry"]) for feature in features]
    return mapping(unary_union(geometries))


def recuperer_geometrie_document(partition_gpu: str) -> ResultatGeometrie:
    """Périmètre d'un document d'urbanisme, via la couche `document` de
    l'API Carto GPU, filtrée par `partition_gpu` (précalculé à l'étape 3).

    Vérifié en réel le 17/08/2026 sur le PLUi et le PSMV de l'Eurométropole
    de Strasbourg : chaque appel renvoie exactement une feature, dont
    `properties.id` correspond bien à l'`id_gpu` d'origine.
    """
    try:
        response = _get(f"{API_CARTO_GPU}/document", {"partition": partition_gpu})
    except requests.exceptions.RequestException as exc:
        return ResultatGeometrie(geometrie_geojson=None, erreur=f"appel document indisponible : {exc}")

    features = response.json().get("features", [])
    if not features:
        return ResultatGeometrie(geometrie_geojson=None, erreur="aucune géométrie renvoyée par le GPU")
    return ResultatGeometrie(geometrie_geojson=_unir_features(features), erreur=None)


def recuperer_geometrie_commune(code_insee_commune: str) -> ResultatGeometrie:
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
