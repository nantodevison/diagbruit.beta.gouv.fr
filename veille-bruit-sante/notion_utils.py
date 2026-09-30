"""Outils Notion partagés : résolution database_id -> data_source_id, et repérage des
fiches ajoutées à la main (marquer_ajouts_manuels).

Depuis la mise à jour de l'API Notion (version 2025-09-03), une base ("database") peut
contenir plusieurs "data sources" ; le schéma de colonnes et les pages vivent sur le data
source, pas directement sur la base — `databases.query` n'existe plus dans le SDK,
`data_sources.query` le remplace, et la création d'une page attend un `data_source_id` en
parent, pas un `database_id`.

Ce projet ne crée jamais qu'un seul data source par base (voir
`etape1_base_notion/creer_base_notion.py`) : NOTION_DATABASE_ID reste l'identifiant que
l'utilisateur copie depuis l'URL Notion. En pratique, selon la façon dont on copie cette
URL dans l'interface Notion, l'identifiant obtenu est parfois celui de la base, parfois
déjà celui de son data source (constaté à l'usage, pas documenté par Notion) — la
résolution accepte donc les deux plutôt que d'exiger que l'utilisateur distingue les deux
notions à chaque fois.
"""
from notion_client import Client
from notion_client.errors import APIErrorCode, APIResponseError


def resoudre_data_source_id(notion: Client, identifiant: str) -> str:
    try:
        base = notion.databases.retrieve(database_id=identifiant)
    except APIResponseError as erreur:
        if erreur.code != APIErrorCode.ObjectNotFound:
            raise
        # Pas une base : peut-être déjà un data_source_id. Le retrieve suivant lève
        # lui-même une erreur claire si l'identifiant n'est ni l'un ni l'autre.
        notion.data_sources.retrieve(data_source_id=identifiant)
        return identifiant

    data_sources = base.get("data_sources") or []
    if not data_sources:
        raise RuntimeError(f"Aucun data source trouve pour la base Notion {identifiant}")
    return data_sources[0]["id"]


def marquer_ajouts_manuels(notion: Client, data_source_id: str) -> int:
    """Coche `ajout_manuel` sur toute fiche créée à la main dans Notion, c'est-à-dire par
    quelqu'un d'autre que l'intégration du script. Notion enregistre l'auteur de chaque
    page (`created_by`) : la détection est automatique, l'utilisateur n'a rien à cocher.

    N'écrit que la colonne `ajout_manuel`, et seulement quand elle n'est pas déjà cochée.
    Retourne le nombre de fiches nouvellement marquées. Voir etape-1-conception-technique.md,
    Décision 3 (date de départ de la recherche)."""
    id_integration = notion.users.me()["id"]
    nb_marquees, curseur = 0, None
    while True:
        reponse = notion.data_sources.query(
            data_source_id=data_source_id, start_cursor=curseur, page_size=100,
            filter={"property": "ajout_manuel", "checkbox": {"equals": False}},
        )
        for page in reponse["results"]:
            if page["created_by"]["id"] != id_integration:
                notion.pages.update(page_id=page["id"], properties={"ajout_manuel": {"checkbox": True}})
                nb_marquees += 1
        if not reponse.get("has_more"):
            return nb_marquees
        curseur = reponse.get("next_cursor")
