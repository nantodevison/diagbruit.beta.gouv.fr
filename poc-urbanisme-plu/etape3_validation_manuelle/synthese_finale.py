"""Étape 3 — Phase 3 : synthèse finale.

Consolide le dernier export de l'outil de relecture (`outil_validation.html`)
avec `etape2_{dept}.csv` pour produire le contrat de sortie de l'étape 3 —
l'entrée attendue par l'étape 4 (assignation de géométrie).

Usage :
    python -m etape3_validation_manuelle.synthese_finale --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape1_{dept}.csv                     — contexte documentaire (nom, communes)
    etape2_{dept}.csv                     — référence complète (tous les id_gpu traités)
    etape3_export_outil_{horodatage}.csv  — export(s) de l'outil ; le plus
                                             récent (horodatage le plus
                                             grand) est détecté automatiquement

Sortie (dans le même dossier) :
    etape3_{dept}.csv                  — contrat pour l'étape 4
    etape3_{dept}_rejetees.csv         — audit : occurrences écartées (si non vide)
    etape3_{dept}_non_traitees.csv     — occurrences oubliées par l'opérateur (si non vide)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from .contexte_documents import charger_contexte_documents

# Une occurrence "corrigé" a été retouchée par l'opérateur avant validation —
# voir etape-3-validation-manuelle.md, "États de validation". Les deux
# valeurs comptent comme retenues pour la suite du pipeline.
STATUT_VALIDE = "validé"
STATUT_CORRIGE = "corrigé"
STATUTS_RETENUS = {STATUT_VALIDE, STATUT_CORRIGE}
STATUT_AUCUNE_OCCURRENCE = "aucune occurrence trouvée"

COLONNES_FINALES = [
    "id_gpu",
    "id_occurrence",
    "statut_verification_finale",
    "nom_document",
    "communes",
    "type_piece_source",
    "lien_web_document",
    "reference_type",
    "reference_precise",
    "zone_reglementaire_mentionnee",
    "extrait_significatif",
    "contexte_documentaire",
    "confiance_extrait",
    "justification",
    "nature_occurrence",
    "nature_juridique_piece",
    "nature_sonore_zone",
    "ocr_utilise",
    "ocr_confiance",
    "validation_manuelle_statut",
    "validation_manuelle_commentaire",
]


class FichiersEntreeIntrouvables(Exception):
    pass


class ExportOutilInvalide(Exception):
    pass


# Nom généré par exporterCSV() dans outil_validation.html (fonction
# horodatage()) : pas de code département dedans, l'outil étant réutilisable
# tel quel pour n'importe quel département. Chaque clic sur "Exporter", et
# chaque export automatique tous les SEUIL_EXPORT_AUTO traitements, produit
# un nouveau fichier plutôt que d'écraser le précédent — d'où la nécessité de
# repérer le plus récent plutôt que d'attendre un nom fixe.
PATRON_EXPORT_OUTIL = re.compile(r"^etape3_export_outil_(\d{8}_\d{6})\.csv$")


def _dernier_export(dossier: Path) -> Path:
    """Retourne le fichier `etape3_export_outil_{horodatage}.csv` le plus
    récent du dossier, l'horodatage encodé dans le nom (format
    `AAAAMMJJ_HHMMSS`) servant de clé de tri plutôt que la date de
    modification du fichier, moins fiable (copie, synchro, téléchargement
    différé...).
    """
    candidats = sorted(
        (correspondance.group(1), chemin)
        for chemin in dossier.glob("etape3_export_outil_*.csv")
        if (correspondance := PATRON_EXPORT_OUTIL.match(chemin.name))
    )
    if not candidats:
        raise FichiersEntreeIntrouvables(
            f"{dossier / 'etape3_export_outil_*.csv'} (aucun export de outil_validation.html trouvé)"
        )
    return candidats[-1][1]


def _lire_csv(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier))


def _ecrire_csv(chemin: Path, colonnes: list[str], lignes: list[dict[str, str]]) -> None:
    with chemin.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=colonnes, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(lignes)


def synthetiser(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_etape1 = dossier / f"etape1_{code_departement}.csv"
    chemin_etape2 = dossier / f"etape2_{code_departement}.csv"

    manquants = [str(c) for c in (chemin_etape1, chemin_etape2) if not c.exists()]
    if manquants:
        raise FichiersEntreeIntrouvables(", ".join(manquants))

    chemin_export = _dernier_export(dossier)
    print(f"Dernier export de l'outil détecté : {chemin_export.name}")

    contexte_documents = charger_contexte_documents(chemin_etape1)
    lignes_etape2 = _lire_csv(chemin_etape2)
    lignes_export = _lire_csv(chemin_export)

    if lignes_export and "validation_manuelle_statut" not in lignes_export[0]:
        raise ExportOutilInvalide(
            "le fichier exporté ne contient pas la colonne validation_manuelle_statut "
            "— vérifiez qu'il s'agit bien d'un export de outil_validation.html, pas d'un autre CSV."
        )

    colonnes_export = list(lignes_export[0].keys()) if lignes_export else []
    non_traitees = [l for l in lignes_export if not l.get("validation_manuelle_statut")]
    traitees = [l for l in lignes_export if l.get("validation_manuelle_statut")]
    retenues = [l for l in traitees if l["validation_manuelle_statut"] in STATUTS_RETENUS]
    rejetees = [l for l in traitees if l["validation_manuelle_statut"] not in STATUTS_RETENUS]

    if non_traitees:
        chemin_non_traitees = dossier / f"etape3_{code_departement}_non_traitees.csv"
        _ecrire_csv(chemin_non_traitees, colonnes_export, non_traitees)
        print(
            f"Attention : {len(non_traitees)} occurrence(s) non traitée(s) par "
            f"l'opérateur, listée(s) dans {chemin_non_traitees}. Exclue(s) de "
            "la sortie finale — à reprendre avant de considérer le "
            "département terminé."
        )

    if rejetees:
        chemin_rejetees = dossier / f"etape3_{code_departement}_rejetees.csv"
        _ecrire_csv(chemin_rejetees, colonnes_export, rejetees)
        print(
            f"{len(rejetees)} occurrence(s) rejetée(s), conservée(s) pour "
            f"traçabilité dans {chemin_rejetees} (pas de suppression silencieuse)."
        )

    # Un document (id_gpu) est non significatif si aucune de ses occurrences
    # n'est retenue — que ce soit parce qu'aucune occurrence n'a jamais été
    # relevée en étape 2 (jamais soumis à relecture), ou parce que toutes ont
    # été rejetées ou laissées non traitées en étape 3. Une seule ligne de
    # synthèse le représente — voir etape-3-validation-manuelle.md,
    # "Agrégation par document".
    id_gpu_significatifs = {l["id_gpu"] for l in retenues}
    tous_les_id_gpu = {l["id_gpu"] for l in lignes_etape2}
    id_gpu_non_significatifs = tous_les_id_gpu - id_gpu_significatifs

    lignes_sortie: list[dict[str, str]] = []
    for ligne in retenues:
        nouvelle = {colonne: ligne.get(colonne, "") for colonne in COLONNES_FINALES}
        nouvelle["statut_verification_finale"] = ligne["validation_manuelle_statut"]
        lignes_sortie.append(nouvelle)

    for id_gpu in sorted(id_gpu_non_significatifs):
        contexte = contexte_documents.get(id_gpu, {})
        nouvelle = {colonne: "" for colonne in COLONNES_FINALES}
        nouvelle.update(
            id_gpu=id_gpu,
            statut_verification_finale=STATUT_AUCUNE_OCCURRENCE,
            nom_document=contexte.get("nom_document", "(document non identifié)"),
            communes=contexte.get("communes", ""),
        )
        lignes_sortie.append(nouvelle)

    lignes_sortie.sort(key=lambda l: (l["nom_document"], l["id_occurrence"]))

    chemin_sortie = dossier / f"etape3_{code_departement}.csv"
    _ecrire_csv(chemin_sortie, COLONNES_FINALES, lignes_sortie)
    print(
        f"{len(lignes_sortie)} ligne(s) écrite(s) dans {chemin_sortie} "
        f"({len(retenues)} occurrence(s) significative(s), "
        f"{len(id_gpu_non_significatifs)} document(s) non significatif(s))."
    )
    return chemin_sortie


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consolide l'export de l'outil de validation manuelle avec etape2_{dept}.csv."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit, 3 chiffres (ex. 033, 971).",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des CSV (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 3, phase 3 — département {args.dept}")
    try:
        synthetiser(args.dept, dossier_sortie=args.output_dir)
    except FichiersEntreeIntrouvables as exc:
        print(f"Arrêt : fichier(s) d'entrée introuvable(s) : {exc}", file=sys.stderr)
        return 1
    except ExportOutilInvalide as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
