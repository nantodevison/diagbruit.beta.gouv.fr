"""Nettoyage de la colonne `domaine_sante` de la base Notion "Études" : remplace les
étiquettes libres des premiers runs par la liste fermée alignée sur le socle — voir
docs/etape-5-conception-technique.md, Décisions 1 et 2 (validées le 17/11/2026).

Aucun appel à l'API Anthropic : la traduction repose uniquement sur les alias validés
dans socle/etat-connaissances.yaml.

    python -m analyse_relecture.nettoyer_domaine_sante              (simulation)
    python -m analyse_relecture.nettoyer_domaine_sante --appliquer  (écrit dans Notion)

En simulation (par défaut), rien n'est écrit dans Notion : le tableau « avant → après »
est écrit dans analyse_relecture/export/nettoyage_domaine_sante.csv (ignoré par Git).
Avec --appliquer, seule la colonne `domaine_sante` est modifiée, et seulement sur les
fiches dont les étiquettes changent. Faire un export (exporter_base) juste avant : il
sert de sauvegarde des anciennes étiquettes.
"""
import argparse
import csv
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from notion_client import Client

from notion_utils import resoudre_data_source_id

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_SOCLE = RACINE / "socle" / "etat-connaissances.yaml"
CHEMIN_SORTIE = Path(__file__).resolve().parent / "export" / "nettoyage_domaine_sante.csv"

# Option qui ne correspond à aucune entrée du socle (voir Décision 1) : document
# d'ensemble, sans effet précis.
OPTION_GENERAL = "General"
# Thème « enfants » : c'est l'etiquette_notion de l'effet « apprentissages chez l'enfant »
# du socle, étendue à tout effet étudié chez l'enfant (décision du 17/11/2026).
OPTION_ENFANT = "Enfant"

# Une ancienne étiquette contenant l'un de ces morceaux de mot porte sur les enfants :
# la fiche reçoit aussi l'option Enfant, en plus de son effet. Comparaison en minuscules.
MOTS_ENFANT = ("enfant", "infantile", "scolaire", "nouveau-n", "néonatal")


def charger_correspondances(socle: dict) -> tuple[dict, list]:
    """Construit, à partir du socle, le dictionnaire « ancienne étiquette → nouvelle
    option » (None pour une étiquette non rattachée), et la liste ordonnée des options,
    qui fixe l'ordre d'affichage dans Notion."""
    entrees = [
        *socle["effets"],
        socle["encadre_a_ne_pas_confondre"],
        *socle["pistes_emergentes"],
        *socle["themes_hors_socle"],
    ]
    correspondances, options = {}, []
    for entree in entrees:
        option = entree["etiquette_notion"]
        options.append(option)
        # L'option elle-même est reconnue : une fiche déjà propre reste inchangée.
        correspondances[option] = option
        for alias in entree["alias_domaine_sante"]:
            correspondances[alias] = option
    for alias in socle["alias_non_rattaches"]:
        correspondances[alias] = None
    options.append(OPTION_GENERAL)
    correspondances[OPTION_GENERAL] = OPTION_GENERAL
    return correspondances, options


def nouvelles_etiquettes(anciennes: list, correspondances: dict, options: list) -> tuple[list, list]:
    """Retourne (nouvelles options triées, étiquettes inconnues). Une étiquette inconnue
    du socle est conservée telle quelle et signalée : rien n'est retiré sans trace."""
    nouvelles, inconnues = set(), []
    for etiquette in anciennes:
        if etiquette not in correspondances:
            inconnues.append(etiquette)
            nouvelles.add(etiquette)
            continue
        option = correspondances[etiquette]
        if option:
            nouvelles.add(option)
        # Effet étudié chez l'enfant (ex. santé mentale de l'enfant, cohorte ELFE) : la
        # fiche relève aussi du thème Enfant.
        if any(mot in etiquette.lower() for mot in MOTS_ENFANT):
            nouvelles.add(OPTION_ENFANT)
    # Aucun effet précis (seulement des étiquettes générales) : General.
    if not nouvelles:
        nouvelles.add(OPTION_GENERAL)
    ordre = {option: i for i, option in enumerate(options)}
    return sorted(nouvelles, key=lambda o: ordre.get(o, len(ordre))), inconnues


def lire_fiches(notion: Client, data_source_id: str) -> list:
    """Toutes les fiches de la base (lecture seule), avec titre et domaine_sante."""
    fiches, curseur = [], None
    while True:
        reponse = notion.data_sources.query(
            data_source_id=data_source_id, start_cursor=curseur, page_size=100,
        )
        for page in reponse["results"]:
            proprietes = page["properties"]
            fiches.append({
                "page_id": page["id"],
                "titre": "".join(m["plain_text"] for m in proprietes["titre"]["title"]),
                "domaine_sante": [o["name"] for o in proprietes["domaine_sante"]["multi_select"]],
            })
        if not reponse.get("has_more"):
            return fiches
        curseur = reponse["next_cursor"]


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--appliquer", action="store_true",
                        help="écrit dans Notion (sinon : simulation, rien n'est modifié)")
    args = parser.parse_args()

    socle = yaml.safe_load(CHEMIN_SOCLE.read_text(encoding="utf-8"))
    correspondances, options = charger_correspondances(socle)

    notion = Client(auth=os.environ["NOTION_API_KEY"])
    data_source_id = resoudre_data_source_id(notion, os.environ["NOTION_DATABASE_ID"])
    fiches = lire_fiches(notion, data_source_id)

    lignes, nb_changements, nb_ecrites = [], 0, 0
    for fiche in fiches:
        apres, inconnues = nouvelles_etiquettes(fiche["domaine_sante"], correspondances, options)
        change = sorted(apres) != sorted(fiche["domaine_sante"])
        nb_changements += change
        lignes.append({
            "page_id": fiche["page_id"],
            "titre": fiche["titre"],
            "avant": " | ".join(fiche["domaine_sante"]),
            "apres": " | ".join(apres),
            "change": "oui" if change else "non",
            "etiquettes_inconnues": " | ".join(inconnues),
        })
        if inconnues:
            print(f"Étiquette(s) inconnue(s) du socle, conservée(s) : {inconnues} — {fiche['titre'][:80]}")
        if change and args.appliquer:
            # Un échec isolé n'interrompt pas le nettoyage (règle du projet) : il est
            # journalisé, et le script peut être relancé, il ne retouche que ce qui change.
            try:
                notion.pages.update(page_id=fiche["page_id"], properties={
                    "domaine_sante": {"multi_select": [{"name": o} for o in apres]},
                })
                nb_ecrites += 1
            except Exception as erreur:  # noqa: BLE001 — on journalise et on continue
                print(f"ÉCHEC d'écriture : {fiche['titre'][:80]} — {erreur}")

    CHEMIN_SORTIE.parent.mkdir(exist_ok=True)
    with CHEMIN_SORTIE.open("w", encoding="utf-8-sig", newline="") as sortie:
        writer = csv.DictWriter(sortie, fieldnames=list(lignes[0].keys()))
        writer.writeheader()
        writer.writerows(lignes)

    print(f"{len(fiches)} fiche(s) lue(s), {nb_changements} à modifier.")
    print(f"Tableau avant → après : {CHEMIN_SORTIE}")
    if args.appliquer:
        print(f"{nb_ecrites} fiche(s) modifiée(s) dans Notion.")
    else:
        print("Simulation : rien n'a été écrit dans Notion (relancer avec --appliquer).")


if __name__ == "__main__":
    main()
