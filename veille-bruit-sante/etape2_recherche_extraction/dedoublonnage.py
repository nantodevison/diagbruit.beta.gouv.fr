"""Phase 3 (etape 2) — dédoublonnage interne au run.

Les fonctions de normalisation d'ici sont réutilisées telles quelles par l'étape 3
(dédoublonnage contre l'existant, etape-3-conception-technique.md, Décision 1) pour garantir
qu'une même étude produit toujours la même clé de comparaison des deux côtés.
"""
import re

from rapidfuzz import fuzz

SEUIL_SIMILARITE_TITRE = 90


def normaliser_doi(doi_url: str | None) -> str:
    if not doi_url:
        return ""
    return (
        doi_url.lower()
        .removeprefix("https://doi.org/")
        .removeprefix("http://doi.org/")
        .strip("/")
    )


def normaliser_titre(titre: str | None) -> str:
    if not titre:
        return ""
    return re.sub(r"[^\w\s]", "", titre.lower()).strip()


def titres_similaires(titre_a: str, titre_b: str) -> bool:
    if not titre_a or not titre_b:
        return False
    return fuzz.ratio(titre_a, titre_b) >= SEUIL_SIMILARITE_TITRE


def dedoublonner(etudes: list[dict]) -> list[dict]:
    """Dédoublonnage interne au run. En cas de doublon entre les deux canaux, l'étude
    issue du canal API scientifiques est conservée en priorité (métadonnées structurées,
    DOI systématique) — voir etape-2-conception-technique.md, Décision 5."""
    etudes_triees = sorted(etudes, key=lambda e: e.get("canal") != "api")

    retenues: list[dict] = []
    doi_vus: set[str] = set()
    titres_vus: list[str] = []

    for etude in etudes_triees:
        doi = normaliser_doi(etude.get("doi_url"))
        titre = normaliser_titre(etude.get("titre"))

        if doi and doi in doi_vus:
            continue
        if any(titres_similaires(titre, t) for t in titres_vus):
            continue

        retenues.append(etude)
        if doi:
            doi_vus.add(doi)
        titres_vus.append(titre)

    return retenues
