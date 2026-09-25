"""Remplit les colonnes de qualification des fiches déjà présentes dans la base Notion
(écrites avant l'ajout de ces colonnes).

Écrit UNIQUEMENT les 7 colonnes de qualification (COLONNES_QUALIFICATION). Les colonnes
remplies à la main — `favori`, `statut`, `fichier` — et toutes les autres ne sont jamais
envoyées à Notion : un contrôle bloque l'écriture si l'une d'elles s'y glissait.

Sources, par ordre de préférence et pour ne payer que le nécessaire :
1. les champs extraits par tester_qualification.py (export/qualification.jsonl) — gratuit ;
2. une nouvelle extraction pour les fiches dont le contenu existe mais dont l'extraction
   avait échoué — payant, ajoutée à qualification.jsonl ; si elle échoue encore, repli
   sur priorité Faible et a_verifier (comme en 3) ;
3. sans contenu récupérable : priorité Faible et a_verifier, sans appel LLM (il n'y a
   rien à lire, c'est ce que ferait le prompt).

    python -m analyse_relecture.qualifier_base_existante      (depuis veille-bruit-sante/)

Pré-requis : exporter_base.py puis recuperer_contenus.py (export/etudes.csv, contenus.json).
"""
import csv
import json
import os

from dotenv import load_dotenv
from notion_client import Client
from tenacity import retry, stop_after_attempt, wait_exponential

from analyse_relecture import tester_qualification as test
from etape2_recherche_extraction import extraction, qualification
from etape3_integration_notion.ecriture import _proprietes
from notion_utils import resoudre_data_source_id

COLONNES_QUALIFICATION = (
    "type_document", "sens_conclusion", "elements_probants", "reprise_de",
    "priorite", "nouveaute", "a_verifier",
)
# Colonnes tenues à la main par l'utilisateur : ne jamais les écrire.
COLONNES_INTERDITES = {"favori", "statut", "fichier"}


def _qualification_sans_contenu(fiche: dict) -> dict:
    annee = int(fiche["annee"]) if fiche["annee"] else None
    return {
        "type_document": None, "sens_conclusion": None, "elements_probants": "",
        "reprise_de": "", "annee": annee, "canal": "", "doi_url": fiche["doi_url"],
        "a_verifier": True,
    }


def _extraire(fiche_avec_contenu: dict) -> dict:
    """Nouvelle extraction (payante), enregistrée dans qualification.jsonl."""
    source = test._source_pour_extraction(fiche_avec_contenu)
    extraite, _usage = extraction.extraire(source)
    etude = extraite.model_dump()
    etude["canal"] = source["canal"]
    etude["doi_url"] = etude["doi_url"] or source["doi_url"]
    with open(test.CHEMIN_RESULTATS, "a", encoding="utf-8") as f:
        ligne = {"page_id": fiche_avec_contenu["page_id"],
                 "favori": fiche_avec_contenu["favori"] == "oui", **etude}
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    return etude


def _proprietes_qualification(etude: dict) -> dict:
    proprietes = {k: v for k, v in _proprietes(etude).items() if k in COLONNES_QUALIFICATION}
    if COLONNES_INTERDITES & proprietes.keys():
        raise RuntimeError("Tentative d'écriture d'une colonne manuelle : arrêt.")
    return proprietes


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _mettre_a_jour(notion: Client, page_id: str, proprietes: dict) -> None:
    notion.pages.update(page_id=page_id, properties=proprietes)


def main() -> None:
    load_dotenv()
    with open(test.DOSSIER_EXPORT / "etudes.csv", encoding="utf-8-sig") as f:
        fiches = list(csv.DictReader(f))
    with open(test.DOSSIER_EXPORT / "contenus.json", encoding="utf-8") as f:
        contenus = json.load(f)
    extraites = test._deja_faits()

    notion = Client(auth=os.environ["NOTION_API_KEY"])
    resoudre_data_source_id(notion, os.environ["NOTION_DATABASE_ID"])  # vérifie l'accès

    bilan = {"source_test": 0, "nouvelle_extraction": 0, "repli_a_verifier": 0,
             "sans_contenu": 0, "echec": 0}
    priorites = {}
    for numero, fiche in enumerate(fiches, start=1):
        fiche["_contenu"] = contenus.get(fiche["page_id"], {})
        try:
            if fiche["page_id"] in extraites:
                etude, origine = dict(extraites[fiche["page_id"]]), "source_test"
            elif fiche["_contenu"].get("contenu"):
                try:
                    etude, origine = _extraire(fiche), "nouvelle_extraction"
                except Exception as erreur:
                    # Repli : la fiche est déjà en base, on la signale à vérifier plutôt
                    # que de la laisser sans qualification.
                    print(f"    extraction en echec ({type(erreur).__name__}), repli a_verifier")
                    etude, origine = _qualification_sans_contenu(fiche), "repli_a_verifier"
            else:
                etude, origine = _qualification_sans_contenu(fiche), "sans_contenu"

            etude.setdefault("a_verifier", bool(etude.get("contenu_insuffisant")))
            qualification.qualifier([etude], test.DATE_DEPUIS)
            # Déjà en base mais hors périmètre selon l'extraction : on ne supprime rien,
            # on la place en bas de liste.
            if etude.get("hors_perimetre"):
                etude["priorite"] = qualification.FAIBLE

            _mettre_a_jour(notion, fiche["page_id"], _proprietes_qualification(etude))
            bilan[origine] += 1
            priorites[etude["priorite"]] = priorites.get(etude["priorite"], 0) + 1
            print(f"{numero:3}/{len(fiches)} {origine:20} {etude['priorite']:10} {fiche['titre'][:55]}")
        except Exception as erreur:  # une fiche en échec ne bloque pas les autres
            bilan["echec"] += 1
            print(f"{numero:3}/{len(fiches)} ECHEC {fiche['titre'][:55]} : {erreur}")

    print("\nBilan :", bilan)
    print("Priorités écrites :", priorites)


if __name__ == "__main__":
    main()
