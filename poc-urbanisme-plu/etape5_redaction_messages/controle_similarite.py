"""Étape 5 — Phase 1 : garde-fou de cohérence géométrique.

Lit `etape4_{dept}.gpkg` (couche `geometries`) et repère les paires
d'occurrences dont la géométrie est à la fois d'aire équivalente et de forme
similaire, sans être reliées par `fusionne_avec_id_gpu`/
`fusionne_avec_id_occurrence` — signal qu'une fusion a peut-être été oubliée
à l'étape 4 (voir `docs/etape-5-conception-technique.md`, "Phase 1"). Jamais
bloquant : le résultat est une liste d'avertissements, jamais une correction
automatique — la fusion reste une décision humaine.

Usage :
    python -m etape5_redaction_messages.controle_similarite --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape4_{dept}.gpkg

Sortie (dans le même dossier) :
    etape5_{dept}_avertissements.csv — paires suspectes, si non vide
"""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

NATURE_ZONE_ELIGIBLE = "occurrence_locale"
# Lambert-93 : projection métrique adaptée à la métropole, nécessaire pour
# calculer des aires et des distances interprétables (le gpkg d'entrée est
# en EPSG:4326, où une distance en degrés ne veut rien dire). Un DROM
# demanderait une projection différente — hors périmètre de ce POC pour
# l'instant, comme déjà noté pour le choix du CRS de sortie de l'étape 4
# (voir etape-4-construction-geometries-diagbruit.md, "Format retenu").
CRS_METRIQUE = "EPSG:2154"
SEUIL_VARIATION_AIRE = 0.10
# Distance de Hausdorff normalisée par la racine carrée de l'aire (une
# longueur caractéristique de la géométrie, pour obtenir un score comparable
# indépendamment de la taille absolue de la zone). Seuil provisoire, jamais
# validé sur données réelles — à ajuster une fois ce script utilisé en
# pratique (voir etape-5-conception-technique.md, "Phase 1").
SEUIL_FORME_NORMALISEE = 0.10

COLONNES_AVERTISSEMENTS = [
    "id_gpu_1",
    "id_occurrence_1",
    "id_gpu_2",
    "id_occurrence_2",
    "variation_aire",
    "distance_forme_normalisee",
    "message",
]


class GpkgIntrouvable(Exception):
    pass


def _texte(valeur) -> str:
    """Normalise une valeur d'attribut en texte, en traitant `None`/`NaN`
    comme une chaîne vide plutôt que la chaîne littérale "nan" — même bug
    que celui corrigé dans `etape4_geometries/synthese_geometries.py`
    (`_texte`). Réimplémenté ici plutôt qu'importé : chaque étape du
    pipeline reste indépendante du code des autres étapes, seule la donnée
    circule entre elles (voir `etape-1-conception-technique.md`,
    "Décision 2")."""
    if valeur is None:
        return ""
    if isinstance(valeur, float) and pd.isna(valeur):
        return ""
    return str(valeur).strip()


def _cle(ligne: pd.Series) -> tuple[str, str]:
    return (_texte(ligne.get("id_gpu")), _texte(ligne.get("id_occurrence")))


def _deja_fusionnees(ligne_a: pd.Series, ligne_b: pd.Series) -> bool:
    """Vrai si les deux lignes appartiennent déjà au même groupe fusionné —
    l'une référence l'autre comme meneur, ou les deux référencent le même
    meneur (membres "frères" d'un même groupe, jamais reliés entre eux
    directement mais déjà unifiés via ce meneur commun — cas rencontré en
    pratique sur des données réelles : plusieurs membres pointant vers le
    même meneur ressortaient comme autant de paires suspectes entre eux,
    alors que la fusion les couvre déjà tous)."""
    fusion_a = (_texte(ligne_a.get("fusionne_avec_id_gpu")), _texte(ligne_a.get("fusionne_avec_id_occurrence")))
    fusion_b = (_texte(ligne_b.get("fusionne_avec_id_gpu")), _texte(ligne_b.get("fusionne_avec_id_occurrence")))
    if fusion_a == _cle(ligne_b) or fusion_b == _cle(ligne_a):
        return True
    return fusion_a != ("", "") and fusion_a == fusion_b


def _bounding_box_se_chevauchent(geom_a, geom_b) -> bool:
    """Filtre préalable, bon marché, avant le calcul de la distance de
    Hausdorff (plus coûteux) : deux géométries dont les bounding box ne se
    chevauchent pas ne peuvent de toute façon pas être géométriquement
    similaires."""
    minx_a, miny_a, maxx_a, maxy_a = geom_a.bounds
    minx_b, miny_b, maxx_b, maxy_b = geom_b.bounds
    return minx_a <= maxx_b and maxx_a >= minx_b and miny_a <= maxy_b and maxy_a >= miny_b


@dataclass
class PaireSuspecte:
    ligne_1: pd.Series
    ligne_2: pd.Series
    variation_aire: float
    distance_forme_normalisee: float


def _comparer_paire(ligne_a: pd.Series, ligne_b: pd.Series) -> PaireSuspecte | None:
    geom_a, geom_b = ligne_a.geometry, ligne_b.geometry
    if not _bounding_box_se_chevauchent(geom_a, geom_b):
        return None

    aire_a, aire_b = geom_a.area, geom_b.area
    if aire_a == 0 or aire_b == 0:
        return None
    variation_aire = abs(aire_a - aire_b) / max(aire_a, aire_b)
    if variation_aire > SEUIL_VARIATION_AIRE:
        return None

    longueur_caracteristique = max(aire_a, aire_b) ** 0.5
    distance_forme_normalisee = geom_a.hausdorff_distance(geom_b) / longueur_caracteristique
    if distance_forme_normalisee > SEUIL_FORME_NORMALISEE:
        return None

    return PaireSuspecte(ligne_a, ligne_b, variation_aire, distance_forme_normalisee)


def controler(code_departement: str, dossier_sortie: str | Path = "output") -> Path | None:
    dossier = Path(dossier_sortie)
    chemin_gpkg = dossier / f"etape4_{code_departement}.gpkg"

    if not chemin_gpkg.exists():
        raise GpkgIntrouvable(str(chemin_gpkg))

    gdf = gpd.read_file(chemin_gpkg, layer="geometries")
    if gdf.crs is not None and str(gdf.crs).upper() != CRS_METRIQUE:
        gdf = gdf.to_crs(CRS_METRIQUE)

    # Éligibles : occurrences réelles (pas les lignes de synthèse RNU/trou de
    # couverture/document non significatif), géométrie présente (un membre
    # fusionné sans géométrie propre n'a rien à comparer), nature_sonore_zone
    # renseignée (deux zones de nature sonore différente, ou toutes deux
    # vides, ne sont de toute façon jamais éligibles à une fusion — voir
    # etape-4-conception-technique.md, "Mécanisme de fusion").
    masque = (
        gdf["nature_zone"].apply(_texte).eq(NATURE_ZONE_ELIGIBLE)
        & ~gdf.geometry.isna()
        & ~gdf.geometry.is_empty
        & gdf["nature_sonore_zone"].apply(_texte).ne("")
    )
    eligibles = gdf[masque].copy()
    eligibles["_nature_sonore_zone_normalisee"] = eligibles["nature_sonore_zone"].apply(_texte)

    avertissements: list[dict] = []
    for _, groupe in eligibles.groupby("_nature_sonore_zone_normalisee"):
        for (_, ligne_a), (_, ligne_b) in itertools.combinations(groupe.iterrows(), 2):
            if _deja_fusionnees(ligne_a, ligne_b):
                continue
            resultat = _comparer_paire(ligne_a, ligne_b)
            if resultat is None:
                continue
            avertissements.append(
                {
                    "id_gpu_1": ligne_a.get("id_gpu", ""),
                    "id_occurrence_1": ligne_a.get("id_occurrence", ""),
                    "id_gpu_2": ligne_b.get("id_gpu", ""),
                    "id_occurrence_2": ligne_b.get("id_occurrence", ""),
                    "variation_aire": f"{resultat.variation_aire:.1%}",
                    "distance_forme_normalisee": f"{resultat.distance_forme_normalisee:.3f}",
                    "message": "aire et forme très proches, sans fusion déclarée — une fusion a-t-elle été oubliée ?",
                }
            )

    if not avertissements:
        print("Aucune paire suspecte détectée.")
        return None

    chemin_sortie = dossier / f"etape5_{code_departement}_avertissements.csv"
    with chemin_sortie.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES_AVERTISSEMENTS)
        writer.writeheader()
        writer.writerows(avertissements)

    print(f"{len(avertissements)} paire(s) suspecte(s), listée(s) dans {chemin_sortie}.")
    return chemin_sortie


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Étape 5, Phase 1 — repère les paires d'occurrences géométriquement proches sans fusion déclarée."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit (ex. 033, 971) — doit correspondre à un etape4_{dept}.gpkg existant.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des fichiers (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 5, phase 1 — département {args.dept}")
    try:
        controler(args.dept, dossier_sortie=args.output_dir)
    except GpkgIntrouvable as exc:
        print(f"Arrêt : etape4_{args.dept}.gpkg introuvable ({exc}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
