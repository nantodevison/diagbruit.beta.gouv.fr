"""Phase 4 (etape 2) — qualification des études extraites, par des règles Python.

Voir etape-2-conception-technique.md, Décisions 7 et 8. Traduit les critères d'une
publication importante, tirés de la relecture manuelle de la base (conclusion claire, source
fiable et reconnue, explications qui étayent la conclusion), en deux attributs :

- `priorite` (Haute / A examiner / Faible) : ordonne la relecture manuelle. Elle informe
  l'utilisateur ; c'est la case `favori`, cochée à la main, qui traduit son choix. Réglée
  pour le rappel plutôt que la précision : mieux vaut un document de plus à trier qu'un
  favori potentiel relégué en bas de liste ;
- `nouveaute` : l'étude a été publiée dans la fenêtre de recherche. Un texte plus ancien
  (ex. lignes directrices OMS) n'est pas écarté : c'est un jalon qui contextualise les
  nouveautés, il est seulement distingué.

Aucun appel LLM ici : le LLM remplit les champs descriptifs à l'extraction (type_document,
sens_conclusion, elements_probants), les règles ci-dessous restent lisibles et ajustables.
Mesures sur les 78 fiches relues du 24/09/2026 : voir analyse_relecture/analyse-2026-09-24.md.
"""
from datetime import date
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

from .recherche_web import charger_domaines_autorises

# Libellés identiques aux options de la colonne Notion (etape1_base_notion/creer_base_notion.py).
HAUTE, A_EXAMINER, FAIBLE = "Haute", "A examiner", "Faible"

# Types de documents qui établissent leurs propres conclusions. Seuls eux peuvent être en
# priorité Haute ; les autres (revues narratives, éditoriaux, communiqués, pages
# d'information) restent candidats via la priorité « A examiner ».
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


def provenance_reconnue(etude: dict) -> bool:
    """Canal API scientifique (revues indexées par OpenAlex / Europe PMC) ou URL d'un
    domaine de la liste blanche."""
    return etude.get("canal") == "api" or domaine_autorise(etude.get("doi_url"))


def source_fiable(etude: dict) -> bool:
    """Type de document qui établit ses conclusions ET provenance reconnue."""
    return etude.get("type_document") in TYPES_SOURCE_FIABLE and provenance_reconnue(etude)


def calculer_priorite(etude: dict) -> str:
    """Haute : les trois critères (conclusion claire, source fiable, explications) — sur les
    fiches relues, 81 % de ces études étaient des favoris.
    A examiner : tout autre document qualifié par le LLM et de provenance reconnue, quel que
    soit son type — Haute + A examiner retrouvent 93 % des favoris.
    Faible : le reste (contenu insuffisant, provenance inconnue)."""
    if (
        etude.get("sens_conclusion") in CONCLUSIONS_CLAIRES
        and source_fiable(etude)
        and bool((etude.get("elements_probants") or "").strip())
    ):
        return HAUTE
    if etude.get("sens_conclusion") is not None and provenance_reconnue(etude):
        return A_EXAMINER
    return FAIBLE


def est_nouveaute(etude: dict, date_depuis: date) -> bool:
    """Comparaison à l'année près : on ne connaît en général que l'année de publication.
    Sans année, on ne peut pas affirmer que c'est une nouveauté."""
    annee = etude.get("annee")
    return annee is not None and annee >= date_depuis.year


def qualifier(etudes: list, date_depuis: date) -> list:
    """Ajoute priorite et nouveaute à chaque étude (modifie les dict en place et renvoie la
    même liste, pour s'enchaîner dans etape2_recherche_extraction/main.py)."""
    for etude in etudes:
        etude["priorite"] = calculer_priorite(etude)
        etude["nouveaute"] = est_nouveaute(etude, date_depuis)
    return etudes
