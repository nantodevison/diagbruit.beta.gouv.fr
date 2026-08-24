"""Phase 5 de l'étape 2 : écriture du CSV de synthèse et du fichier d'erreurs.

Ce module ne fait aucun appel réseau : il met en forme les résultats produits
par `classification.py` (phase 4) selon le format défini dans
`etape-2-analyse-documents-urbanisme-diagbruit.md`. Comme à l'étape 1, le CSV
produit est à la fois le contrat de données stable pour la suite du plan
global et la matérialisation de l'étape de vérification humaine prévue avant
intégration.

Une pièce dont la classification n'a produit aucune occurrence retenue
(`retenu=True`) donne tout de même une ligne, avec `statut_verification =
"aucune occurrence trouvée"` — que la phase 3 n'ait rien repéré du tout, ou
que la phase 4 ait écarté chaque passage lexicalement repéré (`retenu=False`,
non écrit en ligne à part : voir `classification.py`). Une pièce dont
l'extraction (phase 2) a échoué n'a pas de ligne ici : son échec est déjà
documenté dans le fichier d'erreurs, une ligne "aucune occurrence" ferait
double emploi.

`id_occurrence` (mis à jour le 13/08/2026, retour utilisateur) : plutôt qu'un
simple compteur global au département (peu traçable), l'identifiant combine
le nom du fichier source (`nom_fichier` de la pièce, déjà unique dans le
département — voir `resolution_pieces.py`) et un compteur qui repart à 1
pour chaque pièce, ex. `1_246700488_reglement_20260206.pdf`,
`2_246700488_reglement_20260206.pdf`. Il n'est jamais vide pour une occurrence
réelle ; il reste vide uniquement sur les lignes "aucune occurrence trouvée",
qui ne portent par définition aucune occurrence à identifier.

`extrait_significatif` et `contexte_documentaire` (mis à jour le 13/08/2026,
"option 4", retour utilisateur) : remplacent l'ancienne colonne
`extrait_occurrence`. `extrait_significatif` est la citation verbatim
choisie par le modèle (voir `classification.py`) — la règle isolée, sans son
contexte. `contexte_documentaire` concatène, dans l'ordre de lecture du
document, le contexte juste avant cette citation, la citation elle-même, et
le contexte juste après — pour donner au relecteur humain la même vue que
celle dont a disposé le modèle pour classifier, sans qu'il ait besoin
d'ouvrir le PDF source pour la plupart des vérifications. Les deux colonnes
sont exposées côte à côte : `extrait_significatif` pour un survol rapide,
`contexte_documentaire` pour vérifier en contexte (au prix d'une répétition
possible de la citation dans ce dernier, voir
`docs/ameliorations-identifiees.md`).

`justification` (ajouté le 13/08/2026, retour utilisateur) : le raisonnement
du modèle derrière `retenu` et `confiance_extrait` — en particulier laquelle
des deux raisons possibles justifie une confiance faible (citation peu
claire, ou règle limitée à l'infrastructure de transport — voir
`classification.py`). Jusqu'ici calculé mais jamais exposé dans le CSV, donc
invisible sans relire le code ; nécessaire pour comprendre *pourquoi* le
modèle a tranché comme il l'a fait sur un cas litigieux.

Pour la liste exhaustive des valeurs possibles de chaque colonne
(`type_piece_source`, `reference_type`, `nature_occurrence`,
`nature_juridique_piece`, `nature_sonore_zone`, `statut_verification`,
`confiance_extrait`...), voir la section "Valeurs des champs du CSV de
synthèse" de `docs/etape-2-conception-technique.md`.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .classification import OccurrenceClassifiee
from .extraction_texte import ExtractionPiece
from .resolution_pieces import TYPE_OAP, TYPE_PADD, TYPE_PSMV, TYPE_REGLEMENT, ErreurTraitement, Piece

COLONNES_SYNTHESE = [
    "id_gpu",
    "id_occurrence",
    "type_piece_source",
    "lien_web_document",
    "reference_type",
    "reference_precise",
    "zone_reglementaire_mentionnee",
    "portee_geometrique",
    "extrait_significatif",
    "contexte_documentaire",
    "confiance_extrait",
    "justification",
    "nature_occurrence",
    "nature_juridique_piece",
    "nature_sonore_zone",
    "statut_verification",
    "ocr_utilise",
    "ocr_confiance",
    "date_traitement",
]

COLONNES_ERREURS = [
    "id_gpu",
    "lien_web_document",
    "phase",
    "type_erreur",
    "message",
    "contenu_brut",
    "date_traitement",
]

STATUT_VALIDE = "validé"
STATUT_A_VERIFIER = "à vérifier (renvoi CSV-PEB potentiel)"
STATUT_AUCUNE_OCCURRENCE = "aucune occurrence trouvée"

# La nature juridique d'une pièce se déduit de son type (voir
# `etape-2-analyse-documents-urbanisme-diagbruit.md`, phase 5) : le règlement
# (PLU/PLUi/POS/CC comme PSMV) est opposable en conformité, les OAP en
# compatibilité, le PADD n'est pas directement opposable.
_NATURE_JURIDIQUE_PAR_TYPE = {
    TYPE_REGLEMENT: "opposable en conformité",
    TYPE_PSMV: "opposable en conformité",
    TYPE_OAP: "opposable en compatibilité",
    TYPE_PADD: "non opposable",
}


def _nature_juridique(type_piece_source: str) -> str:
    return _NATURE_JURIDIQUE_PAR_TYPE.get(type_piece_source, "")


def _cle_piece(piece: Piece) -> str:
    return piece.lien_web_document


def _contexte_documentaire(occurrence: OccurrenceClassifiee) -> str:
    """Concatène, dans l'ordre de lecture du document, le contexte avant, la
    citation choisie par le modèle et le contexte après (voir docstring du
    module)."""
    passage = occurrence.passage
    morceaux = [passage.contexte_avant, occurrence.extrait_significatif, passage.contexte_apres]
    return " ".join(morceau for morceau in morceaux if morceau).strip()


def _ligne_occurrence(occurrence: OccurrenceClassifiee, id_occurrence: str, date_traitement: str) -> dict:
    piece = occurrence.passage.piece
    statut = STATUT_A_VERIFIER if occurrence.passage.tag_exclusion else STATUT_VALIDE
    return {
        "id_gpu": piece.id_gpu,
        "id_occurrence": id_occurrence,
        "type_piece_source": piece.type_piece_source,
        "lien_web_document": piece.lien_web_document,
        "reference_type": occurrence.passage.reference_type,
        "reference_precise": occurrence.passage.reference_precise,
        "zone_reglementaire_mentionnee": occurrence.zone_reglementaire_mentionnee or "",
        "portee_geometrique": occurrence.portee_geometrique or "",
        "extrait_significatif": occurrence.extrait_significatif or "",
        "contexte_documentaire": _contexte_documentaire(occurrence),
        "confiance_extrait": occurrence.confiance_extrait or "",
        "justification": occurrence.justification,
        "nature_occurrence": occurrence.nature_occurrence or "",
        "nature_juridique_piece": _nature_juridique(piece.type_piece_source),
        "nature_sonore_zone": occurrence.nature_sonore_zone or "",
        "statut_verification": statut,
        "ocr_utilise": occurrence.passage.ocr_utilise,
        "ocr_confiance": occurrence.passage.ocr_confiance or "",
        "date_traitement": date_traitement,
    }


def _ligne_aucune_occurrence(extraction: ExtractionPiece, date_traitement: str) -> dict:
    piece = extraction.piece
    return {
        "id_gpu": piece.id_gpu,
        "id_occurrence": "",
        "type_piece_source": piece.type_piece_source,
        "lien_web_document": piece.lien_web_document,
        "reference_type": "",
        "reference_precise": "",
        "zone_reglementaire_mentionnee": "",
        "portee_geometrique": "",
        "extrait_significatif": "",
        "contexte_documentaire": "",
        "confiance_extrait": "",
        "justification": "",
        "nature_occurrence": "",
        "nature_juridique_piece": _nature_juridique(piece.type_piece_source),
        "nature_sonore_zone": "",
        "statut_verification": STATUT_AUCUNE_OCCURRENCE,
        "ocr_utilise": extraction.ocr_utilise,
        "ocr_confiance": extraction.ocr_confiance or "",
        "date_traitement": date_traitement,
    }


def _lignes_synthese(
    extractions: list[ExtractionPiece],
    occurrences: list[OccurrenceClassifiee],
    date_traitement: str,
) -> list[dict]:
    occurrences_retenues = [o for o in occurrences if o.retenu]

    lignes = []
    compteurs_par_piece: dict[str, int] = {}
    for occurrence in occurrences_retenues:
        nom_fichier = occurrence.passage.piece.nom_fichier
        compteurs_par_piece[nom_fichier] = compteurs_par_piece.get(nom_fichier, 0) + 1
        id_occurrence = f"{compteurs_par_piece[nom_fichier]}_{nom_fichier}"
        lignes.append(_ligne_occurrence(occurrence, id_occurrence, date_traitement))

    pieces_avec_occurrence = {_cle_piece(o.passage.piece) for o in occurrences_retenues}
    for extraction in extractions:
        if _cle_piece(extraction.piece) not in pieces_avec_occurrence:
            lignes.append(_ligne_aucune_occurrence(extraction, date_traitement))

    return lignes


def _lignes_erreurs(erreurs: list[ErreurTraitement], date_traitement: str) -> list[dict]:
    return [
        {
            "id_gpu": erreur.id_gpu,
            "lien_web_document": erreur.lien_web_document,
            "phase": erreur.phase,
            "type_erreur": erreur.type_erreur,
            "message": erreur.message,
            "contenu_brut": erreur.contenu_brut,
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
    extractions: list[ExtractionPiece],
    occurrences: list[OccurrenceClassifiee],
    erreurs: list[ErreurTraitement],
    code_departement: str,
    dossier_sortie: str | Path = "output",
) -> tuple[Path, Path]:
    """Écrit `etape2_{dept}.csv` et `etape2_{dept}_erreurs.csv` dans le
    dossier de sortie. Retourne les deux chemins écrits.
    """
    date_traitement = date.today().isoformat()
    dossier = Path(dossier_sortie)

    chemin_synthese = dossier / f"etape2_{code_departement}.csv"
    _ecrire_csv(
        chemin_synthese,
        COLONNES_SYNTHESE,
        _lignes_synthese(extractions, occurrences, date_traitement),
    )

    chemin_erreurs = dossier / f"etape2_{code_departement}_erreurs.csv"
    _ecrire_csv(chemin_erreurs, COLONNES_ERREURS, _lignes_erreurs(erreurs, date_traitement))

    return chemin_synthese, chemin_erreurs
