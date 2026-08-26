"""Création ponctuelle de la base Notion "Études" — voir docs/etape-1-conception-technique.md,
Décision 4. Exécution manuelle, une seule fois, hors de la boucle hebdomadaire :

    python -m etape1_base_notion.creer_base_notion <id_page_notion_parente>
"""
import argparse
import os

from dotenv import load_dotenv
from notion_client import Client

PROPRIETES = {
    "titre": {"title": {}},
    "auteurs": {"rich_text": {}},
    "annee": {"number": {}},
    "revue": {"select": {}},
    "organisme": {"rich_text": {}},
    "doi_url": {"url": {}},
    "domaine_sante": {"multi_select": {"options": [
        {"name": "Cardiovasculaire"}, {"name": "Sante mentale"},
        {"name": "Cognition"}, {"name": "Metabolique"},
        {"name": "Sommeil"}, {"name": "Enfant"},
    ]}},
    "source_bruit": {"multi_select": {"options": [
        {"name": "Routier"}, {"name": "Aerien"},
        {"name": "Ferroviaire"}, {"name": "Industriel"},
    ]}},
    "resume": {"rich_text": {}},
    "resultat_cle": {"rich_text": {}},
    "date_ajout": {"created_time": {}},
    "statut": {"select": {"options": [
        {"name": "🆕 Nouveau"}, {"name": "✅ Lu"},
    ]}},
    "favori": {"checkbox": {}},
}


def creer_base(notion: Client, page_parent_id: str) -> str:
    base = notion.databases.create(
        parent={"type": "page_id", "page_id": page_parent_id},
        title=[{"type": "text", "text": {"content": "Études"}}],
        properties=PROPRIETES,
    )
    return base["id"]


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Cree la base Notion 'Etudes' (execution ponctuelle, une seule fois)."
    )
    parser.add_argument("page_parent_id", help="ID de la page Notion qui hebergera la base")
    args = parser.parse_args()

    notion = Client(auth=os.environ["NOTION_API_KEY"])
    database_id = creer_base(notion, args.page_parent_id)

    print(f"Base 'Etudes' creee : {database_id}")
    print("Partagez-la avec l'integration (··· -> Connexions) si ce n'est pas deja fait,")
    print("puis reportez cet identifiant dans NOTION_DATABASE_ID (.env ou secrets GitHub).")


if __name__ == "__main__":
    main()
