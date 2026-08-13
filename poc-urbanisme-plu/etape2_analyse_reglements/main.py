"""Point d'entrée de l'étape 2 : analyse des documents d'urbanisme pour
repérer les règles liées au bruit.

Usage :
    python -m etape2_analyse_reglements.main --dept 033
    python -m etape2_analyse_reglements.main --dept 033 --limit 5

Enchaîne les cinq phases (voir `etape-2-conception-technique.md`) :
1. `resolution_pieces.py` — id_gpu -> pièces téléchargeables.
2. `extraction_texte.py` — extraction du texte (OCR si besoin).
3. `filtrage_lexical.py` — repérage des passages liés au bruit.
4. `classification.py` — appel Claude, passage par passage.
5. `synthese.py` — écriture du CSV de synthèse et du fichier d'erreurs.

Seul l'échec de la phase 1 arrête le traitement du département (pas de
pièce résolue = rien d'exploitable en aval). Les erreurs des phases
suivantes sont toujours isolées à une pièce ou un passage et n'empêchent
jamais la production du CSV final (décision 4 de l'étape 1, reconduite).

`--limit N` plafonne, après la phase 1, le nombre de pièces effectivement
traitées par les phases 2 à 5 — utile pour un premier essai maîtrisé en coût
avant un run complet sur tout un département, chaque passage classifié en
phase 4 correspondant à un appel facturé à l'API Anthropic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .classification import classifier_departement
from .extraction_texte import extraire_textes
from .filtrage_lexical import filtrer_departement
from .resolution_pieces import Etape1CsvIntrouvable, resoudre_pieces_departement
from .synthese import ecrire_synthese


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyse les documents d'urbanisme d'un département pour repérer les règles liées au bruit."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit, 3 chiffres (ex. 033, 971) — doit correspondre à un etape1_{dept}.csv existant.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des CSV (défaut : output/).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Plafonne le nombre de pièces traitées après la phase 1 (maîtrise du coût des appels Claude).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 2 — département {args.dept}")
    chemin_etape1 = Path(args.output_dir) / f"etape1_{args.dept}.csv"

    print(f"Phase 1 — résolution des pièces depuis {chemin_etape1}...")
    try:
        pieces, erreurs1 = resoudre_pieces_departement(chemin_etape1)
    except Etape1CsvIntrouvable as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
        return 1
    print(f"  {len(pieces)} pièce(s) résolue(s), {len(erreurs1)} erreur(s).")

    if args.limit is not None and len(pieces) > args.limit:
        print(f"  --limit {args.limit} appliqué : {args.limit} pièce(s) sur {len(pieces)} seront traitées.")
        pieces = pieces[: args.limit]

    print("Phase 2 — extraction du texte (OCR si besoin)...")
    extractions, erreurs2 = extraire_textes(pieces)
    n_ocr = sum(1 for e in extractions if e.ocr_utilise)
    print(f"  {len(extractions)} pièce(s) extraite(s) ({n_ocr} via OCR), {len(erreurs2)} erreur(s).")

    print("Phase 3 — filtrage lexical...")
    passages, erreurs3 = filtrer_departement(extractions)
    print(f"  {len(passages)} passage(s) retenu(s) pour classification.")

    print("Phase 4 — classification (appels à l'API Anthropic)...")
    occurrences, erreurs4 = classifier_departement(passages)
    n_retenues = sum(1 for o in occurrences if o.retenu)
    print(f"  {n_retenues} occurrence(s) retenue(s) sur {len(occurrences)} passage(s) classifié(s), {len(erreurs4)} erreur(s).")

    print("Phase 5 — écriture des fichiers de sortie...")
    erreurs = erreurs1 + erreurs2 + erreurs3 + erreurs4
    chemin_synthese, chemin_erreurs = ecrire_synthese(
        extractions, occurrences, erreurs, args.dept, dossier_sortie=args.output_dir
    )
    print(f"  {chemin_synthese}")
    print(f"  {chemin_erreurs}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
