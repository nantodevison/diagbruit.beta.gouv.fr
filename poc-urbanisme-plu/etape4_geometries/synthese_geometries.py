"""Étape 4 — Phase 3 : synthèse des géométries.

Lit `etape4_{dept}_a_completer.gpkg` (deux couches, potentiellement éditée
manuellement dans QGIS entre-temps — Phase 2), sépare les occurrences jamais
géoréférencées, résout les fusions déclarées par l'opérateur
(`fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence`, voir "Mécanisme de
fusion" ci-dessous), applique le contrôle qualité (`controle_qualite.py`) à
chaque géométrie restante, et écrit le livrable final `etape4_{dept}.gpkg` —
le contrat pour l'étape 5/6 (voir `docs/etape-4-conception-technique.md`,
"Phase 3 — Synthèse").

Mécanisme de fusion (voir `docs/etape-4-conception-technique.md`, section
dédiée) : une occurrence peut référencer une autre occurrence "meneuse" du
même groupe via `fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence`, rempli
par l'opérateur dans QGIS. Le groupe n'est jamais fusionné géométriquement —
chaque occurrence garde sa propre ligne dans le livrable final, y compris une
occurrence membre sans géométrie propre (sa localisation est portée par le
meneur) — mais toute fusion déclarée est revérifiée ici avant d'être
acceptée : le meneur doit exister, ne pas être lui-même membre d'un autre
groupe (pas de chaînage), avoir une géométrie, et partager avec le membre
`nature_zone == "occurrence_locale"` ainsi qu'un `nature_sonore_zone`
identique et non vide. Une fusion incohérente est rejetée (erreur consignée) ;
si le membre a par ailleurs sa propre géométrie, il est tout de même
conservé comme occurrence indépendante plutôt que perdu.

Usage :
    python -m etape4_geometries.synthese_geometries --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape4_{dept}_a_completer.gpkg

Sortie (dans le même dossier) :
    etape4_{dept}.gpkg                — contrat pour l'étape 5/6
    etape4_{dept}_non_traitees.csv    — occurrences jamais géoréférencées, si non vide ;
                                         supprimé si une exécution précédente l'avait
                                         écrit mais que celle-ci n'a plus rien à y lister
    etape4_{dept}_erreurs.csv         — géométries invalides, fusions incohérentes ou de
                                         type inattendu (recalculées à neuf à chaque
                                         exécution), complété (sans les écraser) des échecs
                                         d'appel API éventuellement déjà écrits par
                                         preparer_geometries.py ; supprimé s'il ne reste
                                         plus aucune erreur à consigner
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
from .preparer_geometries import (
    COLONNES_ATTRIBUTS,
    COUCHE_A_GEOREFERENCER,
    COUCHE_ADMINISTRATIVE,
    TYPE_GEOMETRIE_SORTIE,
)

CRS_SORTIE = "EPSG:4326"
COLONNES_ERREURS = ["identifiant", "source", "message", "date_traitement"]

# Seule nature_zone éligible à une fusion : les lignes de synthèse
# (document_non_significatif / rnu / trou_de_couverture) n'ont pas de
# contenu de règle à combiner, et partagent souvent un même
# lien_web_document (ex. toutes les communes RNU pointent vers la même
# fiche Légifrance) sans rapport géographique entre elles — les y autoriser
# rendrait le contrôle automatique de cohérence (document + nature sonore)
# inefficace, faute de vérification de la localisation elle-même (jamais
# recontrôlée, voir _verifier_fusion).
NATURE_ZONE_ELIGIBLE_FUSION = "occurrence_locale"


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


def _texte(valeur) -> str:
    """Normalise une valeur d'attribut en texte. Une colonne texte vide
    relue depuis le gpkg peut revenir en `None` ou en `NaN` (float) selon
    l'outil qui a écrit le fichier — QGIS convertit couramment une chaîne
    vide en NULL à la sauvegarde d'une couche. `valeur or ""` ne suffit pas
    ici : `NaN` est *truthy* en Python (contrairement à `None`), donc
    `NaN or ""` renvoie `NaN`, pas `""` — d'où un `str(NaN)` = `"nan"`, une
    chaîne non vide, qui aurait fait passer un champ réellement vide pour
    une valeur renseignée."""
    if valeur is None:
        return ""
    if isinstance(valeur, float) and pd.isna(valeur):
        return ""
    return str(valeur).strip()


def _valeur(ligne: pd.Series, colonne: str) -> str:
    return _texte(ligne.get(colonne))


def _cle_occurrence(id_gpu, id_occurrence) -> tuple[str, str]:
    return (_texte(id_gpu), _texte(id_occurrence))


def _est_membre_fusion(ligne: pd.Series) -> bool:
    return bool(_valeur(ligne, "fusionne_avec_id_occurrence"))


def _index_par_occurrence(*gdfs: gpd.GeoDataFrame) -> dict[tuple[str, str], pd.Series]:
    """Index (id_gpu, id_occurrence) -> ligne, sur l'ensemble brut des deux
    couches (avant tout filtrage), pour que la résolution d'un meneur de
    fusion fonctionne quelle que soit la couche où il se trouve."""
    index: dict[tuple[str, str], pd.Series] = {}
    for gdf in gdfs:
        for _, ligne in gdf.iterrows():
            index[_cle_occurrence(ligne.get("id_gpu"), ligne.get("id_occurrence"))] = ligne
    return index


def _verifier_fusion(ligne: pd.Series, index_par_occurrence: dict) -> tuple[bool, str | None]:
    """Vérifie la cohérence d'une fusion déclarée par l'opérateur. Renvoie
    (autorise_geometrie_vide, erreur) :
    - si `ligne` ne déclare aucune fusion, (False, None) — comportement
      inchangé, géométrie obligatoire ;
    - si la fusion déclarée est cohérente, (True, None) — la géométrie de
      `ligne` peut être vide, sa localisation est portée par le meneur ;
    - sinon, (False, message d'erreur) — fusion rejetée."""
    if not _est_membre_fusion(ligne):
        return False, None

    cle_meneur = _cle_occurrence(ligne.get("fusionne_avec_id_gpu"), ligne.get("fusionne_avec_id_occurrence"))
    meneur = index_par_occurrence.get(cle_meneur)
    if meneur is None:
        return False, "fusion invalide : meneur introuvable"

    if _est_membre_fusion(meneur):
        return False, "fusion invalide : le meneur référencé est lui-même membre d'un groupe (chaînage non autorisé)"

    if _valeur(ligne, "nature_zone") != NATURE_ZONE_ELIGIBLE_FUSION or _valeur(meneur, "nature_zone") != NATURE_ZONE_ELIGIBLE_FUSION:
        return False, f"fusion invalide : réservée aux occurrences nature_zone = '{NATURE_ZONE_ELIGIBLE_FUSION}'"

    nature_sonore = _valeur(ligne, "nature_sonore_zone")
    if not nature_sonore:
        return False, "fusion invalide : nature_sonore_zone vide"
    if nature_sonore != _valeur(meneur, "nature_sonore_zone"):
        return False, "fusion invalide : nature_sonore_zone différente du meneur"

    geom_meneur = meneur.geometry
    if geom_meneur is None or geom_meneur.is_empty:
        return False, "fusion invalide : le meneur référencé n'a pas de géométrie (non géoréférencé)"

    return True, None


SOURCES_PHASE3 = ("controle_qualite", "fusion")


def _erreurs_existantes(chemin_erreurs: Path) -> list[dict[str, str]]:
    """Reprend les erreurs déjà écrites par preparer_geometries.py (Phase 1,
    échecs d'appel API Carto GPU) pour ne pas les perdre en réécrivant le
    même fichier avec les erreurs de contrôle qualité de cette phase — jamais
    un échec silencieusement oublié (voir etape-4-conception-technique.md,
    "Gestion des erreurs").

    Ne reprend en revanche jamais une erreur de source `controle_qualite` ou
    `fusion` : contrairement à Phase 1 (jamais relancée une fois la Phase 2
    commencée), Phase 3 est destinée à être relancée plusieurs fois — par
    exemple pendant l'ajustement itératif d'une fusion dans QGIS. Ces
    erreurs sont recalculées à neuf à chaque exécution ; les reprendre
    aussi depuis le fichier précédent les dupliquerait à chaque relance, et
    ferait resurgir indéfiniment une erreur déjà corrigée entre-temps."""
    if not chemin_erreurs.exists():
        return []
    with chemin_erreurs.open(encoding="utf-8-sig", newline="") as fichier:
        return [ligne for ligne in csv.DictReader(fichier) if ligne.get("source") not in SOURCES_PHASE3]


def synthetiser(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_a_completer = dossier / f"etape4_{code_departement}_a_completer.gpkg"

    if not chemin_a_completer.exists():
        raise GpkgIntrouvable(str(chemin_a_completer))

    geodf_administratives = _lire_couche(chemin_a_completer, COUCHE_ADMINISTRATIVE)
    geodf_a_georeferencer = _lire_couche(chemin_a_completer, COUCHE_A_GEOREFERENCER)

    # Index construit sur les deux couches brutes, avant tout filtrage : un
    # meneur de fusion doit être trouvable quel que soit son sort ultérieur
    # (exclu pour géométrie vide, en erreur...), voir _verifier_fusion.
    index_par_occurrence = _index_par_occurrence(geodf_administratives, geodf_a_georeferencer)

    # Une géométrie vide n'est routée vers _non_traitees.csv que si
    # l'occurrence ne déclare aucune fusion : membre d'un groupe fusionné,
    # elle est légitimement sans géométrie propre et rejoint le lot
    # géoréférencé pour vérification de cohérence de la fusion (voir
    # _verifier_fusion, appelé plus bas pour chaque ligne).
    membre_fusion = geodf_a_georeferencer["fusionne_avec_id_occurrence"].fillna("").astype(str).str.strip() != ""
    geometrie_vide = geodf_a_georeferencer.geometry.isna() | geodf_a_georeferencer.geometry.is_empty
    non_traitees = geodf_a_georeferencer[geometrie_vide & ~membre_fusion]
    georeferencees = geodf_a_georeferencer[~geometrie_vide | membre_fusion]

    date_traitement = date.today().isoformat()
    chemin_erreurs = dossier / f"etape4_{code_departement}_erreurs.csv"
    erreurs = _erreurs_existantes(chemin_erreurs)

    lignes_validees: list[dict] = []
    geometries_validees = []
    for gdf in (geodf_administratives, georeferencees):
        for _, ligne in gdf.iterrows():
            autorise_vide, erreur_fusion = _verifier_fusion(ligne, index_par_occurrence)
            if erreur_fusion:
                erreurs.append(
                    {
                        "identifiant": _identifiant(ligne),
                        "source": "fusion",
                        "message": erreur_fusion,
                        "date_traitement": date_traitement,
                    }
                )
                # Une fusion rejetée ne fait perdre la ligne que si elle n'a,
                # par ailleurs, pas sa propre géométrie pour exister comme
                # occurrence indépendante.
                if ligne.geometry is None or ligne.geometry.is_empty:
                    continue

            geom_corrigee, erreur = controler_geometrie(ligne.geometry, autorise_vide=autorise_vide)
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

    # synthese_geometries.py est amené à être relancé plusieurs fois (voir
    # _erreurs_existantes) : un fichier _non_traitees.csv/_erreurs.csv d'une
    # exécution précédente, devenu vide à celle-ci, est supprimé plutôt que
    # laissé tel quel — sinon son contenu, périmé, continuerait de signaler
    # un problème déjà résolu entre-temps.
    chemin_non_traitees = dossier / f"etape4_{code_departement}_non_traitees.csv"
    if not non_traitees.empty:
        non_traitees[COLONNES_ATTRIBUTS].to_csv(chemin_non_traitees, index=False, encoding="utf-8-sig")
        print(
            f"Attention : {len(non_traitees)} occurrence(s) jamais géoréférencée(s) dans QGIS, "
            f"listée(s) dans {chemin_non_traitees}. Exclue(s) de la sortie finale — à reprendre "
            "avant de considérer le département terminé."
        )
    elif chemin_non_traitees.exists():
        chemin_non_traitees.unlink()

    if erreurs:
        with chemin_erreurs.open("w", newline="", encoding="utf-8-sig") as fichier:
            writer = csv.DictWriter(fichier, fieldnames=COLONNES_ERREURS)
            writer.writeheader()
            writer.writerows(erreurs)
        print(f"{len(erreurs)} erreur(s) au total (récupération + contrôle qualité), listée(s) dans {chemin_erreurs}.")
    elif chemin_erreurs.exists():
        chemin_erreurs.unlink()

    if lignes_validees:
        geodf_final = gpd.GeoDataFrame(lignes_validees, geometry=geometries_validees, crs=CRS_SORTIE)
    else:
        geodf_final = gpd.GeoDataFrame(columns=COLONNES_ATTRIBUTS, geometry=[], crs=CRS_SORTIE)

    chemin_sortie = dossier / f"etape4_{code_departement}.gpkg"
    geodf_final.to_file(
        chemin_sortie,
        layer="geometries",
        driver="GPKG",
        # Un membre de fusion valide écrit une géométrie None (voir
        # _verifier_fusion / controle_qualite) : sans geometry_type explicite,
        # pyogrio ne peut pas déduire le type d'une colonne contenant des
        # None et GDAL écrirait la couche sans CRS associé — même situation,
        # et même remède, qu'à la Phase 1 (preparer_geometries.py).
        geometry_type=TYPE_GEOMETRIE_SORTIE,
        promote_to_multi=True,
    )

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
