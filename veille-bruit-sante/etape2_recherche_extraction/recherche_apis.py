"""Phase 1a (etape 2) — recherche sur les API scientifiques structurées.

Voir etape-2-conception-technique.md, Décision 2. Aucune clé API requise pour ni OpenAlex
ni Europe PMC ; un `User-Agent` identifiant le projet est envoyé (bonne pratique attendue
par les deux API, notamment pour la "pool polie" d'OpenAlex).
"""
from datetime import date

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

USER_AGENT = "diagBruit-veille-bruit-sante/1.0 (mailto:contact@diagbruit.beta.gouv.fr)"
TIMEOUT_SECONDES = 30
RESULTATS_PAR_PAGE = 50


def _premier_auteur_openalex(travail: dict) -> str:
    auteurs = travail.get("authorships") or []
    if not auteurs:
        return ""
    premier = (auteurs[0].get("author") or {}).get("display_name", "")
    return f"{premier} et al." if len(auteurs) > 1 else premier


def _reconstituer_resume_openalex(travail: dict) -> str:
    """OpenAlex ne renvoie pas le résumé en clair mais un index inversé (position -> mot),
    pour des raisons de droits d'auteur sur les métadonnées d'éditeur."""
    index_inverse = travail.get("abstract_inverted_index")
    if not index_inverse:
        return ""
    positions: dict[int, str] = {}
    for mot, indices in index_inverse.items():
        for i in indices:
            positions[i] = mot
    return " ".join(positions[i] for i in sorted(positions))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _rechercher_openalex(date_depuis: date, date_jusqu_a: date) -> list[dict]:
    reponse = requests.get(
        "https://api.openalex.org/works",
        params={
            "search": "noise health OR bruit sante",
            "filter": (
                f"from_publication_date:{date_depuis.isoformat()},"
                f"to_publication_date:{date_jusqu_a.isoformat()}"
            ),
            "per_page": RESULTATS_PAR_PAGE,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDES,
    )
    reponse.raise_for_status()

    resultats = []
    for travail in reponse.json().get("results", []):
        source = ((travail.get("primary_location") or {}).get("source") or {})
        resultats.append({
            "canal": "api",
            "source_api": "openalex",
            "titre": travail.get("title") or "",
            "doi_url": travail.get("doi") or "",
            "annee": travail.get("publication_year"),
            "revue": source.get("display_name", ""),
            "resume_brut": _reconstituer_resume_openalex(travail),
            "auteurs": _premier_auteur_openalex(travail),
        })
    return resultats


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _rechercher_europe_pmc(date_depuis: date, date_jusqu_a: date) -> list[dict]:
    requete = (
        "(noise OR bruit) AND (health OR sante) AND "
        f"FIRST_PDATE:[{date_depuis.isoformat()} TO {date_jusqu_a.isoformat()}]"
    )
    reponse = requests.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": requete, "format": "json", "pageSize": RESULTATS_PAR_PAGE},
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDES,
    )
    reponse.raise_for_status()

    resultats = []
    for article in reponse.json().get("resultList", {}).get("result", []):
        doi = article.get("doi", "")
        resultats.append({
            "canal": "api",
            "source_api": "europe_pmc",
            "titre": article.get("title", ""),
            "doi_url": f"https://doi.org/{doi}" if doi else "",
            "annee": int(article["pubYear"]) if article.get("pubYear") else None,
            "revue": article.get("journalTitle", ""),
            "resume_brut": article.get("abstractText", ""),
            "auteurs": article.get("authorString", ""),
        })
    return resultats


def executer(date_depuis: date, date_jusqu_a: date | None = None) -> list[dict]:
    """Retourne la liste brute des études trouvées sur les deux API. Un canal en échec
    total (après ses tentatives) n'empêche pas l'autre de produire des résultats — voir
    etape-2-conception-technique.md, Décision 6."""
    date_jusqu_a = date_jusqu_a or date.today()
    resultats: list[dict] = []

    try:
        resultats.extend(_rechercher_openalex(date_depuis, date_jusqu_a))
    except Exception as erreur:
        print(f"[etape2][recherche_apis] echec OpenAlex apres tentatives : {erreur}")

    try:
        resultats.extend(_rechercher_europe_pmc(date_depuis, date_jusqu_a))
    except Exception as erreur:
        print(f"[etape2][recherche_apis] echec Europe PMC apres tentatives : {erreur}")

    return resultats
