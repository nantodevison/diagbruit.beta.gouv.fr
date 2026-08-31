"""Phase pre-ecriture (etape 3) — verification que doi_url pointe reellement vers un
document, juste avant l'ecriture Notion. Requetes HTTP uniquement, aucun appel a l'API
Anthropic (ces appels sont couteux et reserves aux taches qui le justifient).

Heuristique volontairement tolerante, pas une garantie absolue (un site peut renvoyer 200
sur une page de substitution qui ressemble a un vrai document) : on ne rejette jamais une
etude sur ce seul signal, on pose un flag url_not_real pour verification manuelle — voir
etape3_integration_notion/main.py.
"""
from urllib.parse import urlparse

import requests

USER_AGENT = "diagBruit-veille-bruit-sante/1.0 (mailto:contact@diagbruit.beta.gouv.fr)"
TIMEOUT_SECONDES = 15


def _chemin(url: str) -> str:
    return urlparse(url).path.strip("/")


def url_pointe_vers_un_document(url: str) -> bool:
    """False si l'URL est vide, injoignable, en erreur HTTP, ou si la redirection finale a
    perdu le chemin d'origine — signe frequent d'un lien mort renvoye vers la page d'accueil
    du site plutot que vers le document demande (cas constate sur santepubliquefrance.fr)."""
    if not url:
        return False

    chemin_origine = _chemin(url)
    entetes = {"User-Agent": USER_AGENT}

    try:
        reponse = requests.head(url, headers=entetes, timeout=TIMEOUT_SECONDES, allow_redirects=True)
        # Certains sites institutionnels n'implementent pas HEAD (403/405) : on retente en
        # GET plutot que de conclure a tort a un lien mort.
        if reponse.status_code in (403, 405):
            reponse = requests.get(
                url, headers=entetes, timeout=TIMEOUT_SECONDES, allow_redirects=True, stream=True,
            )
            reponse.close()
    except requests.RequestException:
        return False

    if reponse.status_code >= 400:
        return False

    chemin_final = _chemin(reponse.url)
    if chemin_origine and not chemin_final:
        return False

    return True
