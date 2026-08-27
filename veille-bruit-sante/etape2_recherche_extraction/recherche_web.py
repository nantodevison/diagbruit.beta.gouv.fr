"""Phase 1b (etape 2) — recherche via l'outil serveur web_search de l'API Anthropic,
restreinte aux domaines listés dans config/domains_whitelist.yaml.

Voir etape-2-conception-technique.md, Décision 3. Ce module ne fait qu'identifier des
sources candidates (URL + contexte) : l'extraction structurée proprement dite est déléguée
à extraction.py, un appel dédié par source trouvée.
"""
from datetime import date
from pathlib import Path
from typing import Optional

import yaml
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

CHEMIN_WHITELIST = Path(__file__).resolve().parent.parent / "config" / "domains_whitelist.yaml"
MODELE = "claude-sonnet-5"


def _charger_domaines_autorises() -> list[str]:
    """Aplatit toutes les catégories du fichier en une seule liste de domaines — les
    catégories n'existent que pour la lisibilité humaine du fichier, voir son en-tête."""
    with open(CHEMIN_WHITELIST, encoding="utf-8") as f:
        categories = yaml.safe_load(f)
    return [domaine for domaines in categories.values() for domaine in domaines]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def executer(date_depuis: date, date_jusqu_a: Optional[date] = None) -> list[dict]:
    """Retourne une liste de sources candidates brutes (canal="web"), pas encore
    structurées. La date de recherche est toujours injectée en toutes lettres dans le
    prompt (jamais une formulation relative), conformément au plan de veille."""
    date_jusqu_a = date_jusqu_a or date.today()
    domaines = _charger_domaines_autorises()

    client = Anthropic()
    reponse = client.messages.create(
        model=MODELE,
        max_tokens=4096,
        tools=[{
            "type": "web_search_20260209",
            "name": "web_search",
            "allowed_domains": domaines,
        }],
        messages=[{
            "role": "user",
            "content": (
                "Recherche les publications scientifiques et rapports institutionnels "
                "sur le lien entre bruit et sante, publies entre le "
                f"{date_depuis.isoformat()} et le {date_jusqu_a.isoformat()}, portant sur "
                "l'Europe ou des populations europeennes. Pour chaque source trouvee, "
                "indique son titre, son URL exacte, et un resume de son contenu."
            ),
        }],
    )

    sources: list[dict] = []
    for bloc in reponse.content:
        if bloc.type != "web_search_tool_result":
            continue
        if isinstance(bloc.content, list):
            for resultat in bloc.content:
                sources.append({
                    "canal": "web",
                    "titre": getattr(resultat, "title", "") or "",
                    "doi_url": getattr(resultat, "url", "") or "",
                })
        else:
            code_erreur = getattr(bloc.content, "error_code", bloc.content)
            print(f"[etape2][recherche_web] erreur web_search : {code_erreur}")

    # Le texte de synthèse (avec le contenu que le modèle a effectivement lu) sert de
    # contexte à l'extraction structurée pour chaque source listée ci-dessus.
    texte_synthese = next((b.text for b in reponse.content if b.type == "text"), "")
    for source in sources:
        source["contexte_synthese"] = texte_synthese

    return sources
