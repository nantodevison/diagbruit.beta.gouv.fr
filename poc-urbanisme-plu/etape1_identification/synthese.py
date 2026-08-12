"""Phase 3 de l'étape 1 : écriture du CSV de synthèse et du fichier d'erreurs.

Ce module ne fait aucun appel réseau : il met en forme les résultats produits
par `documents_urbanisme.py` (phase 2) selon le format défini dans
`etape-1-identification-documents-urbanisme-diagbruit.md`. Le CSV produit est
le contrat de données stable consommé par l'étape 2 du plan global — voir
`etape-1-conception-technique.md`, décision 2. Il est aussi la matérialisation de l'étape de vérification
humaine prévue par le plan avant intégration : ouvert dans un tableur, chaque
ligne doit se comprendre sans avoir à relire le code.

Une commune donne une ligne par document trouvé (DU et PSMV se cumulent sans
jamais se remplacer — une commune peut donc apparaître sur deux lignes) ; une
commune RNU confirmé ou en trou de couverture donne une seule ligne, sans
document, pour que chaque commune du département reste traçable dans le CSV.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .documents_urbanisme import (
    STATUT_RNU_CONFIRME,
    STATUT_TROU_DE_COUVERTURE,
    ErreurTraitement,
    ResultatCommune,
)

COLONNES_SYNTHESE = [
    "nom_commune",
    "code_insee_commune",
    "code_siren_epci",
    "nom_document",
    "nature_document",
    "id_gpu",
    "date_approbation",
    "niveau_couverture",
    "date_traitement",
    "statut",
]

COLONNES_ERREURS = [
    "code_insee_commune",
    "nom_commune",
    "phase",
    "type_erreur",
    "message",
    "date_traitement",
]


def _code_insee_avec_origine(code_insee_commune: str, code_insee_utilise: str) -> str:
    """Code actuel, avec l'ancien code utilisé précisé si le document n'a été
    trouvé que sous celui-ci (commune issue d'une fusion)."""
    if code_insee_utilise == code_insee_commune:
        return code_insee_commune
    return f"{code_insee_commune} (ancien code {code_insee_utilise})"


def _lignes_synthese(resultats: list[ResultatCommune], date_traitement: str) -> list[dict]:
    lignes = []
    for resultat in resultats:
        commune = resultat.commune

        if not resultat.documents:
            statut = STATUT_RNU_CONFIRME if resultat.rnu_confirme else STATUT_TROU_DE_COUVERTURE
            lignes.append(
                {
                    "nom_commune": commune.nom,
                    "code_insee_commune": commune.code_insee,
                    "code_siren_epci": commune.code_epci or "",
                    "nom_document": "",
                    "nature_document": "",
                    "id_gpu": "",
                    "date_approbation": "",
                    "niveau_couverture": "",
                    "date_traitement": date_traitement,
                    "statut": statut,
                }
            )
            continue

        for document in resultat.documents:
            lignes.append(
                {
                    "nom_commune": commune.nom,
                    "code_insee_commune": _code_insee_avec_origine(
                        commune.code_insee, document.code_insee_utilise
                    ),
                    "code_siren_epci": commune.code_epci or "",
                    "nom_document": document.nom_document,
                    "nature_document": document.nature_document,
                    "id_gpu": document.id_gpu,
                    "date_approbation": document.date_approbation or "",
                    "niveau_couverture": document.niveau_couverture,
                    "date_traitement": date_traitement,
                    "statut": document.statut,
                }
            )

    return lignes


def _lignes_erreurs(erreurs: list[ErreurTraitement], date_traitement: str) -> list[dict]:
    return [
        {
            "code_insee_commune": erreur.code_insee_commune,
            "nom_commune": erreur.nom_commune,
            "phase": erreur.phase,
            "type_erreur": erreur.type_erreur,
            "message": erreur.message,
            "date_traitement": date_traitement,
        }
        for erreur in erreurs
    ]


def _ecrire_csv(chemin: Path, colonnes: list[str], lignes: list[dict]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=colonnes)
        writer.writeheader()
        writer.writerows(lignes)


def ecrire_synthese(
    resultats: list[ResultatCommune],
    erreurs: list[ErreurTraitement],
    code_departement: str,
    dossier_sortie: str | Path = "output",
) -> tuple[Path, Path]:
    """Écrit `etape1_{dept}.csv` et `etape1_{dept}_erreurs.csv` dans le
    dossier de sortie. Retourne les deux chemins écrits.
    """
    date_traitement = date.today().isoformat()
    dossier = Path(dossier_sortie)

    chemin_synthese = dossier / f"etape1_{code_departement}.csv"
    _ecrire_csv(chemin_synthese, COLONNES_SYNTHESE, _lignes_synthese(resultats, date_traitement))

    chemin_erreurs = dossier / f"etape1_{code_departement}_erreurs.csv"
    _ecrire_csv(chemin_erreurs, COLONNES_ERREURS, _lignes_erreurs(erreurs, date_traitement))

    return chemin_synthese, chemin_erreurs
