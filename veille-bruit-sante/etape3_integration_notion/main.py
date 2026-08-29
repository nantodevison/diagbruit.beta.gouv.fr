"""Point d'entrée de l'étape 3 — voir docs/etape-3-conception-technique.md."""
from notion_client import Client

from . import dedoublonnage_existant, ecriture, etat_existant, verification_url


def executer(etudes: list[dict], notion: Client, data_source_id: str) -> None:
    """Reçoit la liste dédoublonnée en interne (sortie de l'étape 2), écrit les nouvelles
    fiches. Un échec isolé d'écriture n'interrompt jamais le run (Décision 4)."""
    doi_existants, titres_existants = etat_existant.recuperer_etat_existant(notion, data_source_id)

    nb_creees = 0
    for etude in etudes:
        if dedoublonnage_existant.est_deja_present(etude, doi_existants, titres_existants):
            continue

        # Verifie l'URL seulement ici (pas plus tot dans le pipeline) : inutile de faire
        # une requete HTTP sur une etude qui sera de toute facon ecartee comme doublon.
        etude["url_not_real"] = not verification_url.url_pointe_vers_un_document(etude.get("doi_url", ""))

        try:
            ecriture.creer_fiche(notion, data_source_id, etude)
            nb_creees += 1
        except Exception as erreur:
            print(f"[etape3][ecriture] echec creation fiche pour '{etude.get('titre', '?')}' : {erreur}")

    print(f"[etape3] {nb_creees} nouvelle(s) fiche(s) creee(s) sur {len(etudes)} etude(s) recue(s).")
