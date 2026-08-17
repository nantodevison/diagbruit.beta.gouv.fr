"""Étape 4 — aide partagée : contrôle qualité d'une géométrie avant écriture
dans le livrable final (`etape4_{dept}.gpkg`), voir
`docs/etape-4-conception-technique.md`, "Contrôle qualité" et
`docs/etape-4-construction-geometries-diagbruit.md`, "Contrôle qualité".

Trois vérifications systématiques : c'est bien un polygone ou un
multi-polygone (pas un point, pas une ligne, jamais une géométrie vide),
elle est valide au sens du standard OGC, et elle est bien exprimée dans le
CRS attendu (WGS84 — vérifié en amont par les appelants, pas ici, voir
`synthese_geometries.py`).

Écart d'implémentation par rapport au cadrage : le cadrage illustre
`controler_geometrie` prenant un GeoJSON en entrée (`shape(geometrie_geojson)`
en première ligne). En pratique, les deux appelants (`preparer_geometries.py`
et `synthese_geometries.py`) manipulent déjà des géométries Shapely via
`geopandas` — cette fonction prend donc directement une géométrie Shapely
(ou `None`), sans étape de conversion GeoJSON intermédiaire inutile.
"""

from __future__ import annotations

from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

TYPES_AUTORISES = ("Polygon", "MultiPolygon")


def controler_geometrie(geom: BaseGeometry | None) -> tuple[BaseGeometry | None, str | None]:
    """Renvoie (geometrie_corrigee, erreur). `erreur` est `None` si tout est
    en ordre, auquel cas `geometrie_corrigee` est la géométrie à écrire dans
    le livrable final (identique à `geom`, ou corrigée par `make_valid`)."""
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
