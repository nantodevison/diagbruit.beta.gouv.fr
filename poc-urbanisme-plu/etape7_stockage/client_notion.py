"""Étape 7 — aide partagée : client Notion (créer/mettre à jour une page,
géométrie référencée en pièce jointe), base "Données réglementaires locales
(PLU, PPBE, …)" — voir `docs/etape-7-conception-technique.md`.

Une page est identifiée par sa propriété `alert_slug` (texte, pas de
contrainte d'unicité native contrairement à Strapi) : `trouver_page_id`
interroge l'API avant d'écrire pour savoir si une page existe déjà —
l'intégration a les droits de lecture, vérifié en réel le 24/08/2026.

**Migration `data_sources` (constatée le 24/08/2026)** : depuis la version
d'API `2025-09-03`, `POST /v1/databases/{id}/query` n'existe plus (une base
Notion peut désormais contenir plusieurs "sources de données" ; interroger
ses lignes et y créer une page se font via un `data_source_id` distinct du
`database_id`, retrouvé une fois via `GET /v1/databases/{NOTION_DATABASE_ID}`
puis mis en cache pour le reste du run). `NOTION_DATABASE_ID` reste
l'identifiant à renseigner dans `.env` (le seul visible depuis l'URL Notion),
`_data_source_id()` fait la traduction.

**Géométrie en lien externe (depuis le 04/09/2026)** : la propriété `data`
(Files & media) ne reçoit plus le `.geojson` en pièce jointe uploadée
(`file_upload`, expirant au bout d'une heure si non attachée) mais un lien
externe (`external`) vers le fichier déposé sur Box par `client_box.py` —
Notion accepte les deux types d'entrée dans une propriété Files & media,
aucun changement de schéma nécessaire côté base Notion.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

NOTION_API_BASE = "https://api.notion.com/v1"
# Version d'API vérifiée en réel le 23/08/2026 — voir "Migration data_sources" ci-dessus.
NOTION_VERSION = "2026-03-11"


class ConfigurationNotionManquante(Exception):
    """`PERSONNAL_NOTION_TOKEN` ou `NOTION_DATABASE_ID` absent de l'environnement."""


def verifier_configuration() -> None:
    """Lève `ConfigurationNotionManquante` tôt si la configuration manque,
    ou si la base Notion est inaccessible/n'a pas de source de données — à
    appeler avant de traiter la moindre ligne plutôt que de le découvrir au
    milieu d'un run."""
    _jeton()
    _database_id()
    _data_source_id()


def _jeton() -> str:
    jeton = os.environ.get("PERSONNAL_NOTION_TOKEN")
    if not jeton:
        raise ConfigurationNotionManquante(
            "PERSONNAL_NOTION_TOKEN n'est pas définie. Voir docs/etape-7-conception-technique.md."
        )
    return jeton


def _database_id() -> str:
    id_base = os.environ.get("NOTION_DATABASE_ID")
    if not id_base:
        raise ConfigurationNotionManquante(
            "NOTION_DATABASE_ID n'est pas définie. Voir docs/etape-7-conception-technique.md."
        )
    return id_base


def _headers_json() -> dict:
    return {"Authorization": f"Bearer {_jeton()}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"}


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _get_json(url: str) -> dict:
    response = requests.get(url, headers=_headers_json(), timeout=15)
    response.raise_for_status()
    return response.json()


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _post_json(url: str, payload: dict) -> dict:
    response = requests.post(url, headers=_headers_json(), json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _patch_json(url: str, payload: dict) -> dict:
    response = requests.patch(url, headers=_headers_json(), json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


_cache_data_source_id: str | None = None


def _data_source_id() -> str:
    """Traduit `NOTION_DATABASE_ID` (celui de l'URL Notion) en identifiant
    de source de données, requis par l'API depuis la version `2025-09-03`
    — voir la note "Migration data_sources" en tête de module. Mis en cache
    pour le run : ne change jamais en cours de route, inutile de le
    redemander à chaque ligne."""
    global _cache_data_source_id
    if _cache_data_source_id is None:
        base = _get_json(f"{NOTION_API_BASE}/databases/{_database_id()}")
        sources = base.get("data_sources") or []
        if not sources:
            raise ConfigurationNotionManquante(
                f"Aucune source de données trouvée pour la base Notion {_database_id()}."
            )
        _cache_data_source_id = sources[0]["id"]
    return _cache_data_source_id


def trouver_page_id(alert_slug: str) -> str | None:
    """Cherche une page existante par `alert_slug`. Retourne son `id`, ou
    `None` si aucune page ne correspond."""
    payload = {"filter": {"property": "alert_slug", "rich_text": {"equals": alert_slug}}}
    donnees = _post_json(f"{NOTION_API_BASE}/data_sources/{_data_source_id()}/query", payload)
    resultats = donnees.get("results") or []
    return resultats[0]["id"] if resultats else None


@dataclass
class ChampsPageNotion:
    territoire: str
    description: str
    alert_slug: str
    url_geometrie: str
    nom_fichier: str


def _proprietes(champs: ChampsPageNotion) -> dict:
    return {
        "Territoire": {"title": [{"text": {"content": champs.territoire}}]},
        "Description": {"rich_text": [{"text": {"content": champs.description}}]},
        "alert_slug": {"rich_text": [{"text": {"content": champs.alert_slug}}]},
        "data": {
            "files": [
                {"type": "external", "external": {"url": champs.url_geometrie}, "name": champs.nom_fichier}
            ]
        },
    }


def creer_ou_mettre_a_jour(champs: ChampsPageNotion) -> tuple[str, bool]:
    """Crée la page si `alert_slug` n'existe pas encore, la met à jour
    sinon. Retourne `(page_id, cree)` — `cree` vrai pour une nouvelle page,
    faux pour une mise à jour."""
    page_id = trouver_page_id(champs.alert_slug)
    proprietes = _proprietes(champs)
    if page_id:
        _patch_json(f"{NOTION_API_BASE}/pages/{page_id}", {"properties": proprietes})
        return page_id, False
    payload = {
        "parent": {"type": "data_source_id", "data_source_id": _data_source_id()},
        "properties": proprietes,
    }
    reponse = _post_json(f"{NOTION_API_BASE}/pages", payload)
    return reponse["id"], True


def archiver_page(page_id: str) -> None:
    """Met une page existante à la corbeille Notion — utilisé pour les
    nettoyages ponctuels, jamais appelé par `inserer.py`. `in_trash`, pas
    `archived` (retiré par la version d'API `NOTION_VERSION` : `POST` avec
    `archived` échoue en 400, `body.archived should be not present` —
    vérifié en réel le 04/09/2026)."""
    _patch_json(f"{NOTION_API_BASE}/pages/{page_id}", {"in_trash": True})
