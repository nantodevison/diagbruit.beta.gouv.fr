"""Export de la base Notion "Études" en CSV, pour analyser la relecture manuelle
(colonnes `favori`, `statut`, `fichier`) — voir FEUILLE_DE_ROUTE.md, « Analyse de la
relecture manuelle ».

Lecture seule : aucune écriture dans Notion, aucun appel à l'API Anthropic. Peut être
relancé après chaque nouveau parcours de la base.

    python -m analyse_relecture.exporter_base      (depuis veille-bruit-sante/)

Le CSV est écrit dans analyse_relecture/export/ (ignoré par Git).
"""
import csv
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from notion_client import Client

from notion_utils import resoudre_data_source_id

DOSSIER_EXPORT = Path(__file__).resolve().parent / "export"
TAILLE_PAGE = 100


def _valeur_texte(propriete: dict) -> str:
    """Convertit une propriété Notion, quel que soit son type, en texte lisible.

    On traite les types génériquement (plutôt que colonne par colonne) pour que l'export
    suive automatiquement les colonnes ajoutées à la main dans Notion, comme `fichier`.
    """
    type_ = propriete.get("type")
    valeur = propriete.get(type_)

    if type_ in ("title", "rich_text"):
        return "".join(morceau.get("plain_text", "") for morceau in valeur or [])
    if type_ == "select":
        return (valeur or {}).get("name", "")
    if type_ == "multi_select":
        return " | ".join(option["name"] for option in valeur or [])
    if type_ == "checkbox":
        return "oui" if valeur else "non"
    if type_ in ("number", "url", "email", "phone_number", "created_time", "last_edited_time"):
        return "" if valeur is None else str(valeur)
    if type_ == "files":
        # Fichier déposé dans Notion : son lien de téléchargement expire au bout d'une
        # heure environ, inutile de le garder — on note seulement son nom. Lien externe :
        # on garde l'URL, elle reste valable.
        elements = []
        for fichier in valeur or []:
            if fichier.get("type") == "external":
                elements.append(f"[lien] {fichier['external']['url']}")
            else:
                elements.append(f"[notion] {fichier.get('name', '?')}")
        return " | ".join(elements)
    if type_ == "status":
        return (valeur or {}).get("name", "")
    # Type non prévu : on le signale plutôt que de perdre l'information en silence.
    return f"<type {type_} non exporté>"


def lister_fiches(notion: Client, data_source_id: str) -> list:
    """Retourne toutes les pages de la base (pagination Notion par curseur)."""
    pages = []
    curseur = None
    while True:
        reponse = notion.data_sources.query(
            data_source_id=data_source_id, start_cursor=curseur, page_size=TAILLE_PAGE,
        )
        pages.extend(reponse["results"])
        if not reponse.get("has_more"):
            return pages
        curseur = reponse.get("next_cursor")


def main() -> None:
    load_dotenv()
    notion = Client(auth=os.environ["NOTION_API_KEY"])
    data_source_id = resoudre_data_source_id(notion, os.environ["NOTION_DATABASE_ID"])

    pages = lister_fiches(notion, data_source_id)

    # Colonnes : identifiants de la page, puis toutes les propriétés dans l'ordre où
    # Notion les renvoie (union sur toutes les pages, par sécurité).
    noms_proprietes: list = []
    types_proprietes: dict = {}
    for page in pages:
        for nom, propriete in page["properties"].items():
            if nom not in types_proprietes:
                noms_proprietes.append(nom)
                types_proprietes[nom] = propriete.get("type")

    lignes = []
    for page in pages:
        ligne = {"page_id": page["id"], "page_url": page.get("url", "")}
        for nom in noms_proprietes:
            propriete = page["properties"].get(nom)
            ligne[nom] = _valeur_texte(propriete) if propriete else ""
        lignes.append(ligne)

    DOSSIER_EXPORT.mkdir(exist_ok=True)
    chemin = DOSSIER_EXPORT / "etudes.csv"
    # utf-8-sig : le CSV s'ouvre avec les bons accents dans Excel.
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["page_id", "page_url", *noms_proprietes])
        writer.writeheader()
        writer.writerows(lignes)

    # Petit bilan en console, pour vérifier l'export d'un coup d'œil.
    print(f"{len(lignes)} fiche(s) exportée(s) dans {chemin}")
    print("Types des colonnes :", ", ".join(f"{n}={t}" for n, t in types_proprietes.items()))
    for colonne in ("favori", "statut", "url_source"):
        if colonne in noms_proprietes:
            print(f"{colonne} :", dict(Counter(ligne[colonne] for ligne in lignes)))
    if "fichier" in noms_proprietes:
        nb_fichiers = sum(1 for ligne in lignes if ligne["fichier"])
        print(f"fichier : {nb_fichiers} fiche(s) renseignée(s)")


if __name__ == "__main__":
    main()
