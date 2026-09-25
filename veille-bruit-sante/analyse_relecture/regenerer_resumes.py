"""Régénère le résumé et la qualification des fiches dont la colonne `fichier` contient le
texte intégral (ajouté à la main par l'utilisateur) — voir docs/workflow-veille.md,
étape « Régénération du résumé à partir du texte intégral ».

Écrit UNIQUEMENT `resume`, `resultat_cle` et les 7 colonnes de qualification. `favori`,
`statut`, `fichier` et les autres colonnes ne sont jamais envoyés à Notion.

    python -m analyse_relecture.regenerer_resumes --estimer     # télécharge + compte, gratuit
    python -m analyse_relecture.regenerer_resumes --limit 1     # petit essai, payant
    python -m analyse_relecture.regenerer_resumes               # toutes les fiches, payant

Les fichiers sont gardés dans export/fichiers/ (ignoré par Git) et chaque résultat dans
export/regeneration.jsonl : relancer le script ne paie jamais deux fois la même fiche.
Un PDF est envoyé tel quel au modèle (texte + mise en page) ; une page web, en texte.
"""
import argparse
import base64
import json
import os
import re

import requests
from anthropic import Anthropic
from dotenv import load_dotenv
from notion_client import Client
from tenacity import retry, stop_after_attempt, wait_exponential

from analyse_relecture import tester_qualification as test
from analyse_relecture.qualifier_base_existante import (
    COLONNES_INTERDITES, COLONNES_QUALIFICATION, _mettre_a_jour,
)
from analyse_relecture.recuperer_contenus import ENTETES, MOTIF_PMCID, _ExtracteurTexte
from etape2_recherche_extraction import extraction, qualification
from etape3_integration_notion.ecriture import _proprietes
from notion_utils import resoudre_data_source_id

DOSSIER_FICHIERS = test.DOSSIER_EXPORT / "fichiers"
CHEMIN_RESULTATS = test.DOSSIER_EXPORT / "regeneration.jsonl"
COLONNES_ECRITES = ("resume", "resultat_cle", *COLONNES_QUALIFICATION)
TIMEOUT = 60
LONGUEUR_MIN_TEXTE = 1500  # en dessous : page d'attente, lien mort… jamais un texte intégral


def _texte(propriete: dict) -> str:
    type_ = propriete["type"]
    if type_ in ("title", "rich_text"):
        return "".join(m["plain_text"] for m in propriete[type_])
    if type_ == "number":
        return "" if propriete["number"] is None else str(propriete["number"])
    if type_ == "url":
        return propriete["url"] or ""
    if type_ == "select":
        return (propriete["select"] or {}).get("name", "")
    return ""


def lister_fiches_avec_fichier(notion: Client, data_source_id: str) -> list:
    """Lit la base en direct : les liens des fichiers déposés dans Notion expirent au bout
    d'environ une heure, il faut donc les obtenir juste avant de les télécharger."""
    fiches, curseur = [], None
    while True:
        reponse = notion.data_sources.query(
            data_source_id=data_source_id, start_cursor=curseur, page_size=100,
        )
        for page in reponse["results"]:
            p = page["properties"]
            fichiers = (p.get("fichier") or {}).get("files") or []
            if not fichiers:
                continue
            # Un PDF déposé dans Notion passe avant un lien externe : les liens copiés
            # depuis un navigateur (ScienceDirect, OUP, Lancet…) sont souvent signés et
            # expirent, l'utilisateur dépose alors le PDF à côté de l'ancien lien.
            choisi = next((f for f in fichiers if f["type"] == "file"), fichiers[0])
            url = choisi["file"]["url"] if choisi["type"] == "file" else choisi["external"]["url"]
            fiches.append({
                "page_id": page["id"], "url_fichier": url,
                "titre": _texte(p["titre"]), "auteurs": _texte(p["auteurs"]),
                "annee": _texte(p["annee"]), "revue": _texte(p["revue"]),
                "doi_url": _texte(p["doi_url"]),
                "favori": p["favori"]["checkbox"],
            })
        if not reponse.get("has_more"):
            return fiches
        curseur = reponse["next_cursor"]


def _texte_integral_europe_pmc(pmcid: str) -> str:
    """Texte intégral d'un article en accès ouvert, via l'API gratuite d'Europe PMC. Les
    liens PDF de PubMed Central renvoient une page d'attente anti-robot
    (« Preparing to download… ») au lieu du document."""
    reponse = requests.get(
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
        headers=ENTETES, timeout=TIMEOUT,
    )
    reponse.raise_for_status()
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", reponse.text)).strip()


def telecharger(fiche: dict) -> dict:
    """Retourne un bloc « document » pour l'API Anthropic (PDF ou texte), mis en cache.
    Lève une erreur si le contenu est trop court pour être un vrai texte intégral."""
    DOSSIER_FICHIERS.mkdir(exist_ok=True)
    pdf = DOSSIER_FICHIERS / f"{fiche['page_id']}.pdf"
    txt = DOSSIER_FICHIERS / f"{fiche['page_id']}.txt"

    if not pdf.exists() and not (txt.exists() and txt.stat().st_size >= LONGUEUR_MIN_TEXTE):
        pmcid = MOTIF_PMCID.search(fiche["url_fichier"])
        if pmcid:
            txt.write_text(_texte_integral_europe_pmc(pmcid.group(1).upper()), encoding="utf-8")
        else:
            reponse = requests.get(fiche["url_fichier"], headers=ENTETES, timeout=TIMEOUT)
            reponse.raise_for_status()
            if "pdf" in reponse.headers.get("Content-Type", "") or reponse.content[:4] == b"%PDF":
                pdf.write_bytes(reponse.content)
            else:
                extracteur = _ExtracteurTexte()
                extracteur.feed(reponse.text)
                txt.write_text(" ".join(extracteur.morceaux), encoding="utf-8")

    if pdf.exists():
        donnees = base64.standard_b64encode(pdf.read_bytes()).decode("utf-8")
        return {"type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": donnees}}
    texte = txt.read_text(encoding="utf-8")
    if len(texte) < LONGUEUR_MIN_TEXTE:
        raise ValueError(f"contenu trop court ({len(texte)} caractères) : page d'attente ou lien mort")
    return {"type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": texte}}


def _messages(fiche: dict, document: dict) -> list:
    source = {**fiche, "resume_brut": "le document joint ci-dessus (texte integral)."}
    return [{"role": "user", "content": [document,
                                         {"type": "text", "text": extraction._construire_prompt(source)}]}]


def _systeme() -> list:
    return [{"type": "text", "text": extraction.PROMPT_SYSTEME, "cache_control": {"type": "ephemeral"}}]


def _deja_faits() -> dict:
    if not CHEMIN_RESULTATS.exists():
        return {}
    with open(CHEMIN_RESULTATS, encoding="utf-8") as f:
        return {r["page_id"]: r for r in map(json.loads, f)}


def estimer(client: Anthropic, fiches: list) -> None:
    total_entree, urls_vues = 0, set()
    for fiche in fiches:
        if fiche["url_fichier"] in urls_vues:
            print(f"  (doublon, réutilisé)  {fiche['titre'][:65]}")
            continue
        urls_vues.add(fiche["url_fichier"])
        try:
            document = telecharger(fiche)
            n = client.messages.count_tokens(
                model=extraction.MODELE, system=_systeme(), messages=_messages(fiche, document),
            ).input_tokens
        except Exception as erreur:
            print(f"  ILLISIBLE {fiche['titre'][:60]} : {erreur}")
            continue
        total_entree += n
        genre = "PDF" if document["source"]["type"] == "base64" else "texte"
        print(f"  {n:8,} tokens  {genre:5}  {fiche['titre'][:65]}")
    # Sortie : ~900 tokens (réponse + réflexion), mesuré au test du 24/09.
    cout = (total_entree * test.PRIX_ENTREE + 900 * len(urls_vues) * test.PRIX_SORTIE) / 1_000_000
    print(f"\n{len(urls_vues)} fichier(s) distinct(s), {total_entree:,} tokens d'entrée"
          f" -> coût estimé ~{cout:.2f} $ (fichiers illisibles non comptés)")


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=2, max=20))
def _extraire(client: Anthropic, fiche: dict, document: dict):
    reponse = client.messages.parse(
        model=extraction.MODELE, max_tokens=4000, system=_systeme(),
        messages=_messages(fiche, document), output_format=extraction.EtudeExtraite,
    )
    if reponse.parsed_output is None:
        raise ValueError(f"parsed_output vide (stop_reason={reponse.stop_reason})")
    return reponse.parsed_output, reponse.usage


def regenerer(client: Anthropic, notion: Client, fiches: list, limite: int) -> None:
    faits = _deja_faits()
    a_faire = [f for f in fiches if f["page_id"] not in faits][:limite or None]
    print(f"{len(faits)} déjà faite(s), {len(a_faire)} à faire.")
    # Un même fichier rattaché à deux fiches (doublon dans la base) n'est payé qu'une fois.
    par_url = {r["url_fichier"]: r for r in faits.values() if r.get("url_fichier")}
    cout_total = 0.0
    for numero, fiche in enumerate(a_faire, start=1):
        cout = 0.0
        if fiche["url_fichier"] in par_url:
            etude = {k: v for k, v in par_url[fiche["url_fichier"]].items()
                     if k not in ("page_id", "favori", "cout")}
        else:
            try:
                extraite, usage = _extraire(client, fiche, telecharger(fiche))
            except Exception as erreur:
                print(f"{numero:3} ECHEC {fiche['titre'][:60]} : {erreur}")
                continue
            cout = (usage.input_tokens * test.PRIX_ENTREE + usage.output_tokens * test.PRIX_SORTIE
                    + (usage.cache_read_input_tokens or 0) * test.PRIX_CACHE_LU
                    + (usage.cache_creation_input_tokens or 0) * test.PRIX_CACHE_ECRIT) / 1_000_000
            etude = extraite.model_dump()
            etude["canal"] = ""  # provenance jugée sur l'URL de la fiche (liste blanche)
            etude["doi_url"] = fiche["doi_url"] or etude["doi_url"]
            etude["url_fichier"] = fiche["url_fichier"]
            etude["a_verifier"] = extraite.contenu_insuffisant
            qualification.qualifier([etude], test.DATE_DEPUIS)
            if etude["hors_perimetre"]:
                etude["priorite"] = qualification.FAIBLE
            par_url[fiche["url_fichier"]] = etude
        cout_total += cout

        with open(CHEMIN_RESULTATS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"page_id": fiche["page_id"], "favori": fiche["favori"],
                                "cout": cout, **etude}, ensure_ascii=False) + "\n")

        # Garde-fou : un texte jugé insuffisant ne remplace jamais le résumé existant.
        if etude.get("contenu_insuffisant"):
            print(f"{numero:3} NON ECRIT (contenu jugé insuffisant) {fiche['titre'][:50]}")
            continue
        proprietes = {k: v for k, v in _proprietes(etude).items() if k in COLONNES_ECRITES}
        if COLONNES_INTERDITES & proprietes.keys():
            raise RuntimeError("Tentative d'écriture d'une colonne manuelle : arrêt.")
        _mettre_a_jour(notion, fiche["page_id"], proprietes)
        print(f"{numero:3} {etude['priorite']:10} {cout:.3f} $  {fiche['titre'][:60]}")
    print(f"Coût réel : {cout_total:.2f} $")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--estimer", action="store_true", help="télécharge et compte, sans appel payant")
    parser.add_argument("--limit", type=int, default=0, help="nombre max de fiches à traiter")
    args = parser.parse_args()

    notion = Client(auth=os.environ["NOTION_API_KEY"])
    data_source_id = resoudre_data_source_id(notion, os.environ["NOTION_DATABASE_ID"])
    fiches = lister_fiches_avec_fichier(notion, data_source_id)
    client = Anthropic()
    if args.estimer:
        estimer(client, [f for f in fiches if f["page_id"] not in _deja_faits()])
    else:
        regenerer(client, notion, fiches, args.limit)


if __name__ == "__main__":
    main()
