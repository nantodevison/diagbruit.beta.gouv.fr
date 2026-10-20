"""Étape 7 — aide partagée : client Strapi (créer/mettre à jour une entrée
`noisezone-alert`), voir `docs/etape-7-conception-technique.md`.

Une entrée est identifiée par `alert_slug` (champ `uid`, unique côté Strapi).
`trouver_document_id` interroge l'API pour savoir si une entrée existe déjà
avant d'écrire — voir "Idempotence" dans la conception technique : le jeton
fourni a `find`/`findOne`/`create`/`update` (jamais `delete`), vérifié en
réel le 24/08/2026.

Toute entrée créée reste en brouillon (`draftAndPublish` actif sur ce
content-type) : ce module ne publie jamais — l'opérateur relit et publie
manuellement dans Strapi.

`title` est renseigné à partir de
`titre_propose`, généré par LLM à l'étape 5 et validé par l'opérateur —
`alert_slug` (champ `uid`, `targetField: title` côté schéma Strapi) continue
d'être fourni explicitement dans le payload plutôt que dérivé de `title`.

**Piège vérifié en réel le 24/08/2026** : un `POST`/`PUT` sans le paramètre
de requête `status=draft` **publie l'entrée immédiatement**, y compris sans
jamais passer `publishedAt` dans le corps — constaté sur une vraie création
(`publishedAt` non nul dans la réponse). Documenté comme un piège connu de
l'API REST de Strapi 5 (le contrôle fiable du statut de brouillon ne passe,
côté documentation officielle, que par l'API interne *Document Service*,
inaccessible à un client REST externe comme celui-ci). Contournement
vérifié en réel : passer `status=draft` en paramètre de requête sur
`POST`/`PUT` — `_post`/`_put` le font systématiquement ci-dessous.

**Deux environnements (depuis le 04/09/2026)** : `--environnement preprod|prod`
(voir `inserer.py`) sélectionne les variables à lire —
`STRAPI_PREPROD_API_TOKEN`/`STRAPI_PREPROD_URL` ou `STRAPI_PROD_API_TOKEN`/
`STRAPI_PROD_URL` — jamais un nom de variable fixe : `_nom_variable` fait la
traduction. Toutes les fonctions de ce module qui touchent le réseau
prennent donc `environnement` en paramètre explicite plutôt qu'un état
global, pour ne jamais mélanger les deux par erreur au sein d'un même run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

CONTENT_TYPE = "noisezone-alerts"
ENVIRONNEMENTS = ("preprod", "prod")


class ConfigurationStrapiManquante(Exception):
    """`STRAPI_{PREPROD,PROD}_API_TOKEN` ou `STRAPI_{PREPROD,PROD}_URL` absent de l'environnement."""


def verifier_configuration(environnement: str) -> None:
    """Lève `ConfigurationStrapiManquante` tôt si la configuration manque —
    à appeler avant de traiter la moindre ligne, plutôt que de le découvrir
    au milieu d'un run."""
    _jeton(environnement)
    _base_url(environnement)


def _nom_variable(suffixe: str, environnement: str) -> str:
    return f"STRAPI_{environnement.upper()}_{suffixe}"


def _base_url(environnement: str) -> str:
    nom = _nom_variable("URL", environnement)
    url = os.environ.get(nom)
    if not url:
        raise ConfigurationStrapiManquante(f"{nom} n'est pas définie. Voir docs/etape-7-conception-technique.md.")
    return url.rstrip("/")


def _jeton(environnement: str) -> str:
    nom = _nom_variable("API_TOKEN", environnement)
    jeton = os.environ.get(nom)
    if not jeton:
        raise ConfigurationStrapiManquante(f"{nom} n'est pas définie. Voir docs/etape-7-conception-technique.md.")
    return jeton


def _headers(environnement: str) -> dict:
    return {"Authorization": f"Bearer {_jeton(environnement)}"}


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _get(url: str, params: dict, environnement: str) -> dict:
    response = requests.get(url, headers=_headers(environnement), params=params, timeout=15)
    response.raise_for_status()
    return response.json()


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _post(url: str, payload: dict, environnement: str) -> dict:
    # status=draft : sans ce paramètre, Strapi publie l'entrée immédiatement
    # à la création — voir la note en tête de module.
    response = requests.post(
        url,
        headers={**_headers(environnement), "Content-Type": "application/json"},
        params={"status": "draft"},
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _put(url: str, payload: dict, environnement: str) -> dict:
    # status=draft : une mise à jour republierait sinon une entrée qu'un
    # opérateur aurait remise en brouillon entre-temps — voir la note en
    # tête de module.
    response = requests.put(
        url,
        headers={**_headers(environnement), "Content-Type": "application/json"},
        params={"status": "draft"},
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def convertir_content_html(message_content: str) -> str:
    """`message_content` (texte brut, `\\n`) → `content` (HTML, CKEditor) :
    un unique `<p>`, chaque retour à la ligne remplacé par `<br>` — voir
    `docs/etape-7-conception-technique.md`, "Conversion
    content". Ni gras ni listes structurées, voir
    `docs/ameliorations-identifiees.md`."""
    corps = message_content.replace("\n", "<br>")
    return f"<p>{corps}</p>"


class DoublonStrapi(Exception):
    """Plusieurs documents Strapi portent le même `alert_slug` — écrire
    dans l'un laisserait l'autre silencieusement obsolète (voir
    `trouver_document_id`). À nettoyer à la main dans l'admin Strapi."""


def _chercher(alert_slug: str, status: str, environnement: str) -> set[str]:
    """`documentId` de toutes les entrées portant `alert_slug` pour ce
    statut — un ensemble, jamais seulement le premier résultat."""
    donnees = _get(
        f"{_base_url(environnement)}/api/{CONTENT_TYPE}",
        params={"filters[alert_slug][$eq]": alert_slug, "status": status},
        environnement=environnement,
    )
    return {resultat["documentId"] for resultat in donnees.get("data") or []}


@dataclass
class EtatEntree:
    """État d'une entrée Strapi pour un `alert_slug` donné.

    Rappel "draft and publish" (Strapi 5, `draftAndPublish: true` sur ce
    content-type) : un document jamais publié n'a qu'une version brouillon ;
    un document publié a deux versions, brouillon et publiée, qui partagent
    le même `documentId`. Le front (FastAPI) ne lit que les publiées."""

    document_id: str | None
    brouillon: bool
    publie: bool


def etat_entree(alert_slug: str, environnement: str) -> EtatEntree:
    """Cherche l'entrée portant `alert_slug`, parmi les brouillons **et**
    parmi les publiées, et lève `DoublonStrapi` si plusieurs documents
    distincts la portent.

    **Piège corrigé le 24/08/2026, après avoir créé 19 doublons en réel** :
    une requête sans paramètre `status` ne cherche, par défaut, que parmi
    les entrées **publiées** — comme ce script ne crée jamais que des
    brouillons (voir `creer_ou_mettre_a_jour`), une recherche sans ce
    paramètre ne trouvait jamais rien et déclenchait une création à chaque
    appel.

    **Recherche stricte (20/10/2026)** : la version précédente ne gardait
    que le premier résultat. Avec un slug en double (doublons résiduels du
    24/08), une seule des entrées était mise à jour, l'autre restait
    obsolète sans que rien ne le signale."""
    brouillons = _chercher(alert_slug, "draft", environnement)
    publies = _chercher(alert_slug, "published", environnement)
    documents = brouillons | publies
    if len(documents) > 1:
        raise DoublonStrapi(
            f"{len(documents)} documents Strapi/{environnement} portent alert_slug={alert_slug!r} : "
            f"{', '.join(sorted(documents))} — à dédoublonner dans l'admin Strapi avant tout envoi."
        )
    document_id = next(iter(documents), None)
    return EtatEntree(document_id=document_id, brouillon=bool(brouillons), publie=bool(publies))


def trouver_document_id(alert_slug: str, environnement: str) -> str | None:
    """`documentId` (Strapi 5 — une chaîne, pas l'`id` numérique) de
    l'entrée portant `alert_slug`, ou `None` si aucune ne correspond. Lève
    `DoublonStrapi` si plusieurs documents la portent (voir `etat_entree`)."""
    return etat_entree(alert_slug, environnement).document_id


def lister_entrees(status: str, environnement: str) -> list[dict]:
    """Toutes les entrées du content-type pour un statut (`draft` ou
    `published`), page par page — lecture seule, utilisée par le mode
    `--audit` de `inserer.py`. Chaque élément porte au moins `documentId`
    et `alert_slug`."""
    entrees: list[dict] = []
    page = 1
    while True:
        donnees = _get(
            f"{_base_url(environnement)}/api/{CONTENT_TYPE}",
            params={
                "status": status,
                "fields[0]": "alert_slug",
                "pagination[page]": page,
                "pagination[pageSize]": 100,
            },
            environnement=environnement,
        )
        entrees.extend(donnees.get("data") or [])
        nb_pages = ((donnees.get("meta") or {}).get("pagination") or {}).get("pageCount", 1)
        if page >= nb_pages:
            return entrees
        page += 1


@dataclass
class ChampsNoisezoneAlert:
    alert_slug: str
    title: str
    message_content: str
    source: str
    reference: str
    label: str


def _payload(champs: ChampsNoisezoneAlert) -> dict:
    return {
        "data": {
            "alert_slug": champs.alert_slug,
            "title": champs.title,
            "content": convertir_content_html(champs.message_content),
            "source": champs.source,
            "reference": champs.reference,
            "label": champs.label,
        }
    }


def creer_ou_mettre_a_jour(champs: ChampsNoisezoneAlert, environnement: str) -> tuple[str, bool]:
    """Crée l'entrée si `alert_slug` n'existe pas encore, la met à jour
    sinon. Retourne `(documentId, cree)` — `cree` vrai pour une nouvelle
    entrée, faux pour une mise à jour. Lève `DoublonStrapi` sans rien
    écrire si plusieurs documents portent déjà ce slug.

    Une mise à jour (`PUT ... ?status=draft`) ne modifie que la version
    brouillon : si l'entrée est déjà publiée, sa version publiée — celle
    que lit le front — reste l'ancienne jusqu'à une republication manuelle
    dans l'admin Strapi."""
    document_id = trouver_document_id(champs.alert_slug, environnement)
    url_collection = f"{_base_url(environnement)}/api/{CONTENT_TYPE}"
    if document_id:
        _put(f"{url_collection}/{document_id}", _payload(champs), environnement)
        return document_id, False
    reponse = _post(url_collection, _payload(champs), environnement)
    return reponse["data"]["documentId"], True
