"""Récupère le contenu source (résumé ou texte de page) de chaque fiche exportée, pour
pouvoir relancer l'extraction dessus (tester_qualification.py).

Gratuit : uniquement OpenAlex, Europe PMC et des requêtes HTTP, aucun appel Anthropic.
On ne réutilise pas les colonnes resume / resultat_cle de la base : elles ont été écrites
par le LLM lui-même, les réinjecter rendrait le test circulaire.

Ordre d'essai pour chaque fiche (on s'arrête au premier contenu exploitable) :
1. DOI dans l'URL → résumé OpenAlex ;
2. identifiant PubMed / PMC dans l'URL → résumé Europe PMC ;
3. page web elle-même (HTML seulement : les PDF sont signalés, pas lus) ;
4. recherche OpenAlex par titre, acceptée seulement si le titre correspond à ≥ 90 % ;
5. recherche Europe PMC sur le titre exact.

    python -m analyse_relecture.recuperer_contenus      (depuis veille-bruit-sante/)

Entrée : export/etudes.csv (exporter_base.py). Sortie : export/contenus.json.
"""
import csv
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from rapidfuzz import fuzz

from etape2_recherche_extraction.dedoublonnage import normaliser_titre
from etape2_recherche_extraction.recherche_apis import (
    TIMEOUT_SECONDES, USER_AGENT, _reconstituer_resume_openalex,
)

DOSSIER_EXPORT = Path(__file__).resolve().parent / "export"
LONGUEUR_MAX_PAGE = 8000   # caractères gardés d'une page web (≈ 2 300 tokens)
LONGUEUR_MIN_UTILE = 200   # en dessous, on considère le contenu comme inexploitable
SEUIL_TITRE = 90

ENTETES = {"User-Agent": USER_AGENT}
MOTIF_DOI = re.compile(r"(10\.\d{4,9}/[^\s?#]+)")
MOTIF_PMCID = re.compile(r"(PMC\d+)", re.I)
MOTIF_PMID = re.compile(r"pubmed(?:\.ncbi\.nlm\.nih\.gov)?/(\d+)")


class _ExtracteurTexte(HTMLParser):
    """Garde le texte visible d'une page HTML (sans scripts, styles, menus)."""
    IGNORES = {"script", "style", "nav", "header", "footer", "noscript"}

    def __init__(self):
        super().__init__()
        self.morceaux = []
        self._profondeur_ignoree = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORES:
            self._profondeur_ignoree += 1

    def handle_endtag(self, tag):
        if tag in self.IGNORES and self._profondeur_ignoree:
            self._profondeur_ignoree -= 1

    def handle_data(self, data):
        if not self._profondeur_ignoree and data.strip():
            self.morceaux.append(data.strip())


def _openalex_par_doi(doi: str) -> Optional[dict]:
    reponse = requests.get(
        f"https://api.openalex.org/works/doi:{doi}", headers=ENTETES, timeout=TIMEOUT_SECONDES,
    )
    if reponse.status_code != 200:
        return None
    return reponse.json()


def _openalex_par_titre(titre: str) -> Optional[dict]:
    reponse = requests.get(
        "https://api.openalex.org/works",
        params={"search": titre, "per_page": 1},
        headers=ENTETES, timeout=TIMEOUT_SECONDES,
    )
    if reponse.status_code != 200:
        return None
    resultats = reponse.json().get("results") or []
    if not resultats:
        return None
    similarite = fuzz.ratio(normaliser_titre(titre), normaliser_titre(resultats[0].get("title")))
    return resultats[0] if similarite >= SEUIL_TITRE else None


def _depuis_openalex(travail: Optional[dict], methode: str) -> Optional[dict]:
    if not travail:
        return None
    contenu = _reconstituer_resume_openalex(travail)
    if len(contenu) < LONGUEUR_MIN_UTILE:
        return None
    source = ((travail.get("primary_location") or {}).get("source") or {})
    return {
        "methode": methode,
        "contenu": contenu,
        "annee": travail.get("publication_year"),
        "revue": source.get("display_name", ""),
    }


def _europe_pmc(requete: str) -> Optional[dict]:
    reponse = requests.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": requete, "format": "json", "resultType": "core", "pageSize": 1},
        headers=ENTETES, timeout=TIMEOUT_SECONDES,
    )
    if reponse.status_code != 200:
        return None
    resultats = reponse.json().get("resultList", {}).get("result", [])
    if not resultats or len(resultats[0].get("abstractText", "")) < LONGUEUR_MIN_UTILE:
        return None
    article = resultats[0]
    return {
        "methode": "europe_pmc",
        # abstractText contient parfois des balises HTML (<h4>, <b>…)
        "contenu": re.sub(r"<[^>]+>", " ", article["abstractText"]),
        "annee": int(article["pubYear"]) if article.get("pubYear") else None,
        "revue": (article.get("journalInfo") or {}).get("journal", {}).get("title", ""),
    }


def _page_web(url: str) -> dict:
    """Retourne toujours un dict : contenu vide et raison dans `methode` en cas d'échec."""
    try:
        reponse = requests.get(url, headers=ENTETES, timeout=TIMEOUT_SECONDES)
    except requests.RequestException as erreur:
        return {"methode": f"echec_page ({type(erreur).__name__})", "contenu": ""}
    type_contenu = reponse.headers.get("Content-Type", "")
    if reponse.status_code >= 400:
        return {"methode": f"echec_page (HTTP {reponse.status_code})", "contenu": ""}
    # Lien mort renvoyé vers la page d'accueil du site : même heuristique que
    # etape3_integration_notion/verification_url.py.
    if urlparse(url).path.strip("/") and not urlparse(reponse.url).path.strip("/"):
        return {"methode": "redirige_accueil", "contenu": ""}
    if "pdf" in type_contenu:
        return {"methode": "pdf_non_lu", "contenu": ""}
    extracteur = _ExtracteurTexte()
    extracteur.feed(reponse.text)
    texte = " ".join(extracteur.morceaux)[:LONGUEUR_MAX_PAGE]
    if len(texte) < LONGUEUR_MIN_UTILE:
        return {"methode": "page_vide", "contenu": ""}
    return {"methode": "page_web", "contenu": texte}


def recuperer(fiche: dict) -> dict:
    url = fiche.get("doi_url", "")

    doi = MOTIF_DOI.search(url)
    if doi:
        trouve = _depuis_openalex(_openalex_par_doi(doi.group(1).rstrip(".")), "openalex_doi")
        if trouve:
            return trouve

    pmcid, pmid = MOTIF_PMCID.search(url), MOTIF_PMID.search(url)
    if pmcid or pmid:
        requete = f"PMCID:{pmcid.group(1).upper()}" if pmcid else f"EXT_ID:{pmid.group(1)} AND SRC:MED"
        trouve = _europe_pmc(requete)
        if trouve:
            return trouve

    resultat_page = _page_web(url) if url else {"methode": "sans_url", "contenu": ""}
    if resultat_page["contenu"]:
        return resultat_page

    trouve = _depuis_openalex(_openalex_par_titre(fiche["titre"]), "openalex_titre")
    if trouve:
        return trouve

    # Dernier recours : titre exact dans Europe PMC (les guillemets imposent la phrase).
    titre_nettoye = re.sub(r'["()\[\]:]', " ", fiche["titre"])
    trouve = _europe_pmc(f'TITLE:"{titre_nettoye}"')
    if trouve:
        trouve["methode"] = "europe_pmc_titre"
        return trouve
    return resultat_page


def main() -> None:
    with open(DOSSIER_EXPORT / "etudes.csv", encoding="utf-8-sig") as f:
        fiches = list(csv.DictReader(f))

    contenus = {}
    for numero, fiche in enumerate(fiches, start=1):
        try:
            contenus[fiche["page_id"]] = recuperer(fiche)
        except Exception as erreur:  # une fiche en échec ne bloque pas les autres
            contenus[fiche["page_id"]] = {"methode": f"erreur ({erreur})", "contenu": ""}
        print(f"{numero:3}/{len(fiches)} {contenus[fiche['page_id']]['methode']:22} {fiche['titre'][:70]}")

    with open(DOSSIER_EXPORT / "contenus.json", "w", encoding="utf-8") as f:
        json.dump(contenus, f, ensure_ascii=False, indent=1)

    methodes = {}
    for c in contenus.values():
        cle = c["methode"].split(" ")[0]
        methodes[cle] = methodes.get(cle, 0) + 1
    print("\nBilan :", methodes)
    print("Caractères de contenu au total :", sum(len(c["contenu"]) for c in contenus.values()))


if __name__ == "__main__":
    main()
