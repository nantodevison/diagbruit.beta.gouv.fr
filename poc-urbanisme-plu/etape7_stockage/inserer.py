"""Étape 7 — phase unique : insertion dans Strapi et Notion (`inserer.py`),
géométrie déposée sur Box, voir `docs/etape-7-conception-technique.md`.

Lit `etape6_{dept}_export.csv` et `etape6_{dept}_geometries/`. Pour chaque
géométrie finale : dépose le `.geojson` dans le dossier Box `--box-folder-id`
(un dossier par territoire), cherche une entrée Strapi/Notion existante par
`alert_slug` (idempotence, voir la conception technique), crée ou met à
jour chaque côté indépendamment — Notion reçoit l'URL Box du fichier dans sa
propriété `data`, pas le fichier lui-même.

**Deux environnements Strapi** : `--environnement preprod|prod` (défaut
`preprod`) sélectionne les variables lues par `client_strapi`
(`STRAPI_PREPROD_API_TOKEN`/`STRAPI_PREPROD_URL` ou `STRAPI_PROD_API_TOKEN`/
`STRAPI_PROD_URL`) — voir `docs/etape-7-conception-technique.md`. Notion et
Box n'ont qu'un seul environnement, non concerné par ce choix.

**Dry-run par défaut** : sans `--envoyer`, aucune requête d'écriture n'est
faite sur Strapi, Notion ni Box — seules les recherches en lecture, pour
afficher fidèlement ce qui serait créé/mis à jour. Cette étape écrit dans des
systèmes partagés, visibles par toute l'équipe métier (voir la conception
technique, "Posture") : jamais d'envoi réel sans ce drapeau explicite.

Usage :
    python -m etape7_stockage.inserer --dept 033 --box-folder-id 12345                          # dry-run, preprod
    python -m etape7_stockage.inserer --dept 033 --box-folder-id 12345 --envoyer                # envoi réel, preprod
    python -m etape7_stockage.inserer --dept 033 --box-folder-id 12345 --environnement prod --envoyer   # envoi réel, prod

Entrée (dans `output/`, voir `--output-dir`) :
    etape6_{dept}_export.csv
    etape6_{dept}_geometries/

Sortie (dans le même dossier, uniquement avec `--envoyer`) :
    etape7_{dept}_insertions.csv   — journal des créations/mises à jour, jamais relu
    etape7_{dept}_erreurs.csv      — échecs isolés, si non vide
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from . import client_box, client_notion, client_strapi

load_dotenv()

COLONNES_INSERTIONS = ["id_geometrie", "alert_slug", "strapi_document_id", "notion_page_id", "date_traitement"]
COLONNES_ERREURS = ["identifiant", "source", "message", "date_traitement"]


class ExportCsvIntrouvable(Exception):
    pass


class GeometriesIntrouvables(Exception):
    pass


def _texte(valeur) -> str:
    return "" if valeur is None else str(valeur).strip()


def _alert_slug_incomplet(alert_slug: str) -> bool:
    """Un `alert_slug` vide ou encore terminé par `-` (proposition
    mécanique jamais complétée par l'opérateur dans `outil_validation.html`,
    voir `etape-6-conception-technique.md`) n'est pas exploitable."""
    return not alert_slug or alert_slug.endswith("-")


def _lire_export(chemin: Path) -> list[dict]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier))


def _traiter_strapi(ligne: dict, alert_slug: str, environnement: str, envoyer: bool) -> tuple[str, str | None]:
    """Retourne `(document_id, message_erreur)` — `message_erreur` est
    `None` en cas de succès (ou en dry-run, jamais un échec)."""
    try:
        if envoyer:
            champs = client_strapi.ChampsNoisezoneAlert(
                alert_slug=alert_slug,
                title=_texte(ligne.get("titre_propose")),
                message_content=_texte(ligne.get("message_content")),
                source=_texte(ligne.get("strapi_source")),
                reference=_texte(ligne.get("strapi_reference")),
                label=_texte(ligne.get("label_propose")),
            )
            document_id, cree = client_strapi.creer_ou_mettre_a_jour(champs, environnement)
            print(f"  [Strapi/{environnement}] {'créé' if cree else 'mis à jour'} ({document_id})")
        else:
            existant = client_strapi.trouver_document_id(alert_slug, environnement)
            document_id = existant or ""
            if existant:
                print(f"  [Strapi/{environnement}] (dry-run) mettrait à jour {existant}")
            else:
                print(
                    f"  [Strapi/{environnement}] (dry-run) créerait — title={_texte(ligne.get('titre_propose'))!r}, "
                    f"content={_texte(ligne.get('message_content'))[:60]!r}..., "
                    f"source={_texte(ligne.get('strapi_source'))!r}, reference={_texte(ligne.get('strapi_reference'))!r}, "
                    f"label={_texte(ligne.get('label_propose'))!r}"
                )
        return document_id, None
    except Exception as exc:
        return "", str(exc)


def _traiter_notion(
    ligne: dict, alert_slug: str, dossier_geometries: Path, box_folder_id: str, envoyer: bool
) -> tuple[str, str | None]:
    """Retourne `(page_id, message_erreur)` — `message_erreur` est `None`
    en cas de succès (ou en dry-run, jamais un échec)."""
    try:
        chemin_geojson = dossier_geometries / _texte(ligne.get("nom_fichier_geometrie"))
        if envoyer:
            if not chemin_geojson.exists():
                raise FileNotFoundError(f"géométrie introuvable : {chemin_geojson}")
            url_geometrie = client_box.televerser_geometrie(chemin_geojson, box_folder_id)
            champs = client_notion.ChampsPageNotion(
                territoire=_texte(ligne.get("territoire_propose")),
                description=_texte(ligne.get("titre_propose")),
                alert_slug=alert_slug,
                url_geometrie=url_geometrie,
                nom_fichier=chemin_geojson.name,
            )
            page_id, cree = client_notion.creer_ou_mettre_a_jour(champs)
            print(f"  [Notion] {'créé' if cree else 'mis à jour'} ({page_id}) — géométrie : {url_geometrie}")
        else:
            existant = client_notion.trouver_page_id(alert_slug)
            page_id = existant or ""
            if existant:
                print(f"  [Notion] (dry-run) mettrait à jour {existant}")
            else:
                print(
                    f"  [Notion] (dry-run) créerait — Territoire={_texte(ligne.get('territoire_propose'))!r}, "
                    f"Description={_texte(ligne.get('titre_propose'))[:60]!r}..., "
                    f"géométrie={chemin_geojson.name!r} ({'présente' if chemin_geojson.exists() else 'MANQUANTE'}) "
                    f"→ Box dossier {box_folder_id}"
                )
        return page_id, None
    except Exception as exc:
        return "", str(exc)


def inserer(
    code_departement: str,
    box_folder_id: str,
    environnement: str = "preprod",
    dossier_sortie: str | Path = "output",
    envoyer: bool = False,
) -> Path:
    if environnement not in client_strapi.ENVIRONNEMENTS:
        raise ValueError(f"environnement doit être parmi {client_strapi.ENVIRONNEMENTS}, reçu {environnement!r}.")

    dossier = Path(dossier_sortie)
    chemin_export = dossier / f"etape6_{code_departement}_export.csv"
    dossier_geometries = dossier / f"etape6_{code_departement}_geometries"

    if not chemin_export.exists():
        raise ExportCsvIntrouvable(str(chemin_export))
    if not dossier_geometries.exists():
        raise GeometriesIntrouvables(str(dossier_geometries))

    # Vérifié tôt, avant de traiter la moindre ligne — une configuration
    # manquante n'a rien d'un échec isolé, rien n'est exploitable sans elle.
    client_strapi.verifier_configuration(environnement)
    client_notion.verifier_configuration()
    client_box.verifier_configuration()

    lignes = _lire_export(chemin_export)
    date_traitement = date.today().isoformat()

    # Journal écrit ligne par ligne, pas en un seul bloc à la fin — une
    # interruption en cours de route (constaté en réel le 24/08/2026, un
    # run coupé par un timeout externe) laisserait sinon aucune trace locale
    # des lignes déjà traitées avant l'arrêt, alors même que les écritures
    # avaient bien eu lieu côté Strapi/Notion.
    chemin_journal = dossier / f"etape7_{code_departement}_insertions.csv" if envoyer else None
    fichier_journal = None
    writer_journal = None
    nb_journalisees = 0
    if chemin_journal is not None:
        nouveau = not chemin_journal.exists()
        fichier_journal = chemin_journal.open("a", newline="", encoding="utf-8-sig")
        writer_journal = csv.DictWriter(fichier_journal, fieldnames=COLONNES_INSERTIONS)
        if nouveau:
            writer_journal.writeheader()

    erreurs: list[dict] = []

    try:
        for ligne in lignes:
            id_geometrie = _texte(ligne.get("id_geometrie"))
            alert_slug = _texte(ligne.get("alert_slug_propose"))
            print(f"{id_geometrie} — {alert_slug or '(alert_slug vide)'}")

            if _alert_slug_incomplet(alert_slug):
                erreurs.append(
                    {
                        "identifiant": id_geometrie,
                        "source": "validation",
                        "message": (
                            f"alert_slug incomplet ou vide ({alert_slug!r}) — à compléter dans "
                            "outil_validation.html (étape 6) avant l'insertion."
                        ),
                        "date_traitement": date_traitement,
                    }
                )
                continue

            strapi_document_id, erreur_strapi = _traiter_strapi(ligne, alert_slug, environnement, envoyer)
            if erreur_strapi:
                erreurs.append(
                    {
                        "identifiant": alert_slug,
                        "source": "strapi",
                        "message": erreur_strapi,
                        "date_traitement": date_traitement,
                    }
                )

            notion_page_id, erreur_notion = _traiter_notion(
                ligne, alert_slug, dossier_geometries, box_folder_id, envoyer
            )
            if erreur_notion:
                erreurs.append(
                    {
                        "identifiant": alert_slug,
                        "source": "notion",
                        "message": erreur_notion,
                        "date_traitement": date_traitement,
                    }
                )

            if writer_journal is not None and (strapi_document_id or notion_page_id):
                writer_journal.writerow(
                    {
                        "id_geometrie": id_geometrie,
                        "alert_slug": alert_slug,
                        "strapi_document_id": strapi_document_id,
                        "notion_page_id": notion_page_id,
                        "date_traitement": date_traitement,
                    }
                )
                fichier_journal.flush()
                nb_journalisees += 1
    finally:
        if fichier_journal is not None:
            fichier_journal.close()

    if nb_journalisees:
        print(f"{nb_journalisees} ligne(s) journalisée(s) dans {chemin_journal}.")

    chemin_erreurs = dossier / f"etape7_{code_departement}_erreurs.csv"
    if erreurs:
        with chemin_erreurs.open("w", newline="", encoding="utf-8-sig") as fichier:
            writer = csv.DictWriter(fichier, fieldnames=COLONNES_ERREURS)
            writer.writeheader()
            writer.writerows(erreurs)
        print(f"{len(erreurs)} erreur(s), listée(s) dans {chemin_erreurs}.")
    elif chemin_erreurs.exists():
        chemin_erreurs.unlink()

    if not envoyer:
        print("\nDry-run — rien n'a été envoyé. Relancez avec --envoyer pour écrire réellement.")

    return chemin_erreurs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Étape 7 — insère/met à jour les entrées Strapi et Notion depuis etape6_{dept}_export.csv."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit (ex. 033, 971) — doit correspondre à un etape6_{dept}_export.csv existant.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des fichiers (défaut : output/).",
    )
    parser.add_argument(
        "--box-folder-id",
        required=True,
        help=(
            "Identifiant du dossier Box cible pour les géométries (un dossier par territoire, "
            "jamais résolu automatiquement — voir docs/etape-7-conception-technique.md)."
        ),
    )
    parser.add_argument(
        "--environnement",
        choices=client_strapi.ENVIRONNEMENTS,
        default="preprod",
        help=(
            "Environnement Strapi cible : préprod (défaut, STRAPI_PREPROD_API_TOKEN/STRAPI_PREPROD_URL) "
            "ou prod (STRAPI_PROD_API_TOKEN/STRAPI_PROD_URL)."
        ),
    )
    parser.add_argument(
        "--envoyer",
        action="store_true",
        help="Exécute réellement les créations/mises à jour. Sans ce drapeau : dry-run, rien n'est envoyé.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(
        f"Étape 7 — département {args.dept} — Strapi/{args.environnement} — "
        f"{'ENVOI RÉEL' if args.envoyer else 'dry-run'}"
    )
    try:
        inserer(
            args.dept,
            args.box_folder_id,
            environnement=args.environnement,
            dossier_sortie=args.output_dir,
            envoyer=args.envoyer,
        )
    except ExportCsvIntrouvable as exc:
        print(f"Arrêt : etape6_{args.dept}_export.csv introuvable ({exc}).", file=sys.stderr)
        return 1
    except GeometriesIntrouvables as exc:
        print(f"Arrêt : etape6_{args.dept}_geometries/ introuvable ({exc}).", file=sys.stderr)
        return 1
    except (
        client_strapi.ConfigurationStrapiManquante,
        client_notion.ConfigurationNotionManquante,
        client_box.ConfigurationBoxManquante,
    ) as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
