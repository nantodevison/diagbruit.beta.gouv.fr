"""Teste la qualification (priorite) sur les fiches déjà relues : les priorités
hautes regroupent-elles les favoris choisis à la main ?

PAYANT : un appel Anthropic (extraction) par fiche testée. Rien n'est écrit dans Notion :
les résultats vont dans export/qualification.jsonl (un résultat par ligne, conservé d'un
lancement à l'autre pour ne jamais payer deux fois la même fiche) et export/qualification.csv.

    python -m analyse_relecture.tester_qualification --estimer     # coût estimé, gratuit
    python -m analyse_relecture.tester_qualification --limit 3     # petit essai
    python -m analyse_relecture.tester_qualification               # toutes les fiches

Entrées : export/etudes.csv (exporter_base.py) et export/contenus.json
(recuperer_contenus.py). Seules les fiches dont le contenu source a pu être récupéré sont
testées : sans contenu, le prompt les classe hors périmètre, ce qui fausserait le test.
"""
import argparse
import csv
import json
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from etape2_recherche_extraction import extraction, qualification

DOSSIER_EXPORT = Path(__file__).resolve().parent / "export"
CHEMIN_RESULTATS = DOSSIER_EXPORT / "qualification.jsonl"

# Tarifs Claude Sonnet 5 en $ par million de tokens (vérifiés le 24/09/2026).
PRIX_ENTREE, PRIX_SORTIE, PRIX_CACHE_LU, PRIX_CACHE_ECRIT = 2.00, 10.00, 0.20, 2.50
# Valeurs mesurées sur un premier essai de 3 fiches (24/09/2026), plus élevées que les
# approximations habituelles : Sonnet 5 réfléchit par défaut (thinking adaptatif, facturé
# comme de la sortie), et les pages web (menus, chiffres, liens) se découpent finement.
TOKENS_SORTIE_ESTIMES = 900   # réponse structurée + réflexion du modèle
CARACTERES_PAR_TOKEN = 2.7
TOKENS_PROMPT_SYSTEME = 3657  # mesuré avec messages.count_tokens

# Même fenêtre que le premier run de la base (rattrapage sur 10 ans), pour que `nouveaute`
# soit calculée comme elle l'aurait été à l'époque.
DATE_DEPUIS = date(2016, 8, 26)


def _charger_fiches() -> list:
    with open(DOSSIER_EXPORT / "etudes.csv", encoding="utf-8-sig") as f:
        fiches = list(csv.DictReader(f))
    with open(DOSSIER_EXPORT / "contenus.json", encoding="utf-8") as f:
        contenus = json.load(f)
    for fiche in fiches:
        fiche["_contenu"] = contenus.get(fiche["page_id"], {})
    return [f for f in fiches if f["_contenu"].get("contenu")]


def _source_pour_extraction(fiche: dict) -> dict:
    """Reconstitue une « source candidate » au format attendu par extraction.extraire,
    comme si la fiche venait d'être trouvée par la recherche."""
    contenu = fiche["_contenu"]
    via_api = contenu["methode"].startswith(("openalex", "europe_pmc"))
    return {
        "canal": "api" if via_api else "web",
        "titre": fiche["titre"],
        "doi_url": fiche["doi_url"],
        "auteurs": fiche["auteurs"],
        "annee": contenu.get("annee") or fiche["annee"] or "",
        "revue": contenu.get("revue") or fiche["revue"],
        "resume_brut": contenu["contenu"],
    }


def _deja_faits() -> dict:
    if not CHEMIN_RESULTATS.exists():
        return {}
    with open(CHEMIN_RESULTATS, encoding="utf-8") as f:
        return {r["page_id"]: r for r in map(json.loads, f)}


def estimer(fiches: list) -> None:
    caracteres = sum(len(f["_contenu"]["contenu"]) for f in fiches)
    tokens_entree = caracteres / CARACTERES_PAR_TOKEN + 150 * len(fiches)  # + gabarit du prompt
    tokens_systeme = TOKENS_PROMPT_SYSTEME
    cout = (
        tokens_entree * PRIX_ENTREE
        + TOKENS_SORTIE_ESTIMES * len(fiches) * PRIX_SORTIE
        + tokens_systeme * PRIX_CACHE_ECRIT
        + tokens_systeme * (len(fiches) - 1) * PRIX_CACHE_LU
    ) / 1_000_000
    print(f"{len(fiches)} fiche(s) à tester, ~{tokens_entree:,.0f} tokens d'entrée hors cache")
    print(f"Coût estimé : ~{cout:.2f} $ (fourchette prudente : {cout * 0.7:.2f} à {cout * 1.5:.2f} $)")


def tester(fiches: list, limite: int) -> None:
    faits = _deja_faits()
    a_faire = [f for f in fiches if f["page_id"] not in faits][:limite or None]
    print(f"{len(faits)} fiche(s) déjà testée(s), {len(a_faire)} à tester maintenant.")

    cout_total = 0.0
    with open(CHEMIN_RESULTATS, "a", encoding="utf-8") as sortie:
        for numero, fiche in enumerate(a_faire, start=1):
            source = _source_pour_extraction(fiche)
            try:
                extraite, usage = extraction.extraire(source)
            except Exception as erreur:  # un échec isolé ne bloque pas le lot
                print(f"  échec pour '{fiche['titre'][:60]}' : {erreur}")
                continue

            etude = extraite.model_dump()
            etude["canal"] = source["canal"]
            etude["doi_url"] = etude["doi_url"] or source["doi_url"]
            qualification.qualifier([etude], DATE_DEPUIS)

            cout = (
                usage.input_tokens * PRIX_ENTREE + usage.output_tokens * PRIX_SORTIE
                + (usage.cache_read_input_tokens or 0) * PRIX_CACHE_LU
                + (usage.cache_creation_input_tokens or 0) * PRIX_CACHE_ECRIT
            ) / 1_000_000
            cout_total += cout

            resultat = {
                "page_id": fiche["page_id"], "favori": fiche["favori"] == "oui",
                "a_fichier": bool(fiche["fichier"]), "methode_contenu": fiche["_contenu"]["methode"],
                "cout": cout, **etude,
            }
            sortie.write(json.dumps(resultat, ensure_ascii=False) + "\n")
            sortie.flush()  # un arrêt en cours de route ne perd pas ce qui est payé
            print(f"{numero:3}/{len(a_faire)} fav={'oui' if resultat['favori'] else 'non'} "
                  f"priorite={etude['priorite']:10} "
                  f"{etude.get('type_document') or '-':35} {fiche['titre'][:50]}")

    print(f"Coût réel de ce lancement : {cout_total:.3f} $")


def bilan() -> None:
    """Tableau favori (choix manuel) × priorite (règle), plus un CSV à relire.

    La priorité est recalculée ici à partir des champs extraits déjà enregistrés : on peut
    ainsi ajuster les règles de qualification.py et remesurer sans aucun nouvel appel payant.
    """
    resultats = list(_deja_faits().values())
    if not resultats:
        return
    qualification.qualifier(resultats, DATE_DEPUIS)
    # Dans le pipeline, une étude hors périmètre n'atteint jamais Notion : on la compte à part.
    ECARTEE = "(ecartee)"
    for r in resultats:
        if r["hors_perimetre"]:
            r["priorite"] = ECARTEE
    niveaux = (qualification.HAUTE, qualification.A_EXAMINER, qualification.FAIBLE, ECARTEE)
    nb_favoris = sum(r["favori"] for r in resultats)

    print(f"\n=== Bilan sur {len(resultats)} fiche(s), dont {nb_favoris} favoris ===")
    print(f"{'priorité':12} {'fiches':>6} {'dont favoris':>13} {'part de favoris':>16}")
    favoris_cumules = 0
    for niveau in niveaux:
        du_niveau = [r for r in resultats if r["priorite"] == niveau]
        favoris = sum(r["favori"] for r in du_niveau)
        favoris_cumules += favoris
        part = f"{favoris / len(du_niveau):.0%}" if du_niveau else "-"
        print(f"{niveau:12} {len(du_niveau):6} {favoris:13} {part:>16}")
        if niveau in (qualification.HAUTE, qualification.A_EXAMINER) and nb_favoris:
            print(f"{'':12} → jusqu'à « {niveau} » : {favoris_cumules / nb_favoris:.0%} des favoris retrouvés")
    print(f"Coût cumulé : {sum(r.get('cout', 0) for r in resultats):.3f} $")

    colonnes = [
        "favori", "priorite", "hors_perimetre", "motif_exclusion", "contenu_insuffisant",
        "type_document", "sens_conclusion",
        "elements_probants", "reprise_de", "annee", "nouveaute", "titre", "doi_url",
        "domaine_sante", "source_bruit", "resume", "resultat_cle", "methode_contenu",
        "a_fichier", "page_id",
    ]
    with open(DOSSIER_EXPORT / "qualification.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=colonnes, extrasaction="ignore")
        writer.writeheader()
        for r in resultats:
            writer.writerow({**r, "domaine_sante": " | ".join(r["domaine_sante"]),
                             "source_bruit": " | ".join(r["source_bruit"])})
    print(f"Détail : {DOSSIER_EXPORT / 'qualification.csv'}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--estimer", action="store_true", help="affiche le coût estimé, sans appel")
    parser.add_argument("--limit", type=int, default=0, help="nombre max de fiches à tester")
    args = parser.parse_args()

    fiches = _charger_fiches()
    if args.estimer:
        estimer([f for f in fiches if f["page_id"] not in _deja_faits()])
        return
    tester(fiches, args.limit)
    bilan()


if __name__ == "__main__":
    main()
