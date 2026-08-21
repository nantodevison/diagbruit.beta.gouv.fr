"""Étape 6 — aide partagée : résolution commune → EPCI (`resolution_territoire.py`).

Pour la liste de noms de commune de la colonne `communes` d'une géométrie
finale (reprise de `etape4_{dept}.gpkg`, voir `generer_export.py`), propose
un `territoire_propose` via l'API Découpage administratif (geo.api.gouv.fr) :
nom de l'EPCI si toutes les communes de la géométrie s'y rattachent, repli
sur le(s) nom(s) de commune(s) tel(s) quel(s) sinon — voir
`docs/etape-6-mise-en-forme-diagbruit.md`, "Calcul du territoire". Jamais
imposé : reste modifiable par l'opérateur dans `etape6_{dept}_export.csv`.

Résultat mis en cache par nom de commune et par SIREN d'EPCI, pour la durée
du run (`ResolveurTerritoire`) — plusieurs géométries d'un même département
partagent souvent les mêmes communes, inutile de répéter un appel déjà fait.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

GEO_API_BASE_URL = "https://geo.api.gouv.fr"

# Séparateur constaté le 21/08/2026 sur un export réel
# (etape4_067-plui-strasbourg.gpkg, colonne `communes`) : ", " — confirme
# l'hypothèse posée comme "point ouvert" dans etape-6-conception-technique.md.
SEPARATEUR_COMMUNES = ", "


@dataclass
class _ResolutionCommune:
    code_epci: str | None
    trouvee: bool


def _code_insee_departement(code_departement: str) -> str:
    """Même conversion que `etape1_identification/communes.py`,
    `_code_insee_departement` — réimplémentée ici plutôt qu'importée (voir
    `etape-1-conception-technique.md`, "Décision 2" : chaque étape reste
    indépendante du code des autres).

    `--dept` porte parfois, en pratique, un suffixe de document après un
    tiret (ex. `067-plui-strasbourg`, convention de nommage utilisée pour
    tester les étapes 3 à 6 sur un seul document sans rejouer les étapes 1/2
    sur tout le département) : seule la partie avant le premier tiret est un
    vrai code département exploitable par l'API Découpage administratif.
    """
    code_departement = code_departement.split("-", 1)[0]
    if code_departement.startswith("0"):
        return code_departement[1:]
    return code_departement


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _chercher_commune(nom: str, code_insee_departement: str) -> list[dict]:
    response = requests.get(
        f"{GEO_API_BASE_URL}/communes",
        params={"nom": nom, "codeDepartement": code_insee_departement, "fields": "nom,code,codeEpci"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _nom_epci(siren: str) -> str | None:
    response = requests.get(f"{GEO_API_BASE_URL}/epcis/{siren}", params={"fields": "nom"}, timeout=10)
    response.raise_for_status()
    return response.json().get("nom")


class ResolveurTerritoire:
    """Résout un ensemble de communes vers un territoire proposé, avec un
    cache mémoire (communes et EPCI) partagé entre toutes les géométries
    traitées pendant le run."""

    def __init__(self, code_departement: str) -> None:
        self._code_insee_departement = _code_insee_departement(code_departement)
        self._cache_communes: dict[str, _ResolutionCommune] = {}
        self._cache_epci: dict[str, str | None] = {}

    def _resoudre_commune(self, nom: str) -> _ResolutionCommune:
        if nom in self._cache_communes:
            return self._cache_communes[nom]
        try:
            resultats = _chercher_commune(nom, self._code_insee_departement)
        except requests.exceptions.RequestException:
            # API indisponible malgré les tentatives : échec isolé à cette
            # commune, jamais fatal pour le reste du traitement (voir
            # etape-6-conception-technique.md, "Gestion des erreurs").
            resolution = _ResolutionCommune(code_epci=None, trouvee=False)
        else:
            if len(resultats) == 1:
                resolution = _ResolutionCommune(code_epci=resultats[0].get("codeEpci"), trouvee=True)
            else:
                # Nom introuvable, ou ambigu au sein du département (aucun
                # choix arbitraire à faire) : même traitement qu'une
                # indisponibilité d'API — échec de résolution pour cette commune.
                resolution = _ResolutionCommune(code_epci=None, trouvee=False)
        self._cache_communes[nom] = resolution
        return resolution

    def _resoudre_nom_epci(self, siren: str) -> str | None:
        if siren not in self._cache_epci:
            try:
                self._cache_epci[siren] = _nom_epci(siren)
            except requests.exceptions.RequestException:
                self._cache_epci[siren] = None
        return self._cache_epci[siren]

    def proposer_territoire(self, communes: list[str]) -> tuple[str, bool]:
        """Retourne `(territoire_propose, echec)`.

        `echec` est vrai si au moins une commune n'a pas pu être résolue
        (nom introuvable ou API indisponible) — `territoire_propose` vaut
        alors `""`, à charge de l'opérateur (voir "Calcul du territoire",
        point 4 de `etape-6-mise-en-forme-diagbruit.md`). Sinon, retourne le
        nom de l'EPCI commun aux communes si elles en partagent un, sinon
        le(s) nom(s) de commune(s) tel(s) quel(s) (point 3).
        """
        if not communes:
            return "", True

        resolutions = [self._resoudre_commune(nom) for nom in communes]
        if any(not r.trouvee for r in resolutions):
            return "", True

        sirens_epci = {r.code_epci for r in resolutions if r.code_epci}
        if len(sirens_epci) == 1:
            (siren,) = sirens_epci
            nom_epci = self._resoudre_nom_epci(siren)
            if nom_epci:
                return nom_epci, False

        return SEPARATEUR_COMMUNES.join(communes), False
