"""Phase 1 de l'étape 1 : référentiel des communes d'un département.

Interroge l'API Découpage administratif (geo.api.gouv.fr) pour obtenir la
liste des communes d'un département, avec les informations nécessaires à la
phase 2 (recherche des documents d'urbanisme en vigueur) : rattachement EPCI
et, pour les communes issues d'une fusion, la liste des anciens codes INSEE
sous lesquels un document peut être resté publié.

Contrairement aux appels de la phase 2 (voir `documents_urbanisme.py`), un
échec ici n'est pas isolé à une commune : sans ce référentiel, rien n'est
exploitable en aval. `get_communes_departement` lève donc
`ReferentielCommunesIndisponible` plutôt que de retourner un résultat
d'erreur structuré ; c'est à `main.py` d'arrêter le traitement du
département sur cette exception, avec un message explicite.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

GEO_API_BASE_URL = "https://geo.api.gouv.fr"
CHAMPS_DEMANDES = "nom,code,codeDepartement,codeRegion,codeEpci,anciensCodes,deleguees"


class ReferentielCommunesIndisponible(Exception):
    """Le référentiel des communes du département n'a pas pu être récupéré."""


class FiltreCommunesInvalide(Exception):
    """`code_insee_garder` et `code_insee_exclure` ont été fournis en même
    temps à `filtrer_communes`."""


@dataclass
class Commune:
    nom: str
    code_insee: str
    code_departement: str
    code_region: str
    code_epci: str | None
    anciens_codes: list[str] = field(default_factory=list)
    # Code actuel + tous les anciens codes (commune renommée ou fusionnée)
    # sous lesquels un document d'urbanisme peut avoir été publié.
    codes_insee_a_tester: list[str] = field(default_factory=list)


def _code_insee_departement(code_departement: str) -> str:
    """Convertit le code département diagBruit (3 chiffres, zero-paddé,
    ex. "033", "002A") vers le code INSEE attendu par l'API Découpage
    administratif (2 caractères en métropole, ex. "33", "2A" ; 3 chiffres
    inchangés en outre-mer, ex. "971"). Un seul zéro de tête est retiré :
    ça suffit dans tous les cas (métropole comme Corse) et laisse les
    codes d'outre-mer, qui ne commencent jamais par 0, inchangés.
    """
    if code_departement.startswith("0"):
        return code_departement[1:]
    return code_departement


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _appeler_api_geo(code_insee_departement: str) -> list[dict]:
    url = f"{GEO_API_BASE_URL}/departements/{code_insee_departement}/communes"
    response = requests.get(url, params={"fields": CHAMPS_DEMANDES}, timeout=10)
    response.raise_for_status()
    return response.json()


def _codes_insee_a_tester(commune_brute: dict) -> list[str]:
    """Code actuel, anciens codes de la commune, puis codes des communes
    déléguées (ex-communes fusionnées) et leurs propres anciens codes.
    """
    code_actuel = commune_brute["code"]
    codes = [code_actuel]

    for ancien_code in commune_brute.get("anciensCodes") or []:
        if ancien_code not in codes:
            codes.append(ancien_code)

    for deleguee in commune_brute.get("deleguees") or []:
        code_deleguee = deleguee.get("code")
        if code_deleguee and code_deleguee not in codes:
            codes.append(code_deleguee)
        for ancien_code in deleguee.get("anciensCodes") or []:
            if ancien_code not in codes:
                codes.append(ancien_code)

    return codes


def get_communes_departement(code_departement: str) -> list[Commune]:
    """Récupère le référentiel des communes d'un département.

    Lève `ReferentielCommunesIndisponible` si l'appel échoue malgré les
    tentatives, ou si l'API ne renvoie aucune commune.
    """
    try:
        communes_brutes = _appeler_api_geo(_code_insee_departement(code_departement))
    except requests.exceptions.RequestException as exc:
        raise ReferentielCommunesIndisponible(
            f"Impossible de récupérer le référentiel des communes du "
            f"département {code_departement} depuis l'API Découpage "
            f"administratif ({GEO_API_BASE_URL}) : {exc}"
        ) from exc

    if not communes_brutes:
        raise ReferentielCommunesIndisponible(
            f"L'API Découpage administratif n'a renvoyé aucune commune pour "
            f"le département {code_departement}."
        )

    return [
        Commune(
            nom=c["nom"],
            code_insee=c["code"],
            code_departement=c.get("codeDepartement", code_departement),
            code_region=c.get("codeRegion", ""),
            code_epci=c.get("codeEpci"),
            anciens_codes=c.get("anciensCodes") or [],
            codes_insee_a_tester=_codes_insee_a_tester(c),
        )
        for c in communes_brutes
    ]


def filtrer_communes(
    communes: list[Commune],
    code_insee_garder: list[str] | None = None,
    code_insee_exclure: list[str] | None = None,
) -> list[Commune]:
    """Restreint le référentiel des communes à une liste explicite de codes
    INSEE (`code_insee_garder`), ou à l'inverse écarte une liste explicite de
    codes INSEE (`code_insee_exclure`) — jamais les deux à la fois. Les deux
    paramètres sont vides par défaut (aucun filtre appliqué).

    Sert par exemple à traiter le reste d'un département après qu'un
    territoire (ex. une métropole) en a déjà été extrait et traité
    séparément, sans redemander de document pour ses communes une seconde
    fois — filtrer ici, avant la phase 2, évite aussi les appels réseau
    inutiles vers l'EPCI/les communes déjà traités.

    Le filtre ne porte que sur le code INSEE actuel de la commune
    (`Commune.code_insee`), pas sur ses anciens codes ni sur les codes de ses
    communes déléguées (`codes_insee_a_tester`) : la liste des communes d'un
    territoire (ex. une métropole) se récupère normalement avec les codes
    INSEE actuels.

    Lève `FiltreCommunesInvalide` si les deux listes sont fournies en même
    temps.
    """
    if code_insee_garder and code_insee_exclure:
        raise FiltreCommunesInvalide(
            "code_insee_garder et code_insee_exclure ne peuvent pas être "
            "fournis en même temps : choisissez l'un ou l'autre."
        )

    if code_insee_garder:
        codes = set(code_insee_garder)
        return [c for c in communes if c.code_insee in codes]

    if code_insee_exclure:
        codes = set(code_insee_exclure)
        return [c for c in communes if c.code_insee not in codes]

    return communes
