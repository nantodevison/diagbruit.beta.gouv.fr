"""Étape 8 — phase unique : publication en préprod des alertes Strapi d'un
département (`publier.py`), voir `docs/etape-8-publication-diagbruit.md`
(cadrage) et `docs/etape-8-conception-technique.md` (implémentation).

Lit `etape6_{dept}_export.csv` pour connaître les `alert_slug` du
département, cherche chacun dans Strapi (brouillon et publié) et publie les
brouillons jamais publiés. Une alerte déjà publiée n'est jamais republiée.

**Préprod uniquement** (décision du 13/11/2026) : `--environnement prod`
est refusé avant tout appel réseau.

**Dry-run par défaut** : sans `--publier`, rien n'est écrit, ni dans
Strapi ni sur le disque — seules des lectures sont faites.

⚠️ **Hypothèse non vérifiée** sur la manière de publier par l'API (voir
`client_strapi._put_publication` et la conception technique). D'où :
- la comparaison automatique brouillon / version publiée après chaque
  publication, avec arrêt immédiat à la première différence ;
- `--ids`, pour publier d'abord une seule alerte et la vérifier à l'œil.

Usage, depuis poc-urbanisme-plu/ :
    python -m etape8_publication.publier --dept 067 --output-dir output/067_horsEurometropole                     # dry-run
    python -m etape8_publication.publier --dept 067 --output-dir output/067_horsEurometropole --ids 1 --publier   # une alerte
    python -m etape8_publication.publier --dept 067 --output-dir output/067_horsEurometropole --publier           # tout

Sortie (dans le dossier de l'export, avec --publier seulement) :
    etape8_{dept}_publications.csv — journal des publications, jamais relu
    etape8_{dept}_erreurs.csv      — erreurs, absent si rien à signaler
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from etape7_stockage import client_strapi

load_dotenv()

COLONNES_PUBLICATIONS = ["id_geometrie", "alert_slug", "environnement", "strapi_document_id", "date_traitement"]
COLONNES_ERREURS = ["identifiant", "source", "message", "date_traitement"]


class ArretPublication(Exception):
    """Arrêt avant tout appel réseau (fichier absent, id inconnu, prod…)."""


class PublicationNonConforme(Exception):
    """La version publiée diffère du brouillon, ou est introuvable : on
    arrête tout, car l'erreur est très probablement systématique."""


def _texte(valeur) -> str:
    return "" if valeur is None else str(valeur).strip()


def _lignes_a_traiter(chemin_export: Path, ids: list[str] | None) -> list[dict]:
    """Lignes de l'export, filtrées sur `ids` si fourni. Un id absent de
    l'export arrête tout : mieux vaut une faute de frappe signalée qu'une
    publication partielle silencieuse."""
    if not chemin_export.exists():
        raise ArretPublication(f"export introuvable : {chemin_export}")
    with chemin_export.open(encoding="utf-8-sig", newline="") as fichier:
        lignes = list(csv.DictReader(fichier))
    if not ids:
        return lignes
    connus = {_texte(l.get("id_geometrie")) for l in lignes}
    inconnus = [i for i in ids if i not in connus]
    if inconnus:
        raise ArretPublication(f"id_geometrie absent(s) de l'export : {', '.join(inconnus)}")
    return [l for l in lignes if _texte(l.get("id_geometrie")) in set(ids)]


def _differences(brouillon: dict, publie: dict | None) -> list[str]:
    """Champs qui diffèrent entre le brouillon (lu avant publication) et la
    version publiée (lue après). Liste vide = publication conforme."""
    if publie is None:
        return ["version publiée introuvable après l'appel"]
    return [
        f"{champ} : brouillon {brouillon.get(champ)!r} ≠ publié {publie.get(champ)!r}"
        for champ in client_strapi.CHAMPS_COMPARES
        if brouillon.get(champ) != publie.get(champ)
    ]


def _publier_une(document_id: str, environnement: str) -> None:
    """Lit le brouillon, publie, relit la version publiée et compare. Lève
    `PublicationNonConforme` à la moindre différence."""
    brouillon = client_strapi.lire_entree(document_id, "draft", environnement)
    if brouillon is None:
        raise PublicationNonConforme(f"brouillon {document_id} introuvable juste avant publication")
    client_strapi.publier(document_id, environnement)
    publie = client_strapi.lire_entree(document_id, "published", environnement)
    differences = _differences(brouillon, publie)
    if differences:
        raise PublicationNonConforme(f"{document_id} : " + " ; ".join(differences))


def publier_departement(
    code_departement: str,
    dossier_sortie: str | Path,
    environnement: str = "preprod",
    ids: list[str] | None = None,
    publier: bool = False,
) -> Counter:
    if environnement != "preprod":
        raise ArretPublication(
            f"publication refusée sur {environnement!r} : préprod uniquement (décision du 13/11/2026)."
        )
    dossier = Path(dossier_sortie)
    lignes = _lignes_a_traiter(dossier / f"etape6_{code_departement}_export.csv", ids)
    client_strapi.verifier_configuration(environnement)

    date_traitement = date.today().isoformat()
    compteur: Counter = Counter()
    erreurs: list[dict] = []

    chemin_journal = dossier / f"etape8_{code_departement}_publications.csv"
    fichier_journal = writer = None
    if publier:
        nouveau = not chemin_journal.exists()
        fichier_journal = chemin_journal.open("a", newline="", encoding="utf-8-sig")
        writer = csv.DictWriter(fichier_journal, fieldnames=COLONNES_PUBLICATIONS)
        if nouveau:
            writer.writeheader()

    def erreur(alert_slug: str, source: str, message: str) -> None:
        compteur[source] += 1
        erreurs.append({"identifiant": alert_slug, "source": source, "message": message,
                        "date_traitement": date_traitement})
        print(f"  ERREUR [{source}] {message}")

    try:
        for ligne in lignes:
            id_geometrie = _texte(ligne.get("id_geometrie"))
            alert_slug = _texte(ligne.get("alert_slug_propose"))
            print(f"{id_geometrie} — {alert_slug}")

            try:
                etat = client_strapi.etat_entree(alert_slug, environnement)
            except client_strapi.DoublonStrapi as exc:
                erreur(alert_slug, "doublon", str(exc))
                continue
            if not etat.document_id:
                erreur(alert_slug, "absent", "aucun document Strapi pour ce slug (étape 7 non faite ?)")
                continue
            if etat.publie:
                compteur["deja_publiee"] += 1
                print(f"  déjà publiée ({etat.document_id}) — laissée telle quelle")
                continue

            if not publier:
                compteur["a_publier"] += 1
                print(f"  (dry-run) publierait {etat.document_id}")
                continue

            try:
                _publier_une(etat.document_id, environnement)
            except PublicationNonConforme as exc:
                # Tracée dans etape8_{dept}_erreurs.csv (écrit dans le
                # `finally`), puis arrêt de tout le run.
                erreur(alert_slug, "verification", str(exc))
                raise
            except Exception as exc:
                erreur(alert_slug, "strapi", f"{etat.document_id} : {exc}")
                continue
            compteur["publiee"] += 1
            print(f"  publiée ({etat.document_id}) — version publiée identique au brouillon")
            writer.writerow({"id_geometrie": id_geometrie, "alert_slug": alert_slug,
                             "environnement": environnement, "strapi_document_id": etat.document_id,
                             "date_traitement": date_traitement})
            fichier_journal.flush()
    finally:
        if fichier_journal is not None:
            fichier_journal.close()
        if publier:
            chemin_erreurs = dossier / f"etape8_{code_departement}_erreurs.csv"
            if erreurs:
                with chemin_erreurs.open("w", newline="", encoding="utf-8-sig") as fichier:
                    w = csv.DictWriter(fichier, fieldnames=COLONNES_ERREURS)
                    w.writeheader()
                    w.writerows(erreurs)
            elif chemin_erreurs.exists():
                chemin_erreurs.unlink()

    return compteur


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Étape 8 — publie en préprod les brouillons Strapi d'un département (dry-run par défaut)."
    )
    parser.add_argument("--dept", required=True, help="Code département (ex. 067).")
    parser.add_argument("--output-dir", default="output", help="Dossier contenant etape6_{dept}_export.csv.")
    parser.add_argument(
        "--environnement", default="preprod", choices=client_strapi.ENVIRONNEMENTS,
        help="Seul 'preprod' est accepté à ce jour (décision du 13/11/2026).",
    )
    parser.add_argument(
        "--ids", nargs="+", metavar="ID",
        help="Limite la publication à ces id_geometrie (ex. pour le test sur une seule alerte).",
    )
    parser.add_argument(
        "--publier", action="store_true",
        help="Publie réellement. Sans ce drapeau : dry-run, rien n'est écrit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Console Windows : sans cela, un caractère hors de l'encodage local (ex. « → »)
    # ferait planter un print — potentiellement juste après une écriture réussie.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    mode = "PUBLICATION RÉELLE" if args.publier else "dry-run"
    print(f"Étape 8 — département {args.dept} — Strapi/{args.environnement} — {mode}")
    try:
        compteur = publier_departement(
            args.dept, args.output_dir, environnement=args.environnement, ids=args.ids, publier=args.publier
        )
    except ArretPublication as exc:
        print(f"Arrêt avant tout envoi : {exc}", file=sys.stderr)
        return 1
    except PublicationNonConforme as exc:
        print(f"\nARRÊT — publication non conforme : {exc}\n"
              "Vérifier ce document dans l'admin Strapi avant toute relance "
              "(voir docs/etape-8-conception-technique.md).", file=sys.stderr)
        return 2
    except client_strapi.ConfigurationStrapiManquante as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
        return 1

    print("\nBilan : " + ", ".join(f"{cle} {valeur}" for cle, valeur in sorted(compteur.items())))
    if not args.publier:
        print("Dry-run — rien n'a été publié. Relancez avec --publier pour publier réellement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
