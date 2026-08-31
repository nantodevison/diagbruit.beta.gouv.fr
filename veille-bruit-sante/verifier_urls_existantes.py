"""Script ponctuel — vérifie l'URL de chaque fiche déjà présente dans la base Notion
"Études" et met à jour url_not_real en conséquence. Contrairement au run hebdomadaire
(main.py, étapes 2 et 3), ce script ne fait aucun appel à l'API Anthropic : uniquement des
requêtes Notion (lecture/écriture) et HTTP (etape3_integration_notion/verification_url) —
les appels Anthropic sont coûteux et réservés aux tâches qui le justifient.

    python verifier_urls_existantes.py
"""
import os

from dotenv import load_dotenv
from notion_client import Client

from etape3_integration_notion import verification_url
from notion_utils import resoudre_data_source_id

TAILLE_PAGE = 100


def _lister_fiches(notion: Client, data_source_id: str) -> list[dict]:
    """Retourne, pour chaque fiche existante, son page_id, son titre, son doi_url et la
    valeur actuelle de url_not_real (pour n'écrire dans Notion que ce qui change)."""
    fiches: list[dict] = []
    curseur = None

    while True:
        reponse = notion.data_sources.query(
            data_source_id=data_source_id, start_cursor=curseur, page_size=TAILLE_PAGE,
        )
        for page in reponse["results"]:
            proprietes = page["properties"]
            titre_bruts = (proprietes.get("titre") or {}).get("title") or []
            fiches.append({
                "page_id": page["id"],
                "titre": titre_bruts[0]["plain_text"] if titre_bruts else "(sans titre)",
                "doi_url": (proprietes.get("doi_url") or {}).get("url") or "",
                "url_not_real_actuel": (proprietes.get("url_not_real") or {}).get("checkbox", False),
            })
        if not reponse.get("has_more"):
            break
        curseur = reponse.get("next_cursor")

    return fiches


def executer(notion: Client, data_source_id: str) -> None:
    fiches = _lister_fiches(notion, data_source_id)
    nb_avec_url = 0
    nb_cassees = 0
    nb_maj = 0

    for fiche in fiches:
        if not fiche["doi_url"]:
            continue
        nb_avec_url += 1

        url_cassee = not verification_url.url_pointe_vers_un_document(fiche["doi_url"])
        if url_cassee:
            nb_cassees += 1
            print(f"[CASSEE] {fiche['titre']} -> {fiche['doi_url']}")

        if url_cassee != fiche["url_not_real_actuel"]:
            notion.pages.update(
                page_id=fiche["page_id"],
                properties={"url_not_real": {"checkbox": url_cassee}},
            )
            nb_maj += 1

    print(
        f"\n{nb_avec_url} fiche(s) avec URL analysee(s) sur {len(fiches)} au total, "
        f"{nb_cassees} URL cassee(s) detectee(s), {nb_maj} fiche(s) mise(s) a jour dans Notion."
    )


def main() -> None:
    load_dotenv()
    notion = Client(auth=os.environ["NOTION_API_KEY"])
    data_source_id = resoudre_data_source_id(notion, os.environ["NOTION_DATABASE_ID"])
    executer(notion, data_source_id)


if __name__ == "__main__":
    main()
