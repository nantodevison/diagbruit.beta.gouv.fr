"""Étape 5 — Phase 4 : synthèse finale des messages.

Lit `etape5_{dept}_a_completer.gpkg` (géométries + messages natifs du LLM,
Phase 2) et le plus récent export de `outil_validation.html`
(`etape5_export_syntheses_{horodatage}.csv`, Phase 3 — voir
`docs/etape-5-conception-technique.md`, "Phase 3"), résout la valeur finale
de chaque message (corrigée si `synthese_corrigee`, sinon native), et écrit
le livrable `etape5_{dept}.gpkg` — le contrat pour l'étape 6.

Les corrections d'occurrence (`etape5_export_occurrences_*.csv`) ne sont
jamais lues ici : par décision (voir `etape-5-conception-technique.md`,
"Correction humaine : natif + correction, jamais de cascade"), elles
n'influencent jamais la synthèse du même run — seulement archivées pour un
usage futur (exemples de recalibrage du prompt).

Usage :
    python -m etape5_redaction_messages.synthese_messages --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape5_{dept}_a_completer.gpkg
    etape5_export_syntheses_{horodatage}.csv — le plus récent, produit par outil_validation.html

Sortie (dans le même dossier) :
    etape5_{dept}.gpkg — contrat pour l'étape 6 (couche unique "messages")
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

# Même motif que synthese_finale.py à l'étape 3
# (etape3_validation_manuelle/synthese_finale.py, PATRON_EXPORT_OUTIL) :
# chaque export d'outil_validation.html produit un nouveau fichier plutôt que
# d'écraser le précédent, d'où la nécessité de repérer le plus récent.
PATRON_EXPORT_SYNTHESES = re.compile(r"^etape5_export_syntheses_(\d{8}_\d{6})\.csv$")

COLONNES_FINALES = [
    "id_geometrie",
    "id_gpu",
    "id_occurrence",
    "message_synthese",
    "message_synthese_llm",
    "synthese_corrigee",
    "message_synthese_corrige",
    "validation_message_commentaire",
]


class GpkgIntrouvable(Exception):
    pass


class ExportIntrouvable(Exception):
    pass


def _texte(valeur) -> str:
    """Même normalisation NaN-safe que le reste du pipeline — voir
    `etape4_geometries/synthese_geometries.py`, `_texte()`. Réimplémentée ici
    plutôt qu'importée : chaque étape reste indépendante du code des autres
    (voir `etape-1-conception-technique.md`, "Décision 2")."""
    if valeur is None:
        return ""
    if isinstance(valeur, float) and pd.isna(valeur):
        return ""
    return str(valeur).strip()


def _dernier_export(dossier: Path) -> Path:
    """Retourne le fichier `etape5_export_syntheses_{horodatage}.csv` le plus
    récent du dossier — même logique que `_dernier_export` à l'étape 3
    (`etape3_validation_manuelle/synthese_finale.py`) : l'horodatage encodé
    dans le nom sert de clé de tri, pas la date de modification du fichier."""
    candidats = sorted(
        (correspondance.group(1), chemin)
        for chemin in dossier.glob("etape5_export_syntheses_*.csv")
        if (correspondance := PATRON_EXPORT_SYNTHESES.match(chemin.name))
    )
    if not candidats:
        raise ExportIntrouvable(
            f"{dossier / 'etape5_export_syntheses_*.csv'} (aucun export de outil_validation.html trouvé)"
        )
    return candidats[-1][1]


def _lire_export(chemin: Path) -> dict[str, dict[str, str]]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return {ligne["id_geometrie"]: ligne for ligne in csv.DictReader(fichier) if ligne.get("id_geometrie")}


def synthetiser(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_a_completer = dossier / f"etape5_{code_departement}_a_completer.gpkg"

    if not chemin_a_completer.exists():
        raise GpkgIntrouvable(str(chemin_a_completer))

    gdf = gpd.read_file(chemin_a_completer, layer="syntheses")
    chemin_export = _dernier_export(dossier)
    export = _lire_export(chemin_export)

    lignes_finales: list[dict] = []
    geometries_finales = []
    anomalies: list[str] = []

    for _, ligne in gdf.iterrows():
        id_geometrie = str(ligne.get("id_geometrie", ""))
        ligne_export = export.get(id_geometrie)
        if ligne_export is None:
            # Une géométrie de la Phase 2 absente de l'export signale un
            # désynchronisme (ex. Phase 2 relancée après l'export) — jamais
            # supposée sans conséquence, ligne exclue plutôt qu'assemblée à
            # partir de données possiblement obsolètes.
            anomalies.append(id_geometrie)
            continue

        corrigee = _texte(ligne_export.get("synthese_corrigee")) in ("True", "true")
        message_corrige = _texte(ligne_export.get("message_synthese_corrige"))
        message_natif = ligne.get("message_synthese_llm", "")
        message_final = message_corrige if corrigee and message_corrige else message_natif

        lignes_finales.append(
            {
                "id_geometrie": id_geometrie,
                "id_gpu": ligne.get("id_gpu", ""),
                "id_occurrence": ligne.get("id_occurrence", ""),
                "message_synthese": message_final,
                "message_synthese_llm": message_natif,
                "synthese_corrigee": "True" if corrigee else "False",
                "message_synthese_corrige": message_corrige,
                "validation_message_commentaire": _texte(ligne_export.get("validation_message_commentaire")),
            }
        )
        geometries_finales.append(ligne.geometry)

    if anomalies:
        print(
            f"Attention : {len(anomalies)} géométrie(s) de etape5_{code_departement}_a_completer.gpkg "
            f"absente(s) de {chemin_export.name} (fichier désynchronisé ?) — exclue(s) de la sortie finale : "
            f"{', '.join(anomalies)}",
            file=sys.stderr,
        )

    if lignes_finales:
        geodf_final = gpd.GeoDataFrame(lignes_finales, geometry=geometries_finales, crs=gdf.crs)
    else:
        geodf_final = gpd.GeoDataFrame(columns=COLONNES_FINALES, geometry=[], crs=gdf.crs)

    chemin_sortie = dossier / f"etape5_{code_departement}.gpkg"
    geodf_final.to_file(chemin_sortie, layer="messages", driver="GPKG")

    print(
        f"{len(geodf_final)} message(s) finalisé(s) (relu depuis {chemin_export.name}), "
        f"écrit(s) dans {chemin_sortie}."
    )
    return chemin_sortie


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Étape 5, Phase 4 — résout les messages finaux (natifs ou corrigés), écrit le livrable."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit (ex. 033, 971) — doit correspondre à un etape5_{dept}_a_completer.gpkg existant.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des fichiers (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 5, phase 4 — département {args.dept}")
    try:
        synthetiser(args.dept, dossier_sortie=args.output_dir)
    except GpkgIntrouvable as exc:
        print(f"Arrêt : etape5_{args.dept}_a_completer.gpkg introuvable ({exc}).", file=sys.stderr)
        return 1
    except ExportIntrouvable as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
