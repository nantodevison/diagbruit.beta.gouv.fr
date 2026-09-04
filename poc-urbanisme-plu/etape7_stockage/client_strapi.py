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


def _chercher(alert_slug: str, status: str, environnement: str) -> str | None:
    donnees = _get(
        f"{_base_url(environnement)}/api/{CONTENT_TYPE}",
        params={"filters[alert_slug][$eq]": alert_slug, "status": status},
        environnement=environnement,
    )
    resultats = donnees.get("data") or []
    return resultats[0]["documentId"] if resultats else None


def trouver_document_id(alert_slug: str, environnement: str) -> str | None:
    """Cherche une entrée existante par `alert_slug`, brouillon ou publiée.
    Retourne son `documentId` (Strapi 5 — une chaîne, pas l'`id` numérique),
    ou `None` si aucune entrée ne correspond.

    **Piège corrigé le 24/08/2026, après avoir créé 19 doublons en réel** :
    une requête sans paramètre `status` ne cherche, par défaut, que parmi
    les entrées **publiées** — comme ce script ne crée jamais que des
    brouillons (voir `creer_ou_mettre_a_jour`), une recherche sans ce
    paramètre ne trouve jamais rien et déclenche une création à chaque
    appel, même pour une entrée déjà existante. Cherche donc d'abord parmi
    les brouillons, puis parmi les publiées (utile si l'opérateur a publié
    l'entrée entre deux passages du script) — les deux peuvent légitimement
    coexister avec le même `documentId` (document publié puis retouché).
    """
    return _chercher(alert_slug, "draft", environnement) or _chercher(alert_slug, "published", environnement)


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
    entrée, faux pour une mise à jour."""
    document_id = trouver_document_id(champs.alert_slug, environnement)
    url_collection = f"{_base_url(environnement)}/api/{CONTENT_TYPE}"
    if document_id:
        _put(f"{url_collection}/{document_id}", _payload(champs), environnement)
        return document_id, False
    reponse = _post(url_collection, _payload(champs), environnement)
    return reponse["data"]["documentId"], True
