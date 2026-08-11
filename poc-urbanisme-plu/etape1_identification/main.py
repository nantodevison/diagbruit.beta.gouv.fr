"""Point d'entrée de l'étape 1 : identification des documents d'urbanisme en
vigueur d'un département.

Usage :
    python -m etape1_identification.main --dept 033

Enchaîne les trois phases (voir `etape-1-conception-technique.md`) :
1. `communes.py` — référentiel des communes du département.
2. `documents_urbanisme.py` — recherche des documents en vigueur.
3. `synthese.py` — écriture du CSV de synthèse et du fichier d'erreurs.

Seul l'échec de la phase 1 arrête le traitement du département (pas de
référentiel commune = rien d'exploitable en aval). Les erreurs de la phase 2
sont toujours isolées à une commune ou un EPCI et n'empêchent jamais la
production du CSV final (décision 4 du document de conception technique).
"""

from __future__ import annotations

import argparse
import sys

from .communes import ReferentielCommunesIndisponible, get_communes_departement
from .documents_urbanisme import rechercher_documents_departement
from .synthese import ecrire_synthese


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Identifie les documents d'urbanisme en vigueur des communes d'un département."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit, 3 chiffres (ex. 033, 971).",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de sortie pour les CSV (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 1 — département {args.dept}")

    print("Phase 1 — référentiel des communes...")
    try:
        communes = get_communes_departement(args.dept)
    except ReferentielCommunesIndisponible as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
        return 1
    print(f"  {len(communes)} commune(s) trouvée(s).")

    print("Phase 2 — recherche des documents d'urbanisme en vigueur...")
    resultats, erreurs = rechercher_documents_departement(communes)
    n_rnu = sum(1 for r in resultats if r.rnu_confirme)
    n_trous = sum(1 for r in resultats if r.trou_de_couverture)
    n_documents = sum(len(r.documents) for r in resultats)
    print(
        f"  {n_documents} document(s) trouvé(s), {n_rnu} commune(s) RNU confirmé, "
        f"{n_trous} trou(s) de couverture, {len(erreurs)} erreur(s)."
    )

    print("Phase 3 — écriture des fichiers de sortie...")
    chemin_synthese, chemin_erreurs = ecrire_synthese(
        resultats, erreurs, args.dept, dossier_sortie=args.output_dir
    )
    print(f"  {chemin_synthese}")
    print(f"  {chemin_erreurs}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
