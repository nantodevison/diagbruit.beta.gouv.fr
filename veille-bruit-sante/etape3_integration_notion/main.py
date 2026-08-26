"""Point d'entrée de l'étape 3 — voir docs/etape-3-conception-technique.md."""
import os

from notion_client import Client

from . import dedoublonnage_existant, ecriture, etat_existant


def executer(etudes: list[dict]) -> None:
    """Reçoit la liste dédoublonnée en interne (sortie de l'étape 2), écrit les nouvelles
    fiches. Un échec isolé d'écriture n'interrompt jamais le run (Décision 4)."""
    database_id = os.environ["NOTION_DATABASE_ID"]
    notion = Client(auth=os.environ["NOTION_API_KEY"])

    doi_existants, titres_existants = etat_existant.recuperer_etat_existant(notion, database_id)

    nb_creees = 0
    for etude in etudes:
        if dedoublonnage_existant.est_deja_present(etude, doi_existants, titres_existants):
            continue
        try:
            ecriture.creer_fiche(notion, database_id, etude)
            nb_creees += 1
        except Exception as erreur:
            print(f"[etape3][ecriture] echec creation fiche pour '{etude.get('titre', '?')}' : {erreur}")

    print(f"[etape3] {nb_creees} nouvelle(s) fiche(s) creee(s) sur {len(etudes)} etude(s) recue(s).")
