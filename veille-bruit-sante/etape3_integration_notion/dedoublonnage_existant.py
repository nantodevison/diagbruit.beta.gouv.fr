"""Phase 2 (etape 3) — dédoublonnage contre l'existant.

Même logique à deux niveaux (DOI puis titre) que le dédoublonnage interne de l'étape 2,
réappliquée ici contre l'intégralité de l'historique de la base — voir
etape-3-conception-technique.md, Décision 2.
"""
from etape2_recherche_extraction.dedoublonnage import normaliser_doi, normaliser_titre, titres_similaires


def est_deja_present(etude: dict, doi_existants: set[str], titres_existants: list[str]) -> bool:
    doi = normaliser_doi(etude.get("doi_url"))
    if doi and doi in doi_existants:
        return True

    titre = normaliser_titre(etude.get("titre"))
    return any(titres_similaires(titre, t) for t in titres_existants)
