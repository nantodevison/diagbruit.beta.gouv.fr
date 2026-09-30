"""Point d'entrée unique du projet — enchaîne étape 2 (recherche/extraction) puis
étape 3 (intégration Notion) dans le même run. Voir docs/etape-1-conception-technique.md,
Décision 2 et 3.
"""
import os
from datetime import date

from dotenv import load_dotenv
from notion_client import Client

from etape2_recherche_extraction.main import executer as executer_etape2
from etape3_integration_notion.main import executer as executer_etape3
from notion_utils import marquer_ajouts_manuels, resoudre_data_source_id

DUREE_PREMIER_RUN_ANNEES = 10


def _calculer_date_depuis(notion: Client, data_source_id: str) -> date:
    """Date `date_ajout` la plus récente parmi les fiches créées par le run, ou aujourd'hui
    moins 10 ans si la base n'en contient aucune (premier run) — voir Décision 3.

    Les fiches ajoutées à la main (`ajout_manuel`) sont ignorées : sinon, une fiche créée
    aujourd'hui ferait partir la recherche d'aujourd'hui, et toute la période depuis le run
    précédent ne serait jamais cherchée, sans aucun signal."""
    reponse = notion.data_sources.query(
        data_source_id=data_source_id,
        filter={"property": "ajout_manuel", "checkbox": {"equals": False}},
        sorts=[{"property": "date_ajout", "direction": "descending"}],
        page_size=1,
    )
    resultats = reponse.get("results", [])
    if not resultats:
        aujourdhui = date.today()
        return aujourdhui.replace(year=aujourdhui.year - DUREE_PREMIER_RUN_ANNEES)

    date_ajout = resultats[0]["properties"]["date_ajout"]["created_time"]
    return date.fromisoformat(date_ajout[:10])


def main() -> None:
    load_dotenv()
    database_id = os.environ["NOTION_DATABASE_ID"]
    notion = Client(auth=os.environ["NOTION_API_KEY"])
    data_source_id = resoudre_data_source_id(notion, database_id)

    # Doit précéder le calcul de la date de départ, qui ignore ces fiches.
    nb_manuels = marquer_ajouts_manuels(notion, data_source_id)
    if nb_manuels:
        print(f"[main] {nb_manuels} fiche(s) ajoutee(s) a la main reperee(s) (ajout_manuel)")

    date_depuis = _calculer_date_depuis(notion, data_source_id)
    print(f"[main] recherche depuis le {date_depuis.isoformat()}")

    etudes = executer_etape2(date_depuis)
    print(f"[main] {len(etudes)} etude(s) retenue(s) apres extraction et dedoublonnage interne")

    executer_etape3(etudes, notion, data_source_id)


if __name__ == "__main__":
    main()
