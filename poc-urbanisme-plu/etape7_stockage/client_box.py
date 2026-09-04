"""Étape 7 — aide partagée : client Box (déposer une géométrie dans un
dossier Box et retourner son URL), voir `docs/etape-7-conception-technique.md`.

Authentification en Client Credentials Grant (CCG), à l'échelle de
l'entreprise Box — même mécanisme que `dagster/src/dagster_project/defs/resources/box.py`,
réimplémenté ici en REST brut (`requests`) plutôt qu'avec le SDK
`box_sdk_gen` : étape 7 reste sans dépendance nouvelle, même choix que pour
Strapi/Notion (voir `etape-7-conception-technique.md`, "Dépendances
retenues").

Le dossier Box cible est un dossier par territoire (`--box-folder-id`,
voir `inserer.py`) : jamais résolu automatiquement depuis les données,
toujours fourni explicitement par l'opérateur.

**URL retournée** : `https://app.box.com/file/{id}`, l'URL native de la
page Box du fichier — pas un *shared link* (`.../s/...`), qui nécessiterait
d'activer explicitement le partage public du fichier.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

BOX_API_BASE = "https://api.box.com/2.0"
BOX_UPLOAD_BASE = "https://upload.box.com/api/2.0"
BOX_OAUTH_URL = "https://api.box.com/oauth2/token"


class ConfigurationBoxManquante(Exception):
    """`BOX_CLIENT_ID`/`BOX_CLIENT_SECRET`/`BOX_ENTREPRISE_ID` absent de l'environnement."""


def verifier_configuration() -> None:
    """Lève `ConfigurationBoxManquante` tôt si la configuration manque —
    à appeler avant de traiter la moindre ligne, même principe que
    `client_strapi.verifier_configuration`/`client_notion.verifier_configuration`."""
    _client_id()
    _client_secret()
    _entreprise_id()


def _client_id() -> str:
    valeur = os.environ.get("BOX_CLIENT_ID")
    if not valeur:
        raise ConfigurationBoxManquante(
            "BOX_CLIENT_ID n'est pas définie. Voir docs/etape-7-conception-technique.md."
        )
    return valeur


def _client_secret() -> str:
    valeur = os.environ.get("BOX_CLIENT_SECRET")
    if not valeur:
        raise ConfigurationBoxManquante(
            "BOX_CLIENT_SECRET n'est pas définie. Voir docs/etape-7-conception-technique.md."
        )
    return valeur


def _entreprise_id() -> str:
    valeur = os.environ.get("BOX_ENTREPRISE_ID")
    if not valeur:
        raise ConfigurationBoxManquante(
            "BOX_ENTREPRISE_ID n'est pas définie. Voir docs/etape-7-conception-technique.md."
        )
    return valeur


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _demander_jeton() -> dict:
    response = requests.post(
        BOX_OAUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "box_subject_type": "enterprise",
            "box_subject_id": _entreprise_id(),
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


_cache_jeton: tuple[str, float] | None = None


def _jeton() -> str:
    """Jeton d'accès Box, mis en cache pour le run et renouvelé s'il est
    expiré (durée de vie annoncée par Box : 60 minutes, marge de 60s prise
    ici) — même logique de cache que `client_notion._data_source_id`."""
    global _cache_jeton
    if _cache_jeton is None or _cache_jeton[1] <= time.monotonic():
        reponse = _demander_jeton()
        expiration = time.monotonic() + reponse["expires_in"] - 60
        _cache_jeton = (reponse["access_token"], expiration)
    return _cache_jeton[0]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_jeton()}"}


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _lister_page_items(dossier_id: str, offset: int) -> dict:
    response = requests.get(
        f"{BOX_API_BASE}/folders/{dossier_id}/items",
        headers=_headers(),
        params={"fields": "name,type", "limit": 1000, "offset": offset},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _lister_fichiers_dossier(dossier_id: str) -> dict[str, str]:
    """Nom de fichier → id, pour tous les fichiers du dossier (pagine si
    besoin). Sert à retrouver un fichier déjà déposé par son nom, avant
    d'en uploader une nouvelle version plutôt qu'un doublon."""
    fichiers: dict[str, str] = {}
    offset = 0
    while True:
        page = _lister_page_items(dossier_id, offset)
        entrees = page.get("entries") or []
        for item in entrees:
            if item.get("type") == "file":
                fichiers[item["name"]] = item["id"]
        offset += len(entrees)
        if offset >= page.get("total_count", offset) or not entrees:
            break
    return fichiers


_cache_index_dossiers: dict[str, dict[str, str]] = {}


def _index_dossier(dossier_id: str) -> dict[str, str]:
    """Index nom → id du dossier, mis en cache pour le run (un seul listing
    par dossier plutôt qu'un par géométrie) et mis à jour localement à
    chaque nouvel upload, voir `televerser_geometrie`."""
    if dossier_id not in _cache_index_dossiers:
        _cache_index_dossiers[dossier_id] = _lister_fichiers_dossier(dossier_id)
    return _cache_index_dossiers[dossier_id]


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _uploader_nouveau(dossier_id: str, nom_fichier: str, contenu: bytes) -> str:
    response = requests.post(
        f"{BOX_UPLOAD_BASE}/files/content",
        headers=_headers(),
        data={"attributes": json.dumps({"name": nom_fichier, "parent": {"id": dossier_id}})},
        files={"file": (nom_fichier, contenu, "application/geo+json")},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["entries"][0]["id"]


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _uploader_nouvelle_version(fichier_id: str, nom_fichier: str, contenu: bytes) -> str:
    response = requests.post(
        f"{BOX_UPLOAD_BASE}/files/{fichier_id}/content",
        headers=_headers(),
        files={"file": (nom_fichier, contenu, "application/geo+json")},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["entries"][0]["id"]


def televerser_geometrie(chemin_geojson: Path, dossier_id: str) -> str:
    """Dépose (ou met à jour) un `.geojson` dans le dossier Box `dossier_id`
    et retourne l'URL de la page Box du fichier. Idempotent par nom de
    fichier au sein du dossier : une géométrie déjà déposée est mise à jour
    (nouvelle version) plutôt que dupliquée."""
    contenu = chemin_geojson.read_bytes()
    nom_fichier = chemin_geojson.name

    index = _index_dossier(dossier_id)
    fichier_id = index.get(nom_fichier)
    if fichier_id:
        fichier_id = _uploader_nouvelle_version(fichier_id, nom_fichier, contenu)
    else:
        fichier_id = _uploader_nouveau(dossier_id, nom_fichier, contenu)
        index[nom_fichier] = fichier_id

    return f"https://app.box.com/file/{fichier_id}"
