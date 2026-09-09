"""Étape 4 — aide partagée : récupération de géométrie via l'API Carto GPU
(couches `document`, `municipality` et `zone-urba`), voir
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

Ajouté le 09/09/2026 : récupération automatique de la géométrie d'une zone
réglementaire (ex. "UA"), via la couche `zone-urba` de la même API Carto GPU
— voir `docs/etape-4-construction-geometries-diagbruit.md`, "Sources de
géométrie". Point vérifié en réel avant implémentation : la couche accepte
bien `partition` (même format que `document`) mais **ignore silencieusement**
un paramètre `libelle` — un appel `zone-urba?partition=...&libelle=N1`
renvoie exactement les mêmes résultats (et le même `numberReturned`) qu'un
appel sans `libelle`, quelle que soit sa valeur, y compris une valeur qui
n'existe dans aucune zone. Le filtrage par code de zone se fait donc
entièrement côté client, sur l'ensemble des zones de la partition (`libelle`,
le code court affiché sur le plan — ex. "UA", "N1", "1AUh" — et `typezone`,
la catégorie générale U/AUx/A/N), après un unique appel par `partition_gpu`
(comme pour `document`) plutôt qu'un appel par occurrence.
"""

from __future__ import annotations

import re
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


def recuperer_zones_urba(partition_gpu: str) -> tuple[list[dict], str | None]:
    """Récupère l'ensemble des zones de la couche `zone-urba` pour une
    partition (un seul appel par `partition_gpu`, jamais un par occurrence —
    voir docstring du module : `libelle` n'est pas filtrable côté serveur).
    Renvoie la liste brute des features GeoJSON (à passer à
    `trouver_geometrie_zone`) et un message d'erreur (None si l'appel a
    réussi, y compris si la partition n'a aucune zone numérisée dans le
    GPU — liste vide, pas une erreur en soi)."""
    try:
        response = _get(f"{API_CARTO_GPU}/zone-urba", {"partition": partition_gpu})
    except requests.exceptions.RequestException as exc:
        return [], f"appel zone-urba indisponible : {exc}"
    return response.json().get("features", []), None


def _normaliser_code_zone(code: str) -> str:
    """Espaces retirés, casse uniforme — suffisant pour absorber l'essentiel
    des variations de saisie ("UA" / "ua" / "U A"). Ne tente PAS de
    normaliser l'ambiguïté chiffre/romain des phases de zone AU ("1AUh" dans
    un règlement écrit vs "IAUB" dans la couche zone-urba, par exemple) :
    une correspondance non trouvée retombe simplement sur le tracé manuel
    (voir preparer_geometries.py), jamais une erreur bloquante — voir
    `docs/ameliorations-identifiees.md` pour cette piste d'amélioration si
    le taux de correspondance s'avère trop faible à l'usage réel."""
    return re.sub(r"\s+", "", code).strip().upper()


def trouver_geometrie_zone(features: list[dict], code_zone: str) -> ResultatGeometrie:
    """Cherche, parmi les zones déjà récupérées d'une partition (voir
    `recuperer_zones_urba`), celle(s) dont `libelle` correspond exactement
    (comparaison normalisée, voir `_normaliser_code_zone`) au code cité dans
    le règlement, et unit leurs géométries en une seule — même logique que
    `_unir_features` pour `document` : un même code de zone peut apparaître
    en plusieurs polygones disjoints dans une même partition (plusieurs
    communes d'un même PLUi partageant le même zonage)."""
    code_normalise = _normaliser_code_zone(code_zone)
    if not code_normalise:
        return ResultatGeometrie(geometrie_geojson=None, erreur="aucun code de zone à rechercher")

    correspondances = [
        f
        for f in features
        if _normaliser_code_zone(f.get("properties", {}).get("libelle") or "") == code_normalise
    ]
    if not correspondances:
        return ResultatGeometrie(
            geometrie_geojson=None, erreur=f"zone « {code_zone} » introuvable dans le zonage GPU de la partition"
        )
    return ResultatGeometrie(geometrie_geojson=_unir_features(correspondances), erreur=None)
