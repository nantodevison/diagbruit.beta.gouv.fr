"""Étape 7 — phase unique : insertion dans Strapi et Notion (`inserer.py`),
géométrie déposée sur Box, voir `docs/etape-7-conception-technique.md`.

Lit `etape6_{dept}_export.csv` et `etape6_{dept}_geometries/`. Pour chaque
géométrie finale : ajoute `alert_slug` aux propriétés du `.geojson` local,
le dépose dans le dossier Box `--box-folder-id` (un dossier par territoire),
cherche une entrée Strapi/Notion existante par `alert_slug` (idempotence,
voir la conception technique), crée ou met à jour chaque côté indépendamment
— Notion reçoit l'URL Box du fichier dans sa propriété `data`, pas le
fichier lui-même.

**Contrôles bloquants (20/10/2026)** : avant tout appel réseau, l'export
entier est contrôlé — format de chaque `alert_slug` (règle du champ `uid` de
Strapi), unicité, présence du `.geojson`. Au moindre problème, le script
s'arrête sans rien envoyer et liste tous les problèmes trouvés : un slug en
double écraserait une autre règle, et un envoi partiel est plus difficile à
rattraper qu'un envoi qui n'a pas eu lieu.

**Deux environnements Strapi** : `--environnement preprod|prod` (défaut
`preprod`) sélectionne les variables lues par `client_strapi`
(`STRAPI_PREPROD_API_TOKEN`/`STRAPI_PREPROD_URL` ou `STRAPI_PROD_API_TOKEN`/
`STRAPI_PROD_URL`) — voir `docs/etape-7-conception-technique.md`. Notion et
Box n'ont qu'un seul environnement, non concerné par ce choix.

**Dry-run par défaut** : sans `--envoyer`, aucune requête d'écriture n'est
faite sur Strapi, Notion ni Box, et aucun fichier local n'est modifié —
seules les recherches en lecture, pour afficher fidèlement ce qui serait
créé/mis à jour. Cette étape écrit dans des systèmes partagés, visibles par
toute l'équipe métier (voir la conception technique, "Posture") : jamais
d'envoi réel sans ce drapeau explicite.

**Mode `--audit` (20/10/2026)** : lecture seule de Strapi (aucune écriture,
ni Notion ni Box) — état de toutes les entrées de l'environnement, et de
chaque slug de l'export. Voir `auditer`.

Usage :
    python -m etape7_stockage.inserer --dept 033 --box-folder-id 12345                          # dry-run, preprod
    python -m etape7_stockage.inserer --dept 033 --box-folder-id 12345 --envoyer                # envoi réel, preprod
    python -m etape7_stockage.inserer --dept 033 --box-folder-id 12345 --environnement prod --envoyer   # envoi réel, prod
    python -m etape7_stockage.inserer --dept 033 --audit --environnement prod                   # audit, lecture seule

Entrée (dans `output/`, voir `--output-dir`) :
    etape6_{dept}_export.csv
    etape6_{dept}_geometries/

Sortie (dans le même dossier) :
    etape7_{dept}_insertions.csv          — journal des créations/mises à jour, jamais relu (avec --envoyer)
    etape7_{dept}_erreurs.csv             — échecs isolés, si non vide (avec --envoyer)
    etape7_{dept}_audit_{environnement}.csv — état Strapi (avec --audit)
    etape6_{dept}_geometries/*.geojson    — propriété alert_slug ajoutée (avec --envoyer)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from . import client_box, client_notion, client_strapi

load_dotenv()

COLONNES_INSERTIONS = [
    "id_geometrie", "alert_slug", "environnement", "action_strapi", "strapi_document_id",
    "action_notion", "notion_page_id", "date_traitement",
]
COLONNES_ERREURS = ["identifiant", "source", "message", "date_traitement"]
COLONNES_AUDIT = ["alert_slug", "dans_export", "id_geometrie", "document_ids", "brouillon", "publie", "anomalie"]

# Règle du champ `uid` de Strapi (`alert_slug`) — lue dans le code de Strapi
# 5.13.0 (`@strapi/core`, `uidValidator`), version déclarée dans
# cms/package.json. Strapi ne l'applique qu'à la publication, pas au
# brouillon : sans ce contrôle, un slug invalide passerait l'étape 7 et ne
# bloquerait qu'au moment où quelqu'un publie.
MOTIF_UID_STRAPI = re.compile(r"[A-Za-z0-9\-_.~]+")


class ExportCsvIntrouvable(Exception):
    pass


class GeometriesIntrouvables(Exception):
    pass


class ExportInvalide(Exception):
    """Au moins un contrôle bloquant a échoué (voir `_controler_export`) —
    porte la liste complète des problèmes, pas seulement le premier."""

    def __init__(self, problemes: list[str]) -> None:
        super().__init__(f"{len(problemes)} problème(s) dans l'export")
        self.problemes = problemes


class JournalAncienFormat(Exception):
    """Un journal existant n'a pas les colonnes actuelles — y ajouter des
    lignes mélangerait deux formats dans le même fichier."""


def _texte(valeur) -> str:
    return "" if valeur is None else str(valeur).strip()


def _lire_export(chemin: Path) -> list[dict]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier))


def _probleme_format_slug(alert_slug: str) -> str | None:
    """Raison pour laquelle `alert_slug` n'est pas exploitable, ou `None`.
    Statut attendu en sortie d'étape 6 : `automatise` ou `manuel` (voir
    `etape-6-mise-en-forme-diagbruit.md`, "Format de l'alert_slug")."""
    if not alert_slug:
        return "vide"
    if alert_slug.endswith("-"):
        return "incomplet (se termine par '-', terme métier jamais saisi)"
    if alert_slug.count("-") < 2:
        return "forme inattendue (moins de deux '-', attendu alert-{Territoire}-{Terme})"
    if not MOTIF_UID_STRAPI.fullmatch(alert_slug):
        interdits = sorted(set(re.sub(r"[A-Za-z0-9\-_.~]", "", alert_slug)))
        return f"caractère(s) refusé(s) par Strapi : {' '.join(repr(c) for c in interdits)}"
    return None


def _controler_export(lignes: list[dict], dossier_geometries: Path) -> list[str]:
    """Contrôles bloquants sur l'export entier, avant tout appel réseau —
    retourne la liste de tous les problèmes (vide si tout va bien)."""
    problemes: list[str] = []
    for ligne in lignes:
        id_geometrie = _texte(ligne.get("id_geometrie"))
        alert_slug = _texte(ligne.get("alert_slug_propose"))
        raison = _probleme_format_slug(alert_slug)
        if raison:
            problemes.append(f"g{id_geometrie} : alert_slug {alert_slug!r} {raison}")
        chemin_geojson = dossier_geometries / _texte(ligne.get("nom_fichier_geometrie"))
        if not _texte(ligne.get("nom_fichier_geometrie")) or not chemin_geojson.is_file():
            problemes.append(f"g{id_geometrie} : géométrie introuvable ({chemin_geojson})")

    par_slug: dict[str, list[str]] = defaultdict(list)
    for ligne in lignes:
        alert_slug = _texte(ligne.get("alert_slug_propose"))
        if alert_slug:
            par_slug[alert_slug].append(_texte(ligne.get("id_geometrie")))
    for alert_slug, ids in sorted(par_slug.items()):
        if len(ids) > 1:
            problemes.append(
                f"alert_slug {alert_slug!r} en double ({', '.join('g' + i for i in ids)}) — "
                "un envoi écraserait une règle par une autre"
            )
    return problemes


def _ajouter_alert_slug_geojson(chemin: Path, alert_slug: str) -> None:
    """Ajoute (ou remplace) la propriété `alert_slug` de chaque entité du
    `.geojson` local, puis relit le fichier pour vérifier — voir
    `etape-7-conception-technique.md`, "Correctif du 20/10/2026", point 2.

    Le fichier local est modifié volontairement (option retenue le
    20/10/2026) : il reste ainsi identique à celui déposé sur Box, sans
    copie modifiée en mémoire dont personne ne garderait la trace. Jamais
    appelé en dry-run."""
    with chemin.open(encoding="utf-8") as fichier:
        contenu = json.load(fichier)
    entites = contenu.get("features") or []
    if not entites:
        raise ValueError(f"aucune entité dans {chemin}")
    for entite in entites:
        entite.setdefault("properties", {})["alert_slug"] = alert_slug
    with chemin.open("w", encoding="utf-8") as fichier:
        json.dump(contenu, fichier, ensure_ascii=False)
    with chemin.open(encoding="utf-8") as fichier:
        relu = json.load(fichier)
    if any((e.get("properties") or {}).get("alert_slug") != alert_slug for e in relu.get("features") or []):
        raise ValueError(f"alert_slug absent ou différent après réécriture de {chemin}")


def _traiter_strapi(ligne: dict, alert_slug: str, environnement: str, envoyer: bool) -> tuple[str, str, str | None]:
    """Retourne `(action, document_id, message_erreur)` — `action` vaut
    `cree`, `mis_a_jour` ou `""` ; `message_erreur` est `None` en cas de
    succès (ou en dry-run, jamais un échec)."""
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
            return ("cree" if cree else "mis_a_jour"), document_id, None

        etat = client_strapi.etat_entree(alert_slug, environnement)
        if etat.document_id:
            note = (
                " — déjà publiée : la mise à jour ne touchera que le brouillon, "
                "visible sur le site seulement après republication"
                if etat.publie else " (brouillon)"
            )
            print(f"  [Strapi/{environnement}] (dry-run) mettrait à jour {etat.document_id}{note}")
        else:
            print(
                f"  [Strapi/{environnement}] (dry-run) créerait (brouillon) — title={_texte(ligne.get('titre_propose'))!r}, "
                f"content={_texte(ligne.get('message_content'))[:60]!r}..., "
                f"source={_texte(ligne.get('strapi_source'))!r}, reference={_texte(ligne.get('strapi_reference'))!r}, "
                f"label={_texte(ligne.get('label_propose'))!r}"
            )
        return "", etat.document_id or "", None
    except Exception as exc:
        return "", "", str(exc)


def _traiter_notion(
    ligne: dict, alert_slug: str, dossier_geometries: Path, box_folder_id: str, envoyer: bool
) -> tuple[str, str, str | None]:
    """Retourne `(action, page_id, message_erreur)` — mêmes conventions que
    `_traiter_strapi`. Le `.geojson` reçoit `alert_slug` juste avant son
    dépôt sur Box (jamais en dry-run)."""
    try:
        chemin_geojson = dossier_geometries / _texte(ligne.get("nom_fichier_geometrie"))
        if envoyer:
            # Recherche Notion d'abord : un doublon Notion arrête la ligne
            # avant toute écriture, y compris le dépôt Box.
            client_notion.trouver_page_id(alert_slug)
            _ajouter_alert_slug_geojson(chemin_geojson, alert_slug)
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
            return ("cree" if cree else "mis_a_jour"), page_id, None

        existant = client_notion.trouver_page_id(alert_slug)
        if existant:
            print(f"  [Notion] (dry-run) mettrait à jour {existant}")
        else:
            print(
                f"  [Notion] (dry-run) créerait — Territoire={_texte(ligne.get('territoire_propose'))!r}, "
                f"Description={_texte(ligne.get('titre_propose'))[:60]!r}..."
            )
        print(f"  [Box] (dry-run) ajouterait alert_slug={alert_slug!r} à {chemin_geojson.name}, puis déposerait dans {box_folder_id}")
        return "", existant or "", None
    except Exception as exc:
        return "", "", str(exc)


def _ouvrir_journal(chemin: Path):
    """Ouvre le journal en ajout. Refuse d'ajouter à un journal existant
    dont les colonnes diffèrent (format d'avant le 20/10/2026, sans
    `environnement` ni `action_*`) — à renommer à la main avant."""
    if chemin.exists():
        with chemin.open(encoding="utf-8-sig", newline="") as fichier:
            entete = next(csv.reader(fichier), [])
        if entete != COLONNES_INSERTIONS:
            raise JournalAncienFormat(
                f"{chemin.name} a un ancien format (colonnes {entete}). Renommez-le (ex. suffixe _avant_20261020) "
                "avant de relancer : y ajouter des lignes mélangerait deux formats."
            )
    nouveau = not chemin.exists()
    fichier = chemin.open("a", newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(fichier, fieldnames=COLONNES_INSERTIONS)
    if nouveau:
        writer.writeheader()
    return fichier, writer


def _chemins(code_departement: str, dossier_sortie: str | Path) -> tuple[Path, Path, Path]:
    dossier = Path(dossier_sortie)
    chemin_export = dossier / f"etape6_{code_departement}_export.csv"
    dossier_geometries = dossier / f"etape6_{code_departement}_geometries"
    if not chemin_export.exists():
        raise ExportCsvIntrouvable(str(chemin_export))
    if not dossier_geometries.exists():
        raise GeometriesIntrouvables(str(dossier_geometries))
    return dossier, chemin_export, dossier_geometries


def inserer(
    code_departement: str,
    box_folder_id: str,
    environnement: str = "preprod",
    dossier_sortie: str | Path = "output",
    envoyer: bool = False,
) -> Path:
    if environnement not in client_strapi.ENVIRONNEMENTS:
        raise ValueError(f"environnement doit être parmi {client_strapi.ENVIRONNEMENTS}, reçu {environnement!r}.")

    dossier, chemin_export, dossier_geometries = _chemins(code_departement, dossier_sortie)
    lignes = _lire_export(chemin_export)

    # Contrôles bloquants d'abord : rien n'est lu ni écrit à distance tant
    # que l'export entier n'est pas exploitable.
    problemes = _controler_export(lignes, dossier_geometries)
    if problemes:
        raise ExportInvalide(problemes)

    # Vérifié tôt, avant de traiter la moindre ligne — une configuration
    # manquante n'a rien d'un échec isolé, rien n'est exploitable sans elle.
    client_strapi.verifier_configuration(environnement)
    client_notion.verifier_configuration()
    client_box.verifier_configuration()

    date_traitement = date.today().isoformat()

    # Journal écrit ligne par ligne, pas en un seul bloc à la fin — une
    # interruption en cours de route (constaté en réel le 24/08/2026, un
    # run coupé par un timeout externe) laisserait sinon aucune trace locale
    # des lignes déjà traitées avant l'arrêt, alors même que les écritures
    # avaient bien eu lieu côté Strapi/Notion.
    chemin_journal = dossier / f"etape7_{code_departement}_insertions.csv"
    fichier_journal, writer_journal = _ouvrir_journal(chemin_journal) if envoyer else (None, None)
    nb_journalisees = 0
    erreurs: list[dict] = []

    try:
        for ligne in lignes:
            id_geometrie = _texte(ligne.get("id_geometrie"))
            alert_slug = _texte(ligne.get("alert_slug_propose"))
            print(f"{id_geometrie} — {alert_slug}")

            action_strapi, strapi_document_id, erreur_strapi = _traiter_strapi(
                ligne, alert_slug, environnement, envoyer
            )
            if erreur_strapi:
                erreurs.append(
                    {"identifiant": alert_slug, "source": "strapi", "message": erreur_strapi, "date_traitement": date_traitement}
                )

            action_notion, notion_page_id, erreur_notion = _traiter_notion(
                ligne, alert_slug, dossier_geometries, box_folder_id, envoyer
            )
            if erreur_notion:
                erreurs.append(
                    {"identifiant": alert_slug, "source": "notion", "message": erreur_notion, "date_traitement": date_traitement}
                )

            if writer_journal is not None and (action_strapi or action_notion):
                writer_journal.writerow(
                    {
                        "id_geometrie": id_geometrie,
                        "alert_slug": alert_slug,
                        "environnement": environnement,
                        "action_strapi": action_strapi,
                        "strapi_document_id": strapi_document_id,
                        "action_notion": action_notion,
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

    # En dry-run, les erreurs sont affichées mais aucun fichier n'est écrit
    # (voir "Mode dry-run" dans la conception technique).
    chemin_erreurs = dossier / f"etape7_{code_departement}_erreurs.csv"
    if erreurs:
        for erreur in erreurs:
            print(f"ERREUR [{erreur['source']}] {erreur['identifiant']} : {erreur['message']}")
        if envoyer:
            with chemin_erreurs.open("w", newline="", encoding="utf-8-sig") as fichier:
                writer = csv.DictWriter(fichier, fieldnames=COLONNES_ERREURS)
                writer.writeheader()
                writer.writerows(erreurs)
            print(f"{len(erreurs)} erreur(s), listée(s) dans {chemin_erreurs}.")
    elif envoyer and chemin_erreurs.exists():
        chemin_erreurs.unlink()

    if not envoyer:
        print(f"\nDry-run — rien n'a été envoyé ni modifié ({len(erreurs)} erreur(s)). "
              "Relancez avec --envoyer pour écrire réellement.")

    return chemin_erreurs


def auditer(code_departement: str, environnement: str, dossier_sortie: str | Path = "output") -> Path:
    """Mode `--audit` : lecture seule de Strapi (que des `GET`), pour
    établir des faits sur l'état d'un environnement — en réponse au retour
    de l'équipe de dev du 19/10/2026 (identifiants dupliqués, PLU manquants
    entre prod et préprod). Écrit `etape7_{dept}_audit_{environnement}.csv`,
    une ligne par `alert_slug` présent dans Strapi ou dans l'export.

    Anomalies relevées :
    - `doublon` : plusieurs documents portent le même slug ;
    - `publie_sans_brouillon` : un document publié sans version brouillon,
      état anormal en Strapi 5 (tout document publié en a une) — c'est le
      cas que l'équipe de dev signale comme cassant l'admin ;
    - `absent` : slug de l'export absent de Strapi.
    Un brouillon seul n'est pas une anomalie : c'est l'état normal d'une
    entrée créée par ce script et jamais publiée — invisible sur le site
    (le front ne lit que les publiées) tant que personne ne la publie."""
    if environnement not in client_strapi.ENVIRONNEMENTS:
        raise ValueError(f"environnement doit être parmi {client_strapi.ENVIRONNEMENTS}, reçu {environnement!r}.")
    dossier, chemin_export, _ = _chemins(code_departement, dossier_sortie)
    client_strapi.verifier_configuration(environnement)

    export = {_texte(l.get("alert_slug_propose")): _texte(l.get("id_geometrie")) for l in _lire_export(chemin_export)}
    brouillons = client_strapi.lister_entrees("draft", environnement)
    publies = client_strapi.lister_entrees("published", environnement)

    documents_par_slug: dict[str, set[str]] = defaultdict(set)
    ids_brouillon: set[str] = set()
    ids_publie: set[str] = set()
    for entree in brouillons:
        documents_par_slug[_texte(entree.get("alert_slug"))].add(entree["documentId"])
        ids_brouillon.add(entree["documentId"])
    for entree in publies:
        documents_par_slug[_texte(entree.get("alert_slug"))].add(entree["documentId"])
        ids_publie.add(entree["documentId"])

    lignes_audit = []
    compteur = Counter()
    for alert_slug in sorted(set(documents_par_slug) | set(export)):
        documents = documents_par_slug.get(alert_slug, set())
        anomalies = []
        if len(documents) > 1:
            anomalies.append("doublon")
        if any(d in ids_publie and d not in ids_brouillon for d in documents):
            anomalies.append("publie_sans_brouillon")
        if alert_slug in export and not documents:
            anomalies.append("absent")
        compteur.update(anomalies)
        lignes_audit.append(
            {
                "alert_slug": alert_slug,
                "dans_export": "oui" if alert_slug in export else "non",
                "id_geometrie": export.get(alert_slug, ""),
                "document_ids": " ".join(sorted(documents)),
                "brouillon": "oui" if documents & ids_brouillon else "non",
                "publie": "oui" if documents & ids_publie else "non",
                "anomalie": " ".join(anomalies),
            }
        )

    chemin_audit = dossier / f"etape7_{code_departement}_audit_{environnement}.csv"
    with chemin_audit.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES_AUDIT)
        writer.writeheader()
        writer.writerows(lignes_audit)

    dans_export = [l for l in lignes_audit if l["dans_export"] == "oui"]
    print(f"Strapi/{environnement} : {len(ids_brouillon)} document(s) avec brouillon, {len(ids_publie)} publié(s), "
          f"{len(documents_par_slug)} slug(s) distinct(s).")
    print(f"Anomalies : {compteur['doublon']} slug(s) en doublon, "
          f"{compteur['publie_sans_brouillon']} publié(s) sans brouillon.")
    print(f"Export {code_departement} : {len(dans_export)} slug(s) — "
          f"{sum(l['publie'] == 'oui' for l in dans_export)} publié(s), "
          f"{sum(l['brouillon'] == 'oui' and l['publie'] == 'non' for l in dans_export)} en brouillon seul, "
          f"{compteur['absent']} absent(s).")
    print(f"Détail : {chemin_audit}")
    return chemin_audit


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
        help=(
            "Identifiant du dossier Box cible pour les géométries (un dossier par territoire, "
            "jamais résolu automatiquement — voir docs/etape-7-conception-technique.md). "
            "Requis, sauf avec --audit."
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--envoyer",
        action="store_true",
        help="Exécute réellement les créations/mises à jour. Sans ce drapeau : dry-run, rien n'est envoyé.",
    )
    mode.add_argument(
        "--audit",
        action="store_true",
        help="Lecture seule : état de Strapi pour cet environnement et pour les slugs de l'export.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.audit and not args.box_folder_id:
        parser.error("--box-folder-id est requis (sauf avec --audit).")

    mode = "AUDIT (lecture seule)" if args.audit else ("ENVOI RÉEL" if args.envoyer else "dry-run")
    print(f"Étape 7 — département {args.dept} — Strapi/{args.environnement} — {mode}")
    try:
        if args.audit:
            auditer(args.dept, args.environnement, dossier_sortie=args.output_dir)
        else:
            inserer(
                args.dept,
                args.box_folder_id,
                environnement=args.environnement,
                dossier_sortie=args.output_dir,
                envoyer=args.envoyer,
            )
    except ExportInvalide as exc:
        print(f"Arrêt avant tout envoi — {exc} :", file=sys.stderr)
        for probleme in exc.problemes:
            print(f"  - {probleme}", file=sys.stderr)
        return 1
    except ExportCsvIntrouvable as exc:
        print(f"Arrêt : etape6_{args.dept}_export.csv introuvable ({exc}).", file=sys.stderr)
        return 1
    except GeometriesIntrouvables as exc:
        print(f"Arrêt : etape6_{args.dept}_geometries/ introuvable ({exc}).", file=sys.stderr)
        return 1
    except JournalAncienFormat as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
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
