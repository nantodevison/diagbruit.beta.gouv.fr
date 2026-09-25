"""Point d'entrée de l'étape 2 — voir docs/etape-2-conception-technique.md."""
from datetime import date

from . import dedoublonnage, extraction, qualification, recherche_apis, recherche_web


def executer(date_depuis: date) -> list[dict]:
    """Retourne la liste des études trouvées, dédoublonnées et qualifiées (priorite,
    nouveaute), prêtes pour l'étape 3."""
    sources: list[dict] = []
    sources.extend(recherche_apis.executer(date_depuis))
    sources.extend(recherche_web.executer(date_depuis))

    etudes = extraction.executer(sources)
    etudes = dedoublonnage.dedoublonner(etudes)
    return qualification.qualifier(etudes, date_depuis)
