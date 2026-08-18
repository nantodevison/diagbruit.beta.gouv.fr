"""Étape 4 — Phase 1 : préparation des géométries.

Lit `etape3_{dept}.csv` (module `csv` de la bibliothèque standard,
`encoding="utf-8-sig"`, cohérent avec le reste du pipeline) et écrit
`etape4_{dept}_a_completer.gpkg`, avec deux couches de structure identique
(voir `docs/etape-4-conception-technique.md`, "Contrat de données") :

- `geometries_administratives` — remplie automatiquement (documents non
  significatifs, communes RNU, trous de couverture, occurrences à portée
  administrative), via `sources_gpu.py`.
- `occurrences_a_georeferencer` — une ligne par occurrence à portée
  `zone_specifique`, tous les attributs déjà remplis, géométrie laissée
  vide pour tracé manuel dans QGIS (Phase 2).

Usage :
    python -m etape4_geometries.preparer_geometries --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape3_{dept}.csv

Sortie (dans le même dossier) :
    etape4_{dept}_a_completer.gpkg — à ouvrir dans QGIS pour la Phase 2
    etape4_{dept}_erreurs.csv      — échecs d'appel API Carto GPU, si non vide
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import geopandas as gpd
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from .sources_gpu import ResultatGeometrie, recuperer_geometrie_commune, recuperer_geometrie_document

PORTEE_ZONE_SPECIFIQUE = "zone_specifique"
CRS_SORTIE = "EPSG:4326"
# GeoPackage n'autorise qu'un seul type de géométrie déclaré par couche
# (gpkg_geometry_columns). On force "MultiPolygon" pour les deux couches :
# ça couvre aussi bien une commune simple (un seul polygone) qu'un document
# GPU renvoyé en plusieurs parties disjointes (voir _unir_features). Sans ce
# paramètre, pyogrio ne peut pas déduire le type d'une couche dont toutes les
# géométries sont vides — occurrences_a_georeferencer au moment de sa
# création — et GDAL l'écrit alors comme une simple table attributaire, sans
# CRS associé : c'est ce que QGIS affichait comme "couche non géoréférencée".
TYPE_GEOMETRIE_SORTIE = "MultiPolygon"

COUCHE_ADMINISTRATIVE = "geometries_administratives"
COUCHE_A_GEOREFERENCER = "occurrences_a_georeferencer"

# Ordre des colonnes d'attributs, identique dans les deux couches — voir
# etape-4-conception-technique.md, "Contrat de données". `id_geometrie` est
# ajoutée par ce module, toutes les autres sont reprises de etape3_{dept}.csv.
COLONNES_ATTRIBUTS = [
    "id_geometrie",
    "id_gpu",
    "id_occurrence",
    "code_insee_commune",
    "nature_zone",
    "portee_geometrique",
    "nom_document",
    "communes",
    "type_piece_source",
    "reference_type",
    "reference_precise",
    "lien_web_document",
    "zone_reglementaire_mentionnee",
    "justification",
    "validation_manuelle_commentaire",
    "statut_verification_finale",
    "date_traitement",
]

COLONNES_ERREURS = ["identifiant", "source", "message", "date_traitement"]


class Etape3CsvIntrouvable(Exception):
    pass


@dataclass
class ErreurGeometrie:
    identifiant: str
    source: str  # "document", "municipality" ou "aucune_source"
    message: str


def _lire_etape3(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier))


def _attributs(ligne: dict[str, str], id_geometrie: int, date_traitement: str) -> dict:
    return {
        "id_geometrie": id_geometrie,
        "id_gpu": ligne.get("id_gpu", ""),
        "id_occurrence": ligne.get("id_occurrence", ""),
        "code_insee_commune": ligne.get("code_insee_commune", ""),
        "nature_zone": ligne.get("nature_zone", ""),
        "portee_geometrique": ligne.get("portee_geometrique", ""),
        "nom_document": ligne.get("nom_document", ""),
        "communes": ligne.get("communes", ""),
        "type_piece_source": ligne.get("type_piece_source", ""),
        "reference_type": ligne.get("reference_type", ""),
        "reference_precise": ligne.get("reference_precise", ""),
        "lien_web_document": ligne.get("lien_web_document", ""),
        "zone_reglementaire_mentionnee": ligne.get("zone_reglementaire_mentionnee", ""),
        "justification": ligne.get("justification", ""),
        "validation_manuelle_commentaire": ligne.get("validation_manuelle_commentaire", ""),
        "statut_verification_finale": ligne.get("statut_verification_finale", ""),
        "date_traitement": date_traitement,
    }


def _identifiant_ligne(ligne: dict[str, str]) -> str:
    """Identifiant le plus parlant disponible pour une ligne sans
    partition_gpu ni code_insee_commune (cas normalement impossible, voir
    etape-3-conception-technique.md, contrat de données)."""
    return ligne.get("id_occurrence") or ligne.get("nom_document") or ligne.get("communes") or "(ligne inconnue)"


def _resoudre_geometries_administratives(
    lignes_administratives: list[dict[str, str]],
) -> tuple[dict[str, ResultatGeometrie], dict[str, ResultatGeometrie], list[ErreurGeometrie]]:
    """Récupère, une seule fois par valeur distincte, la géométrie de chaque
    document (`partition_gpu`) et de chaque commune (`code_insee_commune`,
    pour RNU/trou de couverture) référencés par les lignes à géométrie
    automatique — même logique de dédoublonnage qu'aux étapes précédentes
    (EPCI à l'étape 1, résolution de pièces à l'étape 2)."""
    erreurs: list[ErreurGeometrie] = []

    partitions_uniques = sorted({l["partition_gpu"] for l in lignes_administratives if l.get("partition_gpu")})
    geometries_par_partition: dict[str, ResultatGeometrie] = {}
    for partition_gpu in partitions_uniques:
        resultat = recuperer_geometrie_document(partition_gpu)
        geometries_par_partition[partition_gpu] = resultat
        if resultat.erreur:
            erreurs.append(ErreurGeometrie(partition_gpu, "document", resultat.erreur))

    communes_uniques = sorted(
        {
            l["code_insee_commune"]
            for l in lignes_administratives
            if not l.get("partition_gpu") and l.get("code_insee_commune")
        }
    )
    geometries_par_commune: dict[str, ResultatGeometrie] = {}
    for code_insee in communes_uniques:
        resultat = recuperer_geometrie_commune(code_insee)
        geometries_par_commune[code_insee] = resultat
        if resultat.erreur:
            erreurs.append(ErreurGeometrie(code_insee, "municipality", resultat.erreur))

    return geometries_par_partition, geometries_par_commune, erreurs


def _construire_geodataframe(
    lignes_attributs: list[dict], geometries: list[BaseGeometry | None]
) -> gpd.GeoDataFrame:
    if not lignes_attributs:
        return gpd.GeoDataFrame(columns=COLONNES_ATTRIBUTS, geometry=[], crs=CRS_SORTIE)
    return gpd.GeoDataFrame(lignes_attributs, geometry=geometries, crs=CRS_SORTIE)


def preparer(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_etape3 = dossier / f"etape3_{code_departement}.csv"

    if not chemin_etape3.exists():
        raise Etape3CsvIntrouvable(str(chemin_etape3))

    lignes = _lire_etape3(chemin_etape3)
    date_traitement = date.today().isoformat()

    lignes_a_georeferencer_brutes = [l for l in lignes if l.get("portee_geometrique") == PORTEE_ZONE_SPECIFIQUE]
    lignes_administratives_brutes = [l for l in lignes if l.get("portee_geometrique") != PORTEE_ZONE_SPECIFIQUE]

    geometries_par_partition, geometries_par_commune, erreurs = _resoudre_geometries_administratives(
        lignes_administratives_brutes
    )

    compteur_id = 0
    attributs_admin: list[dict] = []
    geometries_admin: list[BaseGeometry] = []

    for ligne in lignes_administratives_brutes:
        partition_gpu = ligne.get("partition_gpu", "")
        code_insee = ligne.get("code_insee_commune", "")

        if partition_gpu:
            resultat = geometries_par_partition.get(partition_gpu)
        elif code_insee:
            resultat = geometries_par_commune.get(code_insee)
        else:
            erreurs.append(
                ErreurGeometrie(_identifiant_ligne(ligne), "aucune_source", "ni partition_gpu ni code_insee_commune renseignés")
            )
            continue

        # resultat est toujours résolu ici (déjà interrogé, avec ou sans
        # erreur, dans _resoudre_geometries_administratives) : une ligne dont
        # la source de géométrie a échoué est exclue du GeoPackage — son
        # échec est déjà consigné dans erreurs, pas la peine de le dupliquer.
        if resultat.erreur:
            continue

        compteur_id += 1
        attributs_admin.append(_attributs(ligne, compteur_id, date_traitement))
        geometries_admin.append(shape(resultat.geometrie_geojson))

    attributs_a_georeferencer: list[dict] = []
    for ligne in lignes_a_georeferencer_brutes:
        compteur_id += 1
        attributs_a_georeferencer.append(_attributs(ligne, compteur_id, date_traitement))

    geodf_administratives = _construire_geodataframe(attributs_admin, geometries_admin)
    geodf_a_georeferencer = _construire_geodataframe(
        attributs_a_georeferencer, [None] * len(attributs_a_georeferencer)
    )

    chemin_sortie = dossier / f"etape4_{code_departement}_a_completer.gpkg"
    geodf_administratives.to_file(
        chemin_sortie,
        layer=COUCHE_ADMINISTRATIVE,
        driver="GPKG",
        mode="w",
        geometry_type=TYPE_GEOMETRIE_SORTIE,
        # promote_to_multi : au cas où une géométrie de cette couche serait un
        # Polygon simple plutôt qu'un MultiPolygon — GeoPackage n'accepte pas
        # un mélange des deux types dans une même couche.
        promote_to_multi=True,
    )
    geodf_a_georeferencer.to_file(
        chemin_sortie,
        layer=COUCHE_A_GEOREFERENCER,
        driver="GPKG",
        mode="a",
        geometry_type=TYPE_GEOMETRIE_SORTIE,
        promote_to_multi=True,
    )

    if erreurs:
        chemin_erreurs = dossier / f"etape4_{code_departement}_erreurs.csv"
        with chemin_erreurs.open("w", newline="", encoding="utf-8-sig") as fichier:
            writer = csv.DictWriter(fichier, fieldnames=COLONNES_ERREURS)
            writer.writeheader()
            writer.writerows(
                {
                    "identifiant": erreur.identifiant,
                    "source": erreur.source,
                    "message": erreur.message,
                    "date_traitement": date_traitement,
                }
                for erreur in erreurs
            )
        print(f"{len(erreurs)} erreur(s) de récupération de géométrie, listée(s) dans {chemin_erreurs}.")

    print(
        f"{len(attributs_admin)} géométrie(s) automatique(s) écrite(s) dans la couche "
        f"'{COUCHE_ADMINISTRATIVE}', {len(attributs_a_georeferencer)} occurrence(s) à tracer "
        f"manuellement dans la couche '{COUCHE_A_GEOREFERENCER}' de {chemin_sortie}."
    )
    print("Ouvrez ce fichier dans QGIS pour la Phase 2 (tracé manuel).")
    return chemin_sortie


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prépare les géométries automatiques et le gabarit de tracé manuel de l'étape 4."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit (ex. 033, 971) — doit correspondre à un etape3_{dept}.csv existant.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des fichiers (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 4, phase 1 — département {args.dept}")
    try:
        preparer(args.dept, dossier_sortie=args.output_dir)
    except Etape3CsvIntrouvable as exc:
        print(f"Arrêt : etape3_{args.dept}.csv introuvable ({exc}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
