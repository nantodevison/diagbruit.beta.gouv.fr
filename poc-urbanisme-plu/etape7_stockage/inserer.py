"""Étape 7 — phase unique : insertion dans Strapi et Notion (`inserer.py`),
géométrie déposée sur Box, voir `docs/etape-7-conception-technique.md`.

Lit `etape6_{dept}_export.csv` et `etape6_{dept}_geometries/`.

**Un fichier géométrie par territoire (16/11/2026)** : les géométries des
zones d'un même `territoire_propose` sont réunies dans un seul `.geojson`
(une entité par zone, avec `id_geometrie` et `alert_slug`), écrit dans
`etape7_{dept}_geometries/` puis déposé une fois dans le dossier Box
`--box-folder-id`. Raison : Dagster, qui charge ces fichiers, ne supportait
pas un fichier par zone (398 pour le 067).

Puis, pour chaque zone : cherche une entrée Strapi/Notion existante par
`alert_slug` (idempotence, voir la conception technique), crée ou met à jour
chaque côté indépendamment — Notion reçoit dans `data` l'URL Box du fichier
de son territoire, pas le fichier lui-même.

**Contrôles bloquants (20/10/2026)** : avant tout appel réseau, l'export
entier est contrôlé — format de chaque `alert_slug` (règle du champ `uid` de
Strapi), unicité, présence du `.geojson`, champs obligatoires de Strapi non
vides et `label` autorisé. Au moindre problème, le script
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
    etape7_{dept}_geometries/{dept}_{Territoire}.geojson — un fichier par territoire, identique à Box (avec --envoyer)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
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

# Champs obligatoires du schéma Strapi (cms/src/api/noisezone-alert/
# content-types/noisezone-alert/schema.json : source, reference, label —
# alert_slug est contrôlé à part), avec la colonne de l'export qui les
# alimente. Même piège que pour le format du slug : Strapi 5.13.0 ne les
# vérifie qu'à la publication (`required: !isDraft && attr.required`,
# @strapi/core, entity-validator) — vides, l'alerte serait créée en brouillon
# puis impossible à publier. `message_content` (champ `content`, non
# obligatoire côté Strapi) est ajouté : une alerte sans message n'a pas de sens.
CHAMPS_OBLIGATOIRES = {
    "strapi_source": "source",
    "strapi_reference": "reference",
    "label_propose": "label",
    "message_content": "content",
}
LABELS_AUTORISES = ("ZONE SOUMISE AU BRUIT", "ZONE CALME")  # enum `label` du schéma Strapi

# Ligatures à translittérer avant le retrait des accents — même règle que
# `_slugifier_nom` de l'étape 6 (recopiée plutôt qu'importée : chaque étape
# reste indépendante du code des autres).
LIGATURES = {"œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE", "ß": "ss"}


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


def _slugifier_nom(nom: str) -> str:
    """Réduit un nom de territoire à `A-Z a-z 0-9`, casse conservée (ex.
    "CC de l'Alsace Bossue" → `CCdelAlsaceBossue`) — même règle que les
    slugs de l'étape 6, pour que le nom du fichier se lise comme le slug."""
    texte = nom
    for ligature, remplacement in LIGATURES.items():
        texte = texte.replace(ligature, remplacement)
    sans_accents = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]", "", sans_accents)


def _nom_fichier_territoire(code_departement: str, territoire: str) -> str:
    """Nom du `.geojson` qui regroupe les zones d'un territoire (évolution
    du 16/11/2026), ex. `067_CCdelAlsaceBossue.geojson`."""
    return f"{code_departement}_{_slugifier_nom(territoire)}.geojson"


def _lire_geojson(chemin: Path) -> dict:
    with chemin.open(encoding="utf-8") as fichier:
        return json.load(fichier)


def _controler_geometries(lignes: list[dict], dossier_geometries: Path, code_departement: str) -> list[str]:
    """Contrôles propres au regroupement par territoire (16/11/2026) :
    territoire renseigné, noms de fichiers sans collision, `.geojson` non
    vides et tous dans le même système de coordonnées — sans quoi on
    mélangerait des coordonnées incompatibles dans un même fichier."""
    problemes: list[str] = []
    territoires_par_fichier: dict[str, set[str]] = defaultdict(set)
    crs_vus: dict[str, list[str]] = defaultdict(list)
    for ligne in lignes:
        id_geometrie = _texte(ligne.get("id_geometrie"))
        territoire = _texte(ligne.get("territoire_propose"))
        if not territoire:
            problemes.append(f"g{id_geometrie} : territoire_propose vide — impossible de choisir son fichier géométrie")
        else:
            territoires_par_fichier[_nom_fichier_territoire(code_departement, territoire)].add(territoire)
        chemin = dossier_geometries / _texte(ligne.get("nom_fichier_geometrie"))
        if not chemin.is_file():
            continue  # déjà signalé par `_controler_export`
        contenu = _lire_geojson(chemin)
        if not contenu.get("features"):
            problemes.append(f"g{id_geometrie} : aucune entité dans {chemin.name}")
        crs_vus[json.dumps(contenu.get("crs"), sort_keys=True)].append(id_geometrie)
    for nom_fichier, territoires in sorted(territoires_par_fichier.items()):
        if len(territoires) > 1:
            problemes.append(f"territoires {sorted(territoires)} donneraient le même fichier {nom_fichier}")
    if len(crs_vus) > 1:
        detail = " ; ".join(f"{crs} ({len(ids)} fichier(s))" for crs, ids in crs_vus.items())
        problemes.append(f"systèmes de coordonnées différents entre les géométries : {detail}")
    return problemes


def _fichiers_par_territoire(lignes: list[dict], dossier_geometries: Path, code_departement: str) -> dict[str, dict]:
    """Regroupe les géométries de l'étape 6 par territoire, en mémoire.
    Retourne `{territoire: {"nom_fichier", "contenu", "nb_entites"}}` ;
    chaque entité reçoit `id_geometrie` et `alert_slug` en propriétés —
    c'est `alert_slug` qui la relie à son alerte Strapi une fois chargée en
    base par Dagster. Suppose `_controler_geometries` passé."""
    fichiers: dict[str, dict] = {}
    for ligne in lignes:
        territoire = _texte(ligne.get("territoire_propose"))
        contenu = _lire_geojson(dossier_geometries / _texte(ligne.get("nom_fichier_geometrie")))
        if territoire not in fichiers:
            nom_fichier = _nom_fichier_territoire(code_departement, territoire)
            collection = {"type": "FeatureCollection", "name": nom_fichier.removesuffix(".geojson")}
            if contenu.get("crs"):
                collection["crs"] = contenu["crs"]
            collection["features"] = []
            fichiers[territoire] = {"nom_fichier": nom_fichier, "contenu": collection}
        for entite in contenu["features"]:
            proprietes = {"id_geometrie": _texte(ligne.get("id_geometrie")), "alert_slug": _texte(ligne.get("alert_slug_propose"))}
            fichiers[territoire]["contenu"]["features"].append({**entite, "properties": proprietes})
    for fichier in fichiers.values():
        fichier["nb_entites"] = len(fichier["contenu"]["features"])
    return fichiers


def _deposer_fichiers(fichiers: dict[str, dict], dossier_local: Path, box_folder_id: str) -> dict[str, tuple[str, str | None]]:
    """Écrit chaque fichier de territoire dans `dossier_local`, le relit,
    puis le dépose sur Box (création ou nouvelle version, voir `client_box`).
    Retourne `{territoire: (url_box, None)}` ou `{territoire: ("", erreur)}`
    — un échec n'arrête pas les autres territoires. Jamais en dry-run."""
    dossier_local.mkdir(exist_ok=True)
    depots: dict[str, tuple[str, str | None]] = {}
    for territoire, fichier in sorted(fichiers.items()):
        chemin = dossier_local / fichier["nom_fichier"]
        try:
            with chemin.open("w", encoding="utf-8") as sortie:
                json.dump(fichier["contenu"], sortie, ensure_ascii=False)
            if len(_lire_geojson(chemin).get("features") or []) != fichier["nb_entites"]:
                raise ValueError(f"relecture de {chemin.name} : nombre d'entités différent")
            url = client_box.televerser_geometrie(chemin, box_folder_id)
            depots[territoire] = (url, None)
            print(f"[Box] {fichier['nom_fichier']} ({fichier['nb_entites']} zone(s)) déposé : {url}")
        except Exception as exc:
            depots[territoire] = ("", f"dépôt Box de {fichier['nom_fichier']} : {exc}")
            print(f"[Box] ÉCHEC {fichier['nom_fichier']} : {exc}")
    return depots


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
        vides = [champ for colonne, champ in CHAMPS_OBLIGATOIRES.items() if not _texte(ligne.get(colonne))]
        if vides:
            problemes.append(
                f"g{id_geometrie} : champ(s) Strapi vide(s) : {', '.join(vides)} — "
                "l'alerte serait créée en brouillon mais impossible à publier"
            )
        label = _texte(ligne.get("label_propose"))
        if label and label not in LABELS_AUTORISES:
            problemes.append(f"g{id_geometrie} : label {label!r} hors des valeurs autorisées {LABELS_AUTORISES}")

    # Unicité contrôlée sans tenir compte des majuscules (13/11/2026) : deux
    # slugs qui ne diffèrent que par la casse (ex. « ZoneUA » / « ZoneUa »)
    # sont distincts pour Strapi, mais pas pour la recherche Notion, ni pour
    # un humain qui les lit — constaté en réel sur le 067 le 10/11/2026.
    # On regroupe donc les slugs par leur forme en minuscules (`casefold`).
    par_slug: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ligne in lignes:
        alert_slug = _texte(ligne.get("alert_slug_propose"))
        if alert_slug:
            par_slug[alert_slug.casefold()].append((alert_slug, _texte(ligne.get("id_geometrie"))))
    for _, occurrences in sorted(par_slug.items()):
        if len(occurrences) < 2:
            continue
        detail = ", ".join(f"g{id_geometrie} {slug!r}" for slug, id_geometrie in occurrences)
        if len({slug for slug, _ in occurrences}) == 1:
            problemes.append(f"alert_slug en double ({detail}) — un envoi écraserait une règle par une autre")
        else:
            problemes.append(
                f"alert_slug identiques aux majuscules près ({detail}) — Notion les confondrait "
                "et écraserait une page par l'autre"
            )
    return problemes


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
    ligne: dict, alert_slug: str, nom_fichier: str, depot: tuple[str, str | None] | None, envoyer: bool
) -> tuple[str, str, str | None]:
    """Retourne `(action, page_id, message_erreur)` — mêmes conventions que
    `_traiter_strapi`. `nom_fichier` est le fichier du territoire de la
    ligne ; `depot` est le résultat de son dépôt Box (`(url, erreur)`,
    `None` en dry-run). Si ce dépôt a échoué, la page n'est pas écrite : une
    page sans lien vers sa géométrie n'aurait pas de sens."""
    try:
        if envoyer:
            url_geometrie, erreur_depot = depot
            if erreur_depot:
                raise RuntimeError(erreur_depot)
            champs = client_notion.ChampsPageNotion(
                territoire=_texte(ligne.get("territoire_propose")),
                description=_texte(ligne.get("titre_propose")),
                alert_slug=alert_slug,
                url_geometrie=url_geometrie,
                nom_fichier=nom_fichier,
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
        print(f"  [Notion] (dry-run) data → fichier du territoire {nom_fichier}")
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
    problemes += _controler_geometries(lignes, dossier_geometries, code_departement)
    if problemes:
        raise ExportInvalide(problemes)

    # Un fichier géométrie par territoire (évolution du 16/11/2026), constitué
    # en mémoire avant tout appel réseau.
    fichiers = _fichiers_par_territoire(lignes, dossier_geometries, code_departement)
    print(f"{len(fichiers)} fichier(s) géométrie par territoire, pour {len(lignes)} zone(s) :")
    for fichier in sorted(fichiers.values(), key=lambda f: f["nom_fichier"]):
        print(f"  {fichier['nom_fichier']} — {fichier['nb_entites']} zone(s)")

    # Vérifié tôt, avant de traiter la moindre ligne — une configuration
    # manquante n'a rien d'un échec isolé, rien n'est exploitable sans elle.
    client_strapi.verifier_configuration(environnement)
    client_notion.verifier_configuration()
    client_box.verifier_configuration()

    date_traitement = date.today().isoformat()

    # Dépôt Box une fois par territoire, avant le traitement ligne à ligne.
    # En dry-run : rien n'est écrit, ni sur le disque ni sur Box.
    if envoyer:
        depots = _deposer_fichiers(fichiers, dossier / f"etape7_{code_departement}_geometries", box_folder_id)
    else:
        depots = {}
        print(f"[Box] (dry-run) écrirait ces fichiers dans etape7_{code_departement}_geometries/ "
              f"puis les déposerait dans le dossier {box_folder_id}")

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

            territoire = _texte(ligne.get("territoire_propose"))
            action_notion, notion_page_id, erreur_notion = _traiter_notion(
                ligne, alert_slug, fichiers[territoire]["nom_fichier"], depots.get(territoire), envoyer
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
