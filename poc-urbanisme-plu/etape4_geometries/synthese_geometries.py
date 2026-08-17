"""Étape 4 — Phase 3 : synthèse des géométries.

Lit `etape4_{dept}_a_completer.gpkg` (deux couches, potentiellement éditée
manuellement dans QGIS entre-temps — Phase 2), sépare les occurrences jamais
géoréférencées, applique le contrôle qualité (`controle_qualite.py`) à
chaque géométrie restante, et écrit le livrable final `etape4_{dept}.gpkg` —
le contrat pour l'étape 5/6 (voir `docs/etape-4-conception-technique.md`,
"Phase 3 — Synthèse").

Usage :
    python -m etape4_geometries.synthese_geometries --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape4_{dept}_a_completer.gpkg

Sortie (dans le même dossier) :
    etape4_{dept}.gpkg                — contrat pour l'étape 5/6
    etape4_{dept}_non_traitees.csv    — occurrences jamais géoréférencées, si non vide
    etape4_{dept}_erreurs.csv         — géométries invalides ou de type inattendu, si
                                         non vide (complète, sans l'écraser, le fichier
                                         éventuellement déjà écrit par preparer_geometries.py)
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .controle_qualite import controler_geometrie
from .preparer_geometries import COLONNES_ATTRIBUTS, COUCHE_A_GEOREFERENCER, COUCHE_ADMINISTRATIVE

CRS_SORTIE = "EPSG:4326"
COLONNES_ERREURS = ["identifiant", "source", "message", "date_traitement"]


class GpkgIntrouvable(Exception):
    pass


def _lire_couche(chemin: Path, couche: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(chemin, layer=couche)
    # Défensif : Phase 1 écrit déjà en EPSG:4326, et l'édition d'entités
    # existantes dans QGIS (Phase 2) ne change normalement pas le CRS de la
    # couche — mais le contrat garantit un fichier final homogène quoi qu'il
    # arrive en amont, voir etape-4-conception-technique.md, Phase 3.
    if gdf.crs is not None and str(gdf.crs).upper() != CRS_SORTIE:
        gdf = gdf.to_crs(CRS_SORTIE)
    return gdf


def _identifiant(ligne: pd.Series) -> str:
    return str(ligne.get("id_occurrence") or ligne.get("id_geometrie") or "(géométrie inconnue)")


def _erreurs_existantes(chemin_erreurs: Path) -> list[dict[str, str]]:
    """Reprend les erreurs déjà écrites par preparer_geometries.py (Phase 1,
    échecs d'appel API Carto GPU) pour ne pas les perdre en réécrivant le
    même fichier avec les erreurs de contrôle qualité de cette phase — jamais
    un échec silencieusement oublié (voir etape-4-conception-technique.md,
    "Gestion des erreurs")."""
    if not chemin_erreurs.exists():
        return []
    with chemin_erreurs.open(encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier))


def synthetiser(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_a_completer = dossier / f"etape4_{code_departement}_a_completer.gpkg"

    if not chemin_a_completer.exists():
        raise GpkgIntrouvable(str(chemin_a_completer))

    geodf_administratives = _lire_couche(chemin_a_completer, COUCHE_ADMINISTRATIVE)
    geodf_a_georeferencer = _lire_couche(chemin_a_completer, COUCHE_A_GEOREFERENCER)

    geometrie_vide = geodf_a_georeferencer.geometry.isna() | geodf_a_georeferencer.geometry.is_empty
    non_traitees = geodf_a_georeferencer[geometrie_vide]
    georeferencees = geodf_a_georeferencer[~geometrie_vide]

    date_traitement = date.today().isoformat()
    chemin_erreurs = dossier / f"etape4_{code_departement}_erreurs.csv"
    erreurs = _erreurs_existantes(chemin_erreurs)

    lignes_validees: list[dict] = []
    geometries_validees = []
    for gdf in (geodf_administratives, georeferencees):
        for _, ligne in gdf.iterrows():
            geom_corrigee, erreur = controler_geometrie(ligne.geometry)
            if erreur:
                erreurs.append(
                    {
                        "identifiant": _identifiant(ligne),
                        "source": "controle_qualite",
                        "message": erreur,
                        "date_traitement": date_traitement,
                    }
                )
                continue
            lignes_validees.append({colonne: ligne.get(colonne, "") for colonne in COLONNES_ATTRIBUTS})
            geometries_validees.append(geom_corrigee)

    if not non_traitees.empty:
        chemin_non_traitees = dossier / f"etape4_{code_departement}_non_traitees.csv"
        non_traitees[COLONNES_ATTRIBUTS].to_csv(chemin_non_traitees, index=False, encoding="utf-8-sig")
        print(
            f"Attention : {len(non_traitees)} occurrence(s) jamais géoréférencée(s) dans QGIS, "
            f"listée(s) dans {chemin_non_traitees}. Exclue(s) de la sortie finale — à reprendre "
            "avant de considérer le département terminé."
        )

    if erreurs:
        with chemin_erreurs.open("w", newline="", encoding="utf-8-sig") as fichier:
            writer = csv.DictWriter(fichier, fieldnames=COLONNES_ERREURS)
            writer.writeheader()
            writer.writerows(erreurs)
        print(f"{len(erreurs)} erreur(s) au total (récupération + contrôle qualité), listée(s) dans {chemin_erreurs}.")

    if lignes_validees:
        geodf_final = gpd.GeoDataFrame(lignes_validees, geometry=geometries_validees, crs=CRS_SORTIE)
    else:
        geodf_final = gpd.GeoDataFrame(columns=COLONNES_ATTRIBUTS, geometry=[], crs=CRS_SORTIE)

    chemin_sortie = dossier / f"etape4_{code_departement}.gpkg"
    geodf_final.to_file(chemin_sortie, layer="geometries", driver="GPKG")

    print(f"{len(geodf_final)} géométrie(s) validée(s) écrite(s) dans {chemin_sortie}.")
    return chemin_sortie


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fusionne et contrôle la qualité des géométries de l'étape 4, écrit le livrable final."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit (ex. 033, 971) — doit correspondre à un etape4_{dept}_a_completer.gpkg existant.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des fichiers (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 4, phase 3 — département {args.dept}")
    try:
        synthetiser(args.dept, dossier_sortie=args.output_dir)
    except GpkgIntrouvable as exc:
        print(f"Arrêt : etape4_{args.dept}_a_completer.gpkg introuvable ({exc}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
