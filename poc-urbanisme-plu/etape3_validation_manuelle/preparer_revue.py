"""Étape 3 — Phase 1 : préparation de la revue.

Filtre, enrichit et priorise les occurrences d'`etape2_{dept}.csv` qui
nécessitent une relecture manuelle, pour produire un CSV prêt à charger dans
`outil_validation.html` (phase 2).

Usage :
    python -m etape3_validation_manuelle.preparer_revue --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape1_{dept}.csv
    etape2_{dept}.csv

Sortie (dans le même dossier) :
    etape3_{dept}_a_valider.csv — à charger dans outil_validation.html
"""

from __future__ import annotations

import argparse
import csv
import sys
from difflib import SequenceMatcher
from pathlib import Path

from .contexte_documents import charger_contexte_documents

# Seules ces deux valeurs de statut_verification (étape 2) correspondent à
# une occurrence retenue par la classification automatique — voir
# etape-2-analyse-documents-urbanisme-diagbruit.md, phase 5. Les lignes
# "aucune occurrence trouvée" ne sont pas présentées à l'opérateur : rien à y
# relire (voir etape-3-validation-manuelle.md). Elles restent nécessaires en
# amont pour synthese_finale.py, qui les relit directement dans
# etape2_{dept}.csv.
STATUT_VALIDE = "validé"
STATUT_A_VERIFIER = "à vérifier (renvoi CSV-PEB potentiel)"
STATUTS_A_REVOIR = {STATUT_VALIDE, STATUT_A_VERIFIER}

# Ordre de priorité pour la relecture : plus la valeur est basse, plus
# l'occurrence mérite d'être traitée en premier (citation peu claire et/ou
# texte source obtenu par OCR peu fiable). Les valeurs absentes du
# dictionnaire (colonne vide) sont classées en dernier.
RANG_CONFIANCE_EXTRAIT = {"faible": 0, "moyenne": 1, "forte": 2, "totale": 3}
RANG_OCR_CONFIANCE = {"faible": 0, "moyenne": 1, "élevée": 2}

# Seuil de similarité (ratio difflib.SequenceMatcher, 0 à 1) au-delà duquel
# deux occurrences du même document sont signalées comme doublon probable —
# voir "Détection automatique des doublons probables" dans
# etape-3-conception-technique.md. Purement indicatif : jamais utilisé pour
# filtrer, seulement pour présélectionner le champ `doublon_de_id_occurrence`
# que l'opérateur confirme ou corrige dans l'outil de relecture. À affiner
# selon l'usage réel — valeur de départ choisie pour rester permissive
# (mieux vaut une fausse suggestion, écartée en un clic, qu'un doublon réel
# manqué).
SEUIL_SIMILARITE_DOUBLON = 0.6

# Cet ordre de colonnes est celui utilisé par l'outil HTML et par
# synthese_finale.py — voir etape-3-conception-technique.md, "Contrat de
# données". Pas besoin d'être identique à etape2_{dept}.csv (même section) :
# seules id_gpu et id_occurrence doivent rester stables pour permettre une
# jointure ultérieure. date_traitement (étape 2) n'apporte rien à la
# relecture, elle n'est pas reprise ici.
COLONNES_SORTIE = [
    "id_gpu",
    "id_occurrence",
    "nom_document",
    "communes",
    "type_piece_source",
    "lien_web_document",
    "reference_type",
    "reference_precise",
    "numero_page",
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
    "priorite",
    "doublon_probable_de",
]


class FichiersEntreeIntrouvables(Exception):
    pass


def _priorite(ligne: dict[str, str]) -> int:
    rang_confiance = RANG_CONFIANCE_EXTRAIT.get(ligne.get("confiance_extrait", ""), 4)
    rang_ocr = RANG_OCR_CONFIANCE.get(ligne.get("ocr_confiance", ""), 3)
    return rang_confiance * 10 + rang_ocr


def _doublons_probables(lignes: list[dict[str, str | int]]) -> dict[str, str]:
    """Pour chaque `id_occurrence`, suggère l'`id_occurrence` la plus
    textuellement proche parmi les occurrences du même document (`id_gpu`,
    seul périmètre de comparaison : un doublon, par définition, vient du même
    document — voir "Doublon vs fusion" dans
    `plan-automatisation-regles-plu-diagbruit.md`) et de même
    `nature_sonore_zone`, si leur similarité (`extrait_significatif`)
    dépasse `SEUIL_SIMILARITE_DOUBLON`. Comparaison par paire à l'intérieur
    de chaque document (coût négligeable : quelques dizaines d'occurrences
    au plus par document).
    """
    par_document: dict[str, list[dict[str, str | int]]] = {}
    for ligne in lignes:
        par_document.setdefault(str(ligne["id_gpu"]), []).append(ligne)

    suggestions: dict[str, str] = {}
    for occurrences_document in par_document.values():
        for i, candidate in enumerate(occurrences_document):
            nature = candidate.get("nature_sonore_zone")
            if not nature:
                continue
            meilleur_id: str | None = None
            meilleur_score = SEUIL_SIMILARITE_DOUBLON
            for j, autre in enumerate(occurrences_document):
                if i == j or autre.get("nature_sonore_zone") != nature:
                    continue
                score = SequenceMatcher(
                    None,
                    str(candidate.get("extrait_significatif", "")),
                    str(autre.get("extrait_significatif", "")),
                ).ratio()
                if score > meilleur_score:
                    meilleur_score = score
                    meilleur_id = str(autre["id_occurrence"])
            if meilleur_id:
                suggestions[str(candidate["id_occurrence"])] = meilleur_id

    return suggestions


def preparer(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_etape1 = dossier / f"etape1_{code_departement}.csv"
    chemin_etape2 = dossier / f"etape2_{code_departement}.csv"

    if not chemin_etape1.exists() or not chemin_etape2.exists():
        raise FichiersEntreeIntrouvables(f"{chemin_etape1} et/ou {chemin_etape2}")

    contexte_documents = charger_contexte_documents(chemin_etape1)

    lignes_a_revoir: list[dict[str, str | int]] = []
    with chemin_etape2.open(encoding="utf-8-sig", newline="") as fichier:
        for ligne in csv.DictReader(fichier):
            if ligne.get("statut_verification") not in STATUTS_A_REVOIR:
                continue
            contexte = contexte_documents.get(ligne["id_gpu"], {})
            nouvelle_ligne: dict[str, str | int] = dict(ligne)
            nouvelle_ligne["nom_document"] = contexte.get("nom_document", "(document non identifié)")
            nouvelle_ligne["communes"] = contexte.get("communes", "")
            nouvelle_ligne["priorite"] = _priorite(ligne)
            lignes_a_revoir.append(nouvelle_ligne)

    if not lignes_a_revoir:
        print(f"Aucune occurrence à valider pour le département {code_departement}.")

    suggestions_doublons = _doublons_probables(lignes_a_revoir)
    for ligne in lignes_a_revoir:
        ligne["doublon_probable_de"] = suggestions_doublons.get(str(ligne["id_occurrence"]), "")

    lignes_a_revoir.sort(key=lambda l: (l["nom_document"], l["priorite"]))

    n_suggestions = len(suggestions_doublons)
    if n_suggestions:
        print(
            f"{n_suggestions} doublon(s) probable(s) suggéré(s) automatiquement "
            "(à confirmer ou corriger dans l'outil de relecture)."
        )

    chemin_sortie = dossier / f"etape3_{code_departement}_a_valider.csv"
    with chemin_sortie.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES_SORTIE, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(lignes_a_revoir)

    print(f"{len(lignes_a_revoir)} occurrence(s) à valider écrite(s) dans {chemin_sortie}")
    print("Chargez ce fichier dans outil_validation.html pour démarrer la relecture.")
    return chemin_sortie


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Filtre, enrichit et priorise les occurrences d'étape 2 nécessitant une relecture manuelle."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit, 3 chiffres (ex. 033, 971) — doit correspondre à un etape1_{dept}.csv et etape2_{dept}.csv existants.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des CSV (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 3, phase 1 — département {args.dept}")
    try:
        preparer(args.dept, dossier_sortie=args.output_dir)
    except FichiersEntreeIntrouvables as exc:
        print(f"Arrêt : fichier(s) d'entrée introuvable(s) : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
