"""Backfill ponctuel : ajoute `numero_page` aux CSV d'étape 2/3 déjà générés
avant l'ajout de cette colonne (voir `docs/etape-2-conception-technique.md`,
"Valeurs des champs du CSV de synthèse", et `docs/etape-3-conception-technique.md`,
"Contrat de données").

Ne rejoue PAS la phase 4 de l'étape 2 (classification, appels facturés à
l'API Anthropic) : reconstruit uniquement les phases 1 à 3 (résolution des
pièces, extraction du texte, filtrage lexical — aucun appel Anthropic, donc
gratuit) pour retrouver le `numero_page` de chaque passage retenu, puis le
réinjecte dans les fichiers CSV existants sans toucher au reste de leur
contenu — y compris les statuts de relecture déjà saisis dans un export de
`outil_validation.html`.

Appariement : pour chaque pièce (`nom_fichier`), les occurrences déjà
retenues dans `etape2_{dept}.csv` sont triées par leur compteur (préfixe
numérique de `id_occurrence`) puis appariées, dans cet ordre, au premier
passage non encore consommé de la liste régénérée par les phases 1-3 dont
`(reference_type, reference_precise)` correspond exactement. La recherche ne
recule jamais : l'ordre de traitement d'une pièce est préservé de bout en
bout du pipeline (phase 3 -> phase 4 -> phase 5), donc la Nième occurrence
retenue d'une pièce ne peut correspondre qu'à un passage situé après celui
apparié à la (N-1)ième. Les occurrences non appariées (cas limite : deux
passages consécutifs partageant la même référence) sont listées sur stderr,
`numero_page` y reste vide plutôt qu'une valeur devinée.

Usage :
    python backfill_numero_page.py --dept 067
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from etape2_analyse_reglements.extraction_texte import extraire_textes
from etape2_analyse_reglements.filtrage_lexical import PassageRetenu, filtrer_departement
from etape2_analyse_reglements.resolution_pieces import Etape1CsvIntrouvable, resoudre_pieces_departement


def _lire_csv(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier))


def _ecrire_csv(chemin: Path, colonnes: list[str], lignes: list[dict[str, str]]) -> None:
    with chemin.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=colonnes, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(lignes)


def _regenerer_passages(chemin_etape1: Path) -> dict[str, list[PassageRetenu]]:
    """Rejoue les phases 1 à 3 de l'étape 2 (aucun appel Anthropic) et
    regroupe les passages retenus par `nom_fichier`, dans leur ordre
    d'origine."""
    pieces, erreurs1 = resoudre_pieces_departement(chemin_etape1)
    print(f"  {len(pieces)} pièce(s) résolue(s), {len(erreurs1)} erreur(s) (phase 1).")

    extractions, erreurs2 = extraire_textes(pieces)
    print(f"  {len(extractions)} pièce(s) extraite(s), {len(erreurs2)} erreur(s) (phase 2).")

    passages, _ = filtrer_departement(extractions)
    print(f"  {len(passages)} passage(s) retrouvé(s) (phase 3).")

    par_piece: dict[str, list[PassageRetenu]] = {}
    for passage in passages:
        par_piece.setdefault(passage.piece.nom_fichier, []).append(passage)
    return par_piece


def _numero_page_par_occurrence(
    lignes_etape2: list[dict[str, str]],
    passages_par_piece: dict[str, list[PassageRetenu]],
) -> tuple[dict[tuple[str, str], str], list[str]]:
    """Apparie chaque occurrence de `etape2_{dept}.csv` (clé stable
    `id_gpu` + `id_occurrence`, voir "Contrat de données" de l'étape 3) à
    son `numero_page`. Retourne aussi les `id_occurrence` non appariées."""
    par_fichier: dict[str, list[dict[str, str]]] = {}
    for ligne in lignes_etape2:
        if not ligne.get("id_occurrence"):
            continue  # ligne "aucune occurrence trouvée", pas concernée
        _, nom_fichier = ligne["id_occurrence"].split("_", 1)
        par_fichier.setdefault(nom_fichier, []).append(ligne)

    resultat: dict[tuple[str, str], str] = {}
    non_appariees: list[str] = []

    for nom_fichier, lignes in par_fichier.items():
        lignes_triees = sorted(lignes, key=lambda l: int(l["id_occurrence"].split("_", 1)[0]))
        passages = passages_par_piece.get(nom_fichier, [])
        curseur = 0
        for ligne in lignes_triees:
            trouve = None
            for i in range(curseur, len(passages)):
                p = passages[i]
                if p.reference_type == ligne["reference_type"] and p.reference_precise == ligne["reference_precise"]:
                    trouve = i
                    break
            if trouve is None:
                non_appariees.append(ligne["id_occurrence"])
                continue
            resultat[(ligne["id_gpu"], ligne["id_occurrence"])] = str(passages[trouve].numero_page)
            curseur = trouve + 1

    return resultat, non_appariees


def _appliquer(chemin: Path, cle: dict[tuple[str, str], str]) -> int:
    if not chemin.exists():
        return 0
    lignes = _lire_csv(chemin)
    if not lignes:
        return 0

    colonnes = list(lignes[0].keys())
    if "numero_page" not in colonnes:
        index = colonnes.index("reference_precise") + 1 if "reference_precise" in colonnes else len(colonnes)
        colonnes.insert(index, "numero_page")

    n = 0
    for ligne in lignes:
        valeur = cle.get((ligne.get("id_gpu", ""), ligne.get("id_occurrence", "")))
        if valeur is not None:
            ligne["numero_page"] = valeur
            n += 1
        elif "numero_page" not in ligne:
            ligne["numero_page"] = ""

    _ecrire_csv(chemin, colonnes, lignes)
    return n


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill numero_page dans les CSV etape2/etape3 déjà générés, sans rejouer la classification (aucun appel Anthropic)."
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
    dossier = Path(args.output_dir)
    chemin_etape1 = dossier / f"etape1_{args.dept}.csv"
    chemin_etape2 = dossier / f"etape2_{args.dept}.csv"

    if not chemin_etape2.exists():
        print(f"Arrêt : {chemin_etape2} introuvable.", file=sys.stderr)
        return 1

    print(f"Backfill numero_page — département {args.dept}")
    print("Rejoue les phases 1 à 3 de l'étape 2 (aucun appel Anthropic)...")
    try:
        passages_par_piece = _regenerer_passages(chemin_etape1)
    except Etape1CsvIntrouvable as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
        return 1

    lignes_etape2 = _lire_csv(chemin_etape2)
    n_occurrences_reelles = sum(1 for l in lignes_etape2 if l.get("id_occurrence"))
    cle, non_appariees = _numero_page_par_occurrence(lignes_etape2, passages_par_piece)
    print(f"{len(cle)} occurrence(s) appariée(s) sur {n_occurrences_reelles} occurrence(s) réelle(s).")
    if non_appariees:
        print(
            f"ATTENTION : {len(non_appariees)} occurrence(s) non appariée(s), "
            f"numero_page laissé vide : {', '.join(non_appariees)}",
            file=sys.stderr,
        )

    cibles = [chemin_etape2, dossier / f"etape3_{args.dept}_a_valider.csv"]
    cibles += sorted(dossier.glob("etape3_export_outil_*.csv"))

    for chemin in cibles:
        n = _appliquer(chemin, cle)
        if chemin.exists():
            print(f"{chemin.name} : {n} ligne(s) mise(s) à jour.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
