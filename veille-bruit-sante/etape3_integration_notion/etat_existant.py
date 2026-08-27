"""Phase 1 (etape 3) — récupération de l'état actuel de la base Notion.

Un seul appel paginé, en début de run, plutôt qu'une requête par étude — voir
etape-3-conception-technique.md, Décision 1. Interroge le data source de la base (voir
notion_utils.py pour la résolution database_id -> data_source_id).
"""
from notion_client import Client

from etape2_recherche_extraction.dedoublonnage import normaliser_doi, normaliser_titre

TAILLE_PAGE = 100


def recuperer_etat_existant(notion: Client, data_source_id: str) -> tuple[set[str], list[str]]:
    """Retourne (doi_normalises_existants, titres_normalises_existants)."""
    doi_existants: set[str] = set()
    titres_existants: list[str] = []
    curseur = None

    while True:
        reponse = notion.data_sources.query(
            data_source_id=data_source_id,
            start_cursor=curseur,
            page_size=TAILLE_PAGE,
        )
        for page in reponse["results"]:
            proprietes = page["properties"]

            doi = (proprietes.get("doi_url") or {}).get("url")
            if doi:
                doi_existants.add(normaliser_doi(doi))

            titre_bruts = (proprietes.get("titre") or {}).get("title") or []
            titre = titre_bruts[0]["plain_text"] if titre_bruts else ""
            titres_existants.append(normaliser_titre(titre))

        if not reponse.get("has_more"):
            break
        curseur = reponse.get("next_cursor")

    return doi_existants, titres_existants
