"""Phase 2 de l'étape 1 : recherche des documents d'urbanisme en vigueur.

Pour chaque commune du référentiel produit par `communes.py` :

1. Vérifie le statut RNU (API Carto, module GPU, couche `municipality`). Si
   la commune est au RNU, elle est classée « RNU confirmé » et aucune
   recherche de document n'est effectuée pour elle (voir phase 2.2 du
   document de cadrage).
2. Sinon, recherche le document d'urbanisme (DU) en vigueur : d'abord au
   niveau de l'EPCI de rattachement (une seule recherche par EPCI, réutilisée
   pour toutes ses communes membres — dédoublonnage 2.1), puis, si l'EPCI n'a
   pas de document ou que celui-ci ne couvre pas réellement la commune, au
   niveau de la commune elle-même (code INSEE actuel puis anciens codes).
3. Recherche systématiquement un PSMV en complément, sur le même maillage :
   s'il existe, il s'ajoute au DU trouvé (chevauchement possible) sans jamais
   le remplacer.
4. Si aucun document n'est trouvé et que la commune n'est pas RNU confirmé :
   alerte « trou de couverture GPU ».

Écart avec le document de cadrage (`etape-1-identification-documents-urbanisme-diagbruit.md`,
2.3), validé avec l'équipe : la vérification qu'un DU intercommunal couvre
bien une commune membre devait initialement s'appuyer sur le champ
`municipalities` de l'endpoint `document/{id}/details` du GPU. En pratique,
ce champ est toujours `null` sur l'API réelle (testé sur plusieurs PLUi
intercommunaux) — il n'est donc pas exploitable. La vérification est ici
faite par intersection géométrique : `apicarto.ign.fr/api/gpu/document`
(POST, paramètre `geom`) renvoie les documents dont l'emprise intersecte une
géométrie donnée. La géométrie de la commune utilisée pour ce test est celle
déjà renvoyée par l'appel RNU de l'étape 1 ci-dessus — aucun appel
supplémentaire de récupération de géométrie n'est nécessaire, et cela ne
contredit pas la décision de la phase 1 de ne pas récupérer les géométries
communales à ce stade (cette décision visait la délimitation de zone de
l'étape 3, pas la vérification de couverture ici).

Contrairement à `communes.py` (phase 1), un échec ici est toujours isolé à
une commune ou un EPCI : il est empilé dans la liste d'erreurs retournée par
`rechercher_documents_departement` et le reste du département continue
d'être traité (voir `etape-1-conception-technique.md`, décision 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .communes import Commune

APICARTO_GPU_BASE_URL = "https://apicarto.ign.fr/api/gpu"
GPU_DOCUMENT_SEARCH_URL = "https://www.geoportail-urbanisme.gouv.fr/api/document"

STATUT_RNU_CONFIRME = "RNU confirmé"
STATUT_DOCUMENT_TROUVE = "document trouvé"
STATUT_PSMV_ADDITIONNEL = "PSMV additionnel"
STATUT_TROU_DE_COUVERTURE = "trou de couverture"

NIVEAU_EPCI = "EPCI"
NIVEAU_COMMUNE = "commune"


@dataclass
class DocumentTrouve:
    nom_document: str
    nature_document: str  # PLU, PLUi, PLUm, POS, CC, PSMV (valeur du champ `type` du GPU)
    id_gpu: str
    date_approbation: str | None
    niveau_couverture: str  # NIVEAU_EPCI ou NIVEAU_COMMUNE
    code_insee_utilise: str  # code (actuel ou ancien) sous lequel le document a été trouvé
    lien_reglement: str | None
    statut: str  # STATUT_DOCUMENT_TROUVE ou STATUT_PSMV_ADDITIONNEL


@dataclass
class ResultatCommune:
    commune: Commune
    documents: list[DocumentTrouve] = field(default_factory=list)
    rnu_confirme: bool = False
    trou_de_couverture: bool = False


@dataclass
class ErreurTraitement:
    code_insee_commune: str
    nom_commune: str
    phase: str
    type_erreur: str
    message: str


class _ErreurAppelGPU(Exception):
    """Erreur réseau/HTTP lors d'un appel API, après épuisement des tentatives."""


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _get(url: str, params: dict) -> requests.Response:
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _post(url: str, json_body: dict) -> requests.Response:
    response = requests.post(url, json=json_body, timeout=30)
    response.raise_for_status()
    return response


def _verifier_rnu(code_insee: str) -> tuple[bool, dict]:
    """Retourne (is_rnu, géométrie de la commune)."""
    try:
        response = _get(f"{APICARTO_GPU_BASE_URL}/municipality", {"insee": code_insee})
        features = response.json().get("features", [])
    except requests.exceptions.RequestException as exc:
        raise _ErreurAppelGPU(f"couche municipality indisponible : {exc}") from exc

    if not features:
        raise _ErreurAppelGPU("commune introuvable dans la couche municipality du GPU")

    feature = features[0]
    return bool(feature["properties"]["is_rnu"]), feature["geometry"]


def _grid_inconnue(response: requests.Response) -> bool:
    """Le GPU répond 400 (et non une liste vide) quand `grid` ne correspond à
    aucune entrée de sa table des maillages — ce qui arrive couramment pour un
    ancien code INSEE absorbé par une fusion, ou un EPCI non compétent en
    urbanisme. Ce n'est pas une erreur : ça équivaut à « aucun document ».
    """
    try:
        violations = response.json().get("violations", [])
    except ValueError:
        return False
    return any(v.get("property") == "grid" for v in violations)


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _rechercher_documents_bruts(grid: str, document_family: str) -> list[dict]:
    response = requests.get(
        GPU_DOCUMENT_SEARCH_URL,
        params={"grid": grid, "documentFamily[]": document_family, "status": "document.production"},
        timeout=15,
    )
    if response.status_code == 400 and _grid_inconnue(response):
        return []
    response.raise_for_status()
    return response.json()


def _rechercher_documents(grid: str, document_family: str) -> list[dict]:
    """Documents en vigueur (status=document.production) pour un maillage
    (SIREN EPCI ou code INSEE commune) et une famille de document (DU ou PSMV).
    """
    try:
        return _rechercher_documents_bruts(grid, document_family)
    except requests.exceptions.RequestException as exc:
        raise _ErreurAppelGPU(f"recherche de document ({document_family}, grid={grid}) : {exc}") from exc


def _document_couvre_geometrie(document_id: str, geometrie: dict) -> bool:
    """Vérifie par intersection géométrique qu'un document couvre bien une géométrie
    donnée (voir la note en tête de fichier sur l'écart avec le cadrage initial).
    """
    try:
        response = _post(f"{APICARTO_GPU_BASE_URL}/document", {"geom": geometrie})
        ids_trouves = {f["properties"]["id"] for f in response.json().get("features", [])}
        return document_id in ids_trouves
    except requests.exceptions.RequestException as exc:
        raise _ErreurAppelGPU(f"vérification de couverture du document {document_id} : {exc}") from exc


def _details_document(document_id: str) -> dict:
    try:
        response = _get(f"{GPU_DOCUMENT_SEARCH_URL}/{document_id}/details", {})
        return response.json()
    except requests.exceptions.RequestException as exc:
        raise _ErreurAppelGPU(f"détails du document {document_id} : {exc}") from exc


def _lien_reglement(writing_materials: dict) -> str | None:
    """Le PDF du règlement écrit, à l'exclusion des planches graphiques et des
    autres pièces du dossier (rapport, PADD, OAP...).
    """
    for nom_fichier, url in writing_materials.items():
        if "_reglement_" in nom_fichier and "_reglement_graphique_" not in nom_fichier:
            return url
    return None


def _construire_document_trouve(
    document_brut: dict, niveau_couverture: str, code_insee_utilise: str, statut: str
) -> DocumentTrouve:
    details = _details_document(document_brut["id"])
    return DocumentTrouve(
        nom_document=details.get("title") or document_brut.get("name", ""),
        nature_document=document_brut.get("type", ""),
        id_gpu=document_brut["id"],
        date_approbation=details.get("publicationDate"),
        niveau_couverture=niveau_couverture,
        code_insee_utilise=code_insee_utilise,
        lien_reglement=_lien_reglement(details.get("writingMaterials") or {}),
        statut=statut,
    )


def _trouver_document_pour_commune(
    commune: Commune,
    document_family: str,
    geometrie_commune: dict,
    documents_epci: list[dict] | None,
) -> tuple[DocumentTrouve | None, list[ErreurTraitement]]:
    """Recherche un document (DU ou PSMV) pour une commune : niveau EPCI
    d'abord (avec vérification de couverture géométrique), puis repli sur le
    niveau commune (code actuel, puis anciens codes).
    """
    erreurs: list[ErreurTraitement] = []
    statut = STATUT_DOCUMENT_TROUVE if document_family == "DU" else STATUT_PSMV_ADDITIONNEL

    if documents_epci:
        document_brut = documents_epci[0]
        try:
            couvre = _document_couvre_geometrie(document_brut["id"], geometrie_commune)
        except _ErreurAppelGPU as exc:
            erreurs.append(
                ErreurTraitement(
                    commune.code_insee, commune.nom, "2.3-couverture", document_family, str(exc)
                )
            )
            couvre = False  # on ne peut pas confirmer la couverture : on tente le repli commune

        if couvre:
            try:
                document = _construire_document_trouve(
                    document_brut, NIVEAU_EPCI, commune.code_insee, statut
                )
                return document, erreurs
            except _ErreurAppelGPU as exc:
                erreurs.append(
                    ErreurTraitement(commune.code_insee, commune.nom, "2.3-details", document_family, str(exc))
                )
                return None, erreurs

    # Repli niveau commune : code actuel puis anciens codes (commune fusionnée).
    for code in commune.codes_insee_a_tester:
        try:
            documents_commune = _rechercher_documents(code, document_family)
        except _ErreurAppelGPU as exc:
            erreurs.append(
                ErreurTraitement(commune.code_insee, commune.nom, "2.3-commune", document_family, str(exc))
            )
            continue

        if documents_commune:
            try:
                document = _construire_document_trouve(
                    documents_commune[0], NIVEAU_COMMUNE, code, statut
                )
                return document, erreurs
            except _ErreurAppelGPU as exc:
                erreurs.append(
                    ErreurTraitement(commune.code_insee, commune.nom, "2.3-details", document_family, str(exc))
                )
                return None, erreurs

    return None, erreurs


def rechercher_documents_departement(
    communes: list[Commune],
) -> tuple[list[ResultatCommune], list[ErreurTraitement]]:
    """Traite l'ensemble des communes d'un département (phase 2 complète).

    Ne lève jamais d'exception : toute erreur isolée est empilée dans la
    liste d'erreurs retournée, le reste du département continue d'être
    traité (décision 4 du document de conception technique).
    """
    resultats: list[ResultatCommune] = []
    erreurs: list[ErreurTraitement] = []

    # 2.1 — dédoublonnage des EPCI : chaque EPCI n'est interrogé qu'une fois,
    # le résultat est réutilisé pour toutes ses communes membres.
    epcis_uniques = {c.code_epci for c in communes if c.code_epci}
    documents_par_epci: dict[str, dict[str, list[dict]]] = {}
    for epci in epcis_uniques:
        documents_par_epci[epci] = {}
        for document_family in ("DU", "PSMV"):
            try:
                documents_par_epci[epci][document_family] = _rechercher_documents(epci, document_family)
            except _ErreurAppelGPU as exc:
                erreurs.append(ErreurTraitement("", f"EPCI {epci}", "2.3-epci", document_family, str(exc)))
                documents_par_epci[epci][document_family] = []

    for commune in communes:
        # 2.2 — statut RNU (donne aussi la géométrie, réutilisée pour la
        # vérification de couverture ci-dessous).
        try:
            is_rnu, geometrie_commune = _verifier_rnu(commune.code_insee)
        except _ErreurAppelGPU as exc:
            erreurs.append(ErreurTraitement(commune.code_insee, commune.nom, "2.2", "rnu", str(exc)))
            continue  # sans statut RNU ni géométrie, rien d'exploitable pour cette commune

        if is_rnu:
            resultats.append(ResultatCommune(commune=commune, rnu_confirme=True))
            continue

        documents_epci_commune = documents_par_epci.get(commune.code_epci, {}) if commune.code_epci else {}

        # 2.3 — document d'urbanisme (DU).
        document_du, erreurs_du = _trouver_document_pour_commune(
            commune, "DU", geometrie_commune, documents_epci_commune.get("DU")
        )
        erreurs.extend(erreurs_du)

        # 2.4 — PSMV en complément, systématique, sur le même maillage.
        document_psmv, erreurs_psmv = _trouver_document_pour_commune(
            commune, "PSMV", geometrie_commune, documents_epci_commune.get("PSMV")
        )
        erreurs.extend(erreurs_psmv)

        documents_trouves = [d for d in (document_du, document_psmv) if d is not None]

        # 2.5 — cas résiduel : ni DU ni PSMV, et commune non RNU.
        resultats.append(
            ResultatCommune(
                commune=commune,
                documents=documents_trouves,
                trou_de_couverture=not documents_trouves,
            )
        )

    return resultats, erreurs
