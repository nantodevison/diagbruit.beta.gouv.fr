"""Création ponctuelle de la base Notion "Études" — voir docs/etape-1-conception-technique.md,
Décision 4. Exécution manuelle, une seule fois, hors de la boucle hebdomadaire :

    python -m etape1_base_notion.creer_base_notion <id_page_notion_parente>
"""
import argparse
import os

from dotenv import load_dotenv
from notion_client import Client

# Options fermées, réutilisées telles quelles par etape2_recherche_extraction/extraction.py
# (Literal du modèle Pydantic) pour garantir que le modèle ne produit jamais une valeur hors
# de cette liste — voir etape-2-conception-technique.md, corrigé après le premier essai réel
# (le modèle produisait des valeurs libres avec virgules, rejetées par Notion : un
# multi_select/select ne peut pas contenir de virgule dans le nom d'une option).
OPTIONS_DOMAINE_SANTE = (
    "Cardiovasculaire", "Sante mentale", "Cognition", "Metabolique", "Sommeil", "Enfant",
)
OPTIONS_SOURCE_BRUIT = ("Routier", "Aerien", "Ferroviaire", "Industriel")

# Trace le process qui a produit doi_url, pour reperer en un coup d'oeil les URL les moins
# fiables (celles qu'un LLM a proposees ou trouvees en recherche web, jamais verifiees a la
# source, par opposition a celles issues telles quelles d'une API scientifique structuree) —
# voir etape3_integration_notion/verification_url.py pour le controle qui accompagne ce champ.
OPTIONS_URL_SOURCE = ("API metier", "Claude_web_search", "Claude_LLM")

# Colonnes ajoutees apres la creation initiale de la base (voir OPTIONS_URL_SOURCE ci-dessus) :
# isolees ici pour pouvoir aussi les ajouter a une base deja existante via
# ajouter_proprietes_verification_url, sans dupliquer leur definition.
PROPRIETES_VERIFICATION_URL = {
    "url_source": {"select": {"options": [{"name": o} for o in OPTIONS_URL_SOURCE]}},
    "url_not_real": {"checkbox": {}},
}

PROPRIETES = {
    "titre": {"title": {}},
    "auteurs": {"rich_text": {}},
    "annee": {"number": {}},
    "revue": {"select": {}},
    "organisme": {"rich_text": {}},
    "doi_url": {"url": {}},
    **PROPRIETES_VERIFICATION_URL,
    "domaine_sante": {"multi_select": {"options": [{"name": o} for o in OPTIONS_DOMAINE_SANTE]}},
    "source_bruit": {"multi_select": {"options": [{"name": o} for o in OPTIONS_SOURCE_BRUIT]}},
    "resume": {"rich_text": {}},
    "resultat_cle": {"rich_text": {}},
    "date_ajout": {"created_time": {}},
    "statut": {"select": {"options": [
        {"name": "🆕 Nouveau"}, {"name": "✅ Lu"},
    ]}},
    "favori": {"checkbox": {}},
}


def creer_base(notion: Client, page_parent_id: str) -> str:
    """Retourne l'ID de la base créée. Depuis l'API Notion 2025-09-03, les propriétés
    sont portées par le "data source" de la base, pas par la base elle-même — voir
    notion_utils.py pour la résolution database_id -> data_source_id, utilisée ensuite
    par le reste du projet."""
    base = notion.databases.create(
        parent={"type": "page_id", "page_id": page_parent_id},
        title=[{"type": "text", "text": {"content": "Études"}}],
        initial_data_source={"properties": PROPRIETES},
    )
    return base["id"]


def ajouter_proprietes_verification_url(notion: Client, data_source_id: str) -> None:
    """Migration ponctuelle pour une base 'Etudes' deja existante (creee avant l'ajout de
    url_source/url_not_real) : notion.data_sources.update n'ajoute/ne modifie que les
    proprietes passees ici, il ne touche a aucune des colonnes existantes ni aux pages deja
    ecrites — sans risque a rejouer sur une base deja peuplee."""
    notion.data_sources.update(data_source_id=data_source_id, properties=PROPRIETES_VERIFICATION_URL)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Cree la base Notion 'Etudes', ou met a jour son schema (execution ponctuelle)."
    )
    parser.add_argument("page_parent_id", nargs="?", help="ID de la page Notion qui hebergera la base")
    parser.add_argument(
        "--ajouter-verification-url",
        metavar="DATA_SOURCE_ID",
        help="N'ajoute que les colonnes url_source/url_not_real a une base 'Etudes' existante",
    )
    args = parser.parse_args()

    notion = Client(auth=os.environ["NOTION_API_KEY"])

    if args.ajouter_verification_url:
        ajouter_proprietes_verification_url(notion, args.ajouter_verification_url)
        print(f"Colonnes url_source/url_not_real ajoutees a {args.ajouter_verification_url}.")
        return

    if not args.page_parent_id:
        parser.error("page_parent_id est requis hors migration --ajouter-verification-url")

    database_id = creer_base(notion, args.page_parent_id)

    print(f"Base 'Etudes' creee : {database_id}")
    print("Partagez-la avec l'integration (··· -> Connexions) si ce n'est pas deja fait,")
    print("puis reportez cet identifiant dans NOTION_DATABASE_ID (.env ou secrets GitHub).")


if __name__ == "__main__":
    main()
