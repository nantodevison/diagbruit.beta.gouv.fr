"""Phase 4 (etape 2) — qualification des études extraites, par des règles Python.

Voir etape-2-conception-technique.md, Décision 7. Traduit les critères d'une publication
importante, tirés de la relecture manuelle de la base (conclusion claire, source fiable et
reconnue, explications qui étayent la conclusion), en deux cases à cocher :

- `candidat_favori` : l'étude remplit les trois critères ;
- `nouveaute` : l'étude a été publiée dans la fenêtre de recherche. Un texte plus ancien
  (ex. lignes directrices OMS) n'est pas écarté : c'est un jalon qui contextualise les
  nouveautés, il est seulement distingué.

Aucun appel LLM ici : le LLM remplit les champs descriptifs à l'extraction (type_document,
sens_conclusion, elements_probants), les règles ci-dessous restent lisibles et ajustables.
"""
from datetime import date
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

from .recherche_web import charger_domaines_autorises

# Types de documents qui peuvent compter comme « source fiable ». Les revues narratives,
# éditoriaux, communiqués et pages d'information en sont exclus : ils relaient ou
# commentent des conclusions plutôt que de les établir.
TYPES_SOURCE_FIABLE = {
    "Etude originale",
    "Meta-analyse ou revue systematique",
    "Rapport institutionnel",
}

# Conclusions « claires » : dans un sens comme dans l'autre.
CONCLUSIONS_CLAIRES = {"Effet demontre", "Absence d'effet"}


@lru_cache(maxsize=1)
def _domaines_autorises() -> tuple:
    # Lu une seule fois par run (lru_cache), la liste ne change pas en cours de route.
    return tuple(charger_domaines_autorises())


def domaine_autorise(url: Optional[str]) -> bool:
    """True si l'URL appartient à un domaine de la liste blanche, sous-domaines compris
    (ex. beh.santepubliquefrance.fr pour santepubliquefrance.fr)."""
    if not url:
        return False
    hote = urlparse(url).netloc.lower().removeprefix("www.")
    return any(hote == d or hote.endswith("." + d) for d in _domaines_autorises())


def source_fiable(etude: dict) -> bool:
    """Type de document fiable ET provenance reconnue : canal API scientifique (revues
    indexées par OpenAlex / Europe PMC) ou URL d'un domaine de la liste blanche."""
    if etude.get("type_document") not in TYPES_SOURCE_FIABLE:
        return False
    return etude.get("canal") == "api" or domaine_autorise(etude.get("doi_url"))


def est_candidat_favori(etude: dict) -> bool:
    return (
        etude.get("sens_conclusion") in CONCLUSIONS_CLAIRES
        and source_fiable(etude)
        and bool((etude.get("elements_probants") or "").strip())
    )


def est_nouveaute(etude: dict, date_depuis: date) -> bool:
    """Comparaison à l'année près : on ne connaît en général que l'année de publication.
    Sans année, on ne peut pas affirmer que c'est une nouveauté."""
    annee = etude.get("annee")
    return annee is not None and annee >= date_depuis.year


def qualifier(etudes: list, date_depuis: date) -> list:
    """Ajoute candidat_favori et nouveaute à chaque étude (modifie les dict en place et
    renvoie la même liste, pour s'enchaîner dans etape2_recherche_extraction/main.py)."""
    for etude in etudes:
        etude["candidat_favori"] = est_candidat_favori(etude)
        etude["nouveaute"] = est_nouveaute(etude, date_depuis)
    return etudes
